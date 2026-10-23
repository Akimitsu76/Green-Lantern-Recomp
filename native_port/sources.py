"""Bounded, read-only structural inspection. Never decrypts a source."""
import hashlib
import os
from pathlib import Path
import stat
import struct
from .errors import PortError

SECTOR = 2048
MAGIC = b'MICROSOFT*XBOX*MEDIA'
PARTITIONS = (0, 0xFB20, 0x20600, 0x2080000, 0xFD90000)


def source_path(value):
    p = Path(value).expanduser()
    try:
        p = p.resolve(strict=True)
        s = p.stat()
        if not stat.S_ISREG(s.st_mode):
            raise PortError('NOT_FILE', 'A entrada precisa ser um arquivo regular.')
        if not s.st_mode & 0o444 or not os.access(p, os.R_OK):
            raise PortError('UNREADABLE', 'Sem permissão de leitura.')
        return p
    except (OSError, ValueError, RuntimeError) as e:
        raise PortError('SOURCE_PATH', str(e)) from e


def read_at(f, offset, size, total):
    if offset < 0 or size < 0 or offset + size > total:
        raise PortError('TRUNCATED', 'Região fora dos limites do arquivo.', offset=offset, size=size)
    f.seek(offset)
    b = f.read(size)
    if len(b) != size:
        raise PortError('TRUNCATED', 'Leitura incompleta.')
    return b


def inspect_imports(blob):
    if len(blob) < 12:
        raise PortError('BAD_XEX', 'Cabeçalho de imports incompleto.')
    size, string_bytes, count = struct.unpack_from('>III', blob)
    if size != len(blob) or 12 + string_bytes > size or count > 4096:
        raise PortError('BAD_XEX', 'Tabela de strings de imports inválida.')
    names, pos = [], 12
    strings_end = 12 + string_bytes
    for _ in range(count):
        end = blob.find(b'\0', pos, strings_end)
        if end < 0:
            raise PortError('BAD_XEX', 'Nome de biblioteca sem terminador.')
        names.append(blob[pos:end].decode('ascii', errors='replace'))
        pos = 12 + ((end + 1 - 12 + 3) // 4) * 4
    pos, libraries = strings_end, []
    while pos < size:
        if size-pos < 40:
            raise PortError('BAD_XEX', 'Registro de biblioteca incompleto.')
        length = struct.unpack_from('>I', blob, pos)[0]
        ident, version, minimum, name_index, records = struct.unpack_from('>IIIHH', blob, pos+24)
        name_index &= 255
        if length < 40 + records*4 or pos+length > size or name_index >= len(names):
            raise PortError('BAD_XEX', 'Registro de biblioteca fora dos limites.')
        libraries.append({'name': names[name_index], 'id': ident,
                          'version_raw': f'{version:08X}', 'minimum_version_raw': f'{minimum:08X}',
                          'import_record_count': records, 'resolved_ordinals': False})
        pos += length
    return libraries


def inspect_xex(f, total):
    h = read_at(f, 0, 24, total)
    magic, flags, pe, reserved, security, count = struct.unpack('>4s5I', h)
    if magic != b'XEX2':
        raise PortError('BAD_XEX', 'Assinatura XEX2 ausente.')
    table_end = 24 + count * 8
    if count > 4096 or pe < table_end or pe >= total or security < table_end or security + 4 > pe:
        raise PortError('BAD_XEX', 'Cabeçalho XEX2 inconsistente.')
    table = read_at(f, 24, count * 8, total)
    info = {'format': 'xex2', 'payload_offset': pe, 'flags': flags,
            'title_id': None, 'entry_point': None, 'image_base': None,
            'encryption': None, 'compression': None, 'optional_headers': [],
            'validation': 'header-only', 'complete_assets': False}
    keys = set()
    for key, value in struct.iter_unpack('>II', table):
        if key in keys:
            raise PortError('BAD_XEX', 'Cabeçalho opcional duplicado.')
        keys.add(key)
        units = key & 255
        if units in (0, 1):  # type 1 stores an inline DWORD, not a file offset
            info['optional_headers'].append({'key': f'0x{key:08X}', 'kind': 'inline', 'value': value})
            if key == 0x10100:
                info['entry_point'] = f'0x{value:08X}'
            elif key == 0x10201:
                info['image_base'] = f'0x{value:08X}'
            continue
        length = units * 4
        if units == 255:
            if value < table_end or value + 4 > pe:
                raise PortError('BAD_XEX', 'Ponteiro opcional inválido.')
            length = struct.unpack('>I', read_at(f, value, 4, total))[0]
            if length < 4:
                raise PortError('BAD_XEX', 'Tamanho opcional inválido.')
        if value < table_end or value + length > pe:
            raise PortError('BAD_XEX', 'Cabeçalho opcional fora do cabeçalho XEX.')
        info['optional_headers'].append({'key': f'0x{key:08X}', 'kind': 'file-range',
                                         'offset': value, 'size': length})
        if key == 0x40006:
            raw = read_at(f, value, 24, total)
            info['title_id'] = f'{struct.unpack_from(">I", raw, 12)[0]:08X}'
            info['media_id'] = f'{struct.unpack_from(">I", raw)[0]:08X}'
            info['version_raw'] = f'{struct.unpack_from(">I", raw, 4)[0]:08X}'
        elif key == 0x103FF:
            info['import_libraries'] = inspect_imports(read_at(f, value, length, total))
        elif key == 0x200FF:
            if (length - 4) % 16:
                raise PortError('BAD_XEX', 'Tabela de bibliotecas estáticas desalinhada.')
            libs = []
            for off in range(value+4, value+length, 16):
                raw = read_at(f, off, 16, total)
                major, minor, build = struct.unpack_from('>HHH', raw, 8)
                libs.append({'name': raw[:8].rstrip(b'\0').decode('ascii', errors='replace'),
                             'major': major, 'minor': minor, 'build': build})
            info['static_libraries'] = libs
        elif key == 0x3FF:
            if length < 8:
                raise PortError('BAD_XEX', 'File format info incompleto.')
            _, encryption, compression = struct.unpack('>IHH', read_at(f, value, 8, total))
            info.update(encryption=encryption, compression=compression)
            info['code_access'] = ('encrypted' if encryption else
                                   'compressed' if compression else 'plain-payload')
            if compression == 1:
                if (length - 8) % 8:
                    raise PortError('BAD_XEX', 'Tabela de compressão básica desalinhada.')
                pairs = list(struct.iter_unpack('>II', read_at(f, value+8, length-8, total)))
                stored = sum(pair[0] for pair in pairs)
                if stored > total - pe:
                    raise PortError('TRUNCATED', 'Dados dos blocos XEX excedem o payload.')
                info['basic_compression'] = {'block_count': len(pairs), 'stored_bytes': stored,
                                             'expanded_bytes': sum(a+b for a, b in pairs)}
    return info


def inspect_iso(f, total):
    for base in PARTITIONS:
        off = base + 32 * SECTOR
        if off + SECTOR > total:
            continue
        h = read_at(f, off, SECTOR, total)
        if h[:20] != MAGIC:
            continue
        if h[-20:] != MAGIC:
            raise PortError('BAD_ISO', 'Descritor XDVDFS sem assinatura final.')
        root_sector, root_size = struct.unpack_from('<II', h, 20)
        root = base + root_sector * SECTOR
        if not root_size or root < off + SECTOR or root + root_size > total:
            raise PortError('TRUNCATED', 'Diretório raiz XDVDFS fora da imagem.')
        return {'format': 'xdvdfs', 'partition_offset': base, 'root_offset': root,
                'root_size': root_size, 'validation': 'volume-only', 'title_id': None,
                'complete_assets': None}
    raise PortError('UNSUPPORTED_ISO',
                    'XDVDFS não encontrado nos offsets suportados. Extração bloqueada; '
                    'a causa pode ser formato não suportado, dump inconsistente ou proteção. '
                    'A extensão .iso não comprova o formato.', offsets=list(PARTITIONS))


def inspect_source(value, cancel=None):
    candidate = Path(value).expanduser()
    if candidate.is_dir():
        return inspect_folder(candidate, cancel)
    p = source_path(value)
    try:
        with p.open('rb') as f:
            before = os.fstat(f.fileno())
            size = before.st_size
            if size < 24:
                raise PortError('TRUNCATED', 'Entrada pequena demais.')
            magic = f.read(4)
            if magic == b'XEX2':
                result = inspect_xex(f, size)
            elif p.suffix.lower() == '.xex':
                raise PortError('BAD_XEX', 'Assinatura XEX2 ausente.')
            else:
                result = inspect_iso(f, size)
            after = os.fstat(f.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise PortError('SOURCE_CHANGED', 'A entrada mudou durante a inspeção.')
            result.update(path=str(p), size=size)
            return result
    except OSError as e:
        raise PortError('SOURCE_READ', str(e)) from e


def digest_source(value, cancel):
    p = source_path(value)
    h = hashlib.sha256()
    with p.open('rb') as f:
        before = os.fstat(f.fileno())
        while True:
            cancel.check()
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
        after = os.fstat(f.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise PortError('SOURCE_CHANGED', 'A entrada mudou durante o hash.')
    return h.hexdigest()


def inspect_folder(value, cancel=None):
    """Inventory an extracted game folder without executing any files.

    Prefer default.xex at the root, otherwise require exactly one XEX candidate.
    Asset presence is inventoried, never certified complete without known hashes.
    """
    from .tasks import Cancellation
    cancel = cancel or Cancellation()
    root = Path(value).expanduser().resolve(strict=True)
    records, xex_files = [], []
    count, total = 0, 0
    manifest = hashlib.sha256()
    def walk_error(error):
        raise PortError('SOURCE_READ', str(error)) from error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        cancel.check()
        rel_dir = Path(directory).relative_to(root)
        if len(rel_dir.parts) > 32:
            raise PortError('FOLDER_LIMIT', 'Pasta excede o limite de 32 níveis.')
        if len(dirs) + len(files) > 100000:
            raise PortError('FOLDER_LIMIT', 'Diretório grande demais para inventário.')
        for name in sorted(dirs + files):
            p = Path(directory) / name
            if p.is_symlink():
                raise PortError('SOURCE_SYMLINK', 'Link simbólico dentro da pasta do jogo não é aceito.',
                                path=str(p.relative_to(root)))
        dirs.sort()
        for name in sorted(files):
            cancel.check()
            p = source_path(Path(directory) / name)
            stat_info = p.stat()
            count += 1
            if count > 100000:
                raise PortError('FOLDER_LIMIT', 'Pasta excede o limite de 100.000 arquivos.')
            relative = p.relative_to(root).as_posix()
            total += stat_info.st_size
            manifest.update(relative.encode('utf8', errors='surrogateescape'))
            manifest.update(b'\0')
            manifest.update(f'{stat_info.st_size}:{stat_info.st_mtime_ns}\n'.encode())
            if len(records) < 200:
                records.append({'path': relative, 'size': stat_info.st_size})
            if p.suffix.lower() == '.xex':
                xex_files.append(p)
    if not xex_files:
        raise PortError('MISSING_XEX', 'Nenhum arquivo .xex encontrado na pasta selecionada.')
    defaults = [p for p in xex_files if p.parent == root and p.name.lower() == 'default.xex']
    if len(defaults) == 1:
        executable = defaults[0]
    elif len(xex_files) == 1:
        executable = xex_files[0]
    else:
        raise PortError('AMBIGUOUS_XEX', 'Há vários XEX e nenhum default.xex único na raiz. '
                        'Selecione o executável principal diretamente.',
                        candidates=[p.relative_to(root).as_posix() for p in xex_files[:100]])
    cancel.check()
    result = inspect_source(executable, cancel)
    result.update(input_kind='game-folder', game_directory=str(root), file_count=count,
                  total_bytes=total, asset_file_count=count-len(xex_files),
                  inventory=records, inventory_truncated=count > len(records),
                  xex_candidates=[p.relative_to(root).as_posix() for p in xex_files],
                  directory_manifest_sha256=manifest.hexdigest(), complete_assets=None,
                  assets_status='presence-only; completeness-unverified')
    return result

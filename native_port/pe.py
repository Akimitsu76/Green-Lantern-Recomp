"""Validate Xbox PE32 and normalize a decoded memory image to on-disk section layout."""
import struct
from .errors import PortError


def inspect_pe(data):
    def need(offset, size):
        if offset < 0 or size < 0 or offset+size > len(data):
            raise PortError('BAD_PE', 'Região PE fora da imagem.', offset=offset, size=size)
    need(0, 64)
    if data[:2] != b'MZ':
        raise PortError('BAD_PE', 'Assinatura MZ ausente.')
    nt = struct.unpack_from('<I', data, 60)[0]
    need(nt, 24)
    if data[nt:nt+4] != b'PE\0\0':
        raise PortError('BAD_PE', 'Assinatura PE ausente.')
    machine, count = struct.unpack_from('<HH', data, nt+4)
    opt_size = struct.unpack_from('<H', data, nt+20)[0]
    opt = nt+24
    need(opt, opt_size)
    if machine != 0x1F2 or not 1 <= count <= 96 or opt_size < 96:
        raise PortError('BAD_PE', 'Esperado PE PowerPCBE com seções válidas.')
    if struct.unpack_from('<H', data, opt)[0] != 0x10B:
        raise PortError('BAD_PE', 'Esperado PE32.')
    entry = struct.unpack_from('<I', data, opt+16)[0]
    base = struct.unpack_from('<I', data, opt+28)[0]
    image_size, headers_size = struct.unpack_from('<II', data, opt+56)
    subsystem = struct.unpack_from('<H', data, opt+68)[0]
    if subsystem != 14 or image_size > 1024**3:
        raise PortError('BAD_PE', 'Subsystem ou tamanho da imagem Xbox inválido.')
    need(0, headers_size)
    need(opt+opt_size, count*40)
    sections = []
    for off in range(opt+opt_size, opt+opt_size+count*40, 40):
        name = data[off:off+8].split(b'\0')[0].decode('ascii', errors='replace')
        vsize, rva, raw_size, raw = struct.unpack_from('<IIII', data, off+8)
        flags = struct.unpack_from('<I', data, off+36)[0]
        if rva+max(vsize,raw_size) > image_size or raw+raw_size > 1024**3:
            raise PortError('BAD_PE', 'Seção excede os limites declarados.')
        sections.append(dict(name=name, rva=rva, virtual_size=vsize, raw_offset=raw,
                             raw_size=raw_size, flags=flags, executable=bool(flags & 0x20000000)))
    if not any(s['executable'] and s['rva'] <= entry < s['rva']+s['virtual_size'] for s in sections):
        raise PortError('BAD_PE', 'Entrada fora das seções executáveis.')
    return dict(machine='0x01F2', architecture='PowerPC big-endian', image_base=base,
                entry_point=base+entry, image_size=image_size, headers_size=headers_size, sections=sections)


def normalize_memory_pe(data):
    info = inspect_pe(data)
    required = max(s['rva']+s['raw_size'] for s in info['sections'])
    if len(data) > info['image_size'] or len(data) < required:
        raise PortError('BAD_PE', 'Bytes decodificados não cobrem as seções inicializadas.')
    info['decoded_size'] = len(data)
    ranges = [(0, info['headers_size'])]
    for s in info['sections']:
        if s['raw_size']:
            ranges.append((s['raw_offset'], s['raw_offset']+s['raw_size']))
    ranges.sort()
    if any(a[1] > b[0] for a,b in zip(ranges,ranges[1:])):
        raise PortError('BAD_PE', 'Intervalos de arquivo PE se sobrepõem.')
    out = bytearray(max(end for _,end in ranges))
    out[:info['headers_size']] = data[:info['headers_size']]
    for s in info['sections']:
        out[s['raw_offset']:s['raw_offset']+s['raw_size']] = data[s['rva']:s['rva']+s['raw_size']]
    return bytes(out), info

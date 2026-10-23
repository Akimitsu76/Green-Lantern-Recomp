"""Reproduce the Vulkan driver-cache plugin against the pinned public SDK."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import urllib.request

from .errors import PortError

SOURCES = (
    ('rexglue-source-f5337cdc.zip',
     'https://github.com/rexglue/rexglue-sdk/archive/f5337cdc947ff6d4c4196737e2c807a48f2a1fc2.zip',
     'e116dd1561f1e163600e6393d3c3df12ceaf089771b23b41d0e572056e9db394',
     'rexglue-sdk-f5337cdc947ff6d4c4196737e2c807a48f2a1fc2'),
    ('glslang-f4f1d8a3.zip',
     'https://github.com/KhronosGroup/glslang/archive/f4f1d8a352ca1908943aea2ad8c54b39b4879080.zip',
     'c149464d54d840ddceab33fc0ea0cf36b2e22a7634aa1166d56cfaed583e41ea',
     'glslang-f4f1d8a352ca1908943aea2ad8c54b39b4879080'),
)


def apply_patch_exact(root, patch_text):
    """Apply reviewed unified text hunks with exact context, without fuzz/shell."""
    lines = patch_text.splitlines(keepends=True)
    i = 0
    changed = []
    while i < len(lines):
        if not lines[i].startswith('+++ b/'):
            i += 1
            continue
        relative = lines[i][6:].strip()
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise PortError('CACHE_PATCH', 'Caminho inválido no patch do SDK.')
        original = path.read_text().splitlines(keepends=True)
        output, position = [], 0
        i += 1
        while i < len(lines) and not lines[i].startswith('diff --git '):
            match = re.match(r'@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@', lines[i])
            if not match:
                i += 1
                continue
            start = int(match[1]) - 1
            if start < position or start > len(original):
                raise PortError('CACHE_PATCH', 'Offset inválido no patch do SDK.')
            output.extend(original[position:start])
            position = start
            i += 1
            while i < len(lines) and lines[i][:1] in (' ', '+', '-') and not lines[i].startswith(('+++ ', '--- ')):
                kind, text = lines[i][0], lines[i][1:]
                if kind in (' ', '-'):
                    if position >= len(original) or original[position] != text:
                        raise PortError('CACHE_PATCH', 'O contexto do patch não corresponde ao SDK fixado.')
                    position += 1
                if kind in (' ', '+'):
                    output.append(text)
                i += 1
        output.extend(original[position:])
        path.write_text(''.join(output))
        changed.append(path)
    if not changed:
        raise PortError('CACHE_PATCH', 'Patch vazio ou não reconhecido.')
    return changed


def build_cache_plugin(root, work, prefix, tools, cancel, emit, run, allow_download):
    from .native_build import file_hash, safe_extract
    patch = root / 'integrations/rexglue/patches/0001-vulkan-driver-pipeline-cache.patch'
    recipe = hashlib.sha256((file_hash(patch) + file_hash(root / 'integrations/rexglue/plugin-only/CMakeLists.txt')).encode()).hexdigest()[:20]
    cache_root = work.path('tools/cache-plugin/' + recipe)
    product = cache_root / 'build/isolated-runtime/librexgpu-xenosrd.so'
    identity = cache_root / 'product.json'
    if product.is_file() and identity.is_file():
        if json.loads(identity.read_text()).get('sha256') == file_hash(product):
            return product
    cache_root.mkdir(parents=True, exist_ok=True)
    extracted = []
    for filename, url, checksum, directory in SOURCES:
        archive = work.path('tools/downloads/' + filename)
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.is_file() or file_hash(archive) != checksum:
            if not allow_download:
                raise PortError('SDK_MISSING', 'As fontes públicas do cache estão ausentes; habilite baixar SDK.')
            emit({'task': 'Baixar fontes públicas do cache', 'state': 'running', 'message': url})
            fd, temporary = tempfile.mkstemp(dir=archive.parent)
            try:
                with os.fdopen(fd, 'wb') as output, urllib.request.urlopen(url, timeout=30) as response:
                    while block := response.read(1024 * 1024):
                        cancel.check()
                        output.write(block)
                        if output.tell() > 256 * 1024**2:
                            raise PortError('SDK_DOWNLOAD', 'Arquivo excedeu o tamanho previsto.')
                if file_hash(Path(temporary)) != checksum:
                    raise PortError('SDK_HASH', 'Hash inválido nas fontes públicas do SDK.')
                os.replace(temporary, archive)
            finally:
                Path(temporary).unlink(missing_ok=True)
        destination = cache_root / directory
        if not destination.is_dir():
            safe_extract(archive, cache_root)
        extracted.append(destination)
    source, glslang = extracted
    marker = cache_root / 'patched.json'
    if not marker.is_file():
        changed = apply_patch_exact(source, patch.read_text())
        marker.write_text(json.dumps({str(p.relative_to(source)): file_hash(p) for p in changed}))
    for relative, expected in json.loads(marker.read_text()).items():
        if file_hash(source / relative) != expected:
            raise PortError('CACHE_CHANGED', 'As fontes verificadas do cache foram alteradas.')
    cmake, ninja, compiler, _ = tools
    run('Configurar cache persistente', [cmake, '-S', root / 'integrations/rexglue/plugin-only',
        '-B', cache_root / 'build', '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
        f'-DCMAKE_C_COMPILER={str(Path(compiler).with_name("clang"))}',
        f'-DCMAKE_CXX_COMPILER={compiler}', f'-DCMAKE_MAKE_PROGRAM={ninja}',
        f'-DASTER_REX_SOURCE={source}', f'-DASTER_REX_PREFIX={prefix}',
        f'-DASTER_GLSLANG_SOURCE={glslang}', '-DASTER_PINNED_ARCHIVE_SOURCES=ON'])
    run('Compilar cache persistente', [cmake, '--build', cache_root / 'build', '--parallel', '2'])
    if not product.is_file():
        raise PortError('CACHE_BUILD', 'Plugin de cache não foi gerado.')
    identity.write_text(json.dumps({'sha256': file_hash(product)}))
    return product

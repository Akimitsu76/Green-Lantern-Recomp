#!/usr/bin/env python3
"""Build a portable launcher with the host platform's Python/PyInstaller.

Run on Linux for ELF, Windows Python (or Windows Python under Wine) for PE.
Only the explicit public source/resource allowlist is copied, never .aster.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import zipfile

PUBLIC_DIRS = ['native_port', 'games', 'integrations/rexglue']
PUBLIC_SCRIPTS = ['play_green_lantern.py']
FORBIDDEN_SUFFIXES = {'.xex', '.iso', '.xexp', '.lvl_760', '.pdb', '.xdb', '.vkcache', '.usm'}


def copy_public(root, destination):
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for directory in PUBLIC_DIRS:
        for source in (root / directory).rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix in ('.pyc', '.log'):
                continue
            if source.is_symlink() or source.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ValueError('Forbidden distribution input: ' + str(source))
            relative = source.relative_to(root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(relative))
    for name in PUBLIC_SCRIPTS:
        (destination / 'scripts').mkdir(exist_ok=True)
        shutil.copy2(root / 'scripts' / name, destination / 'scripts' / name)
        copied.append('scripts/' + name)
    (destination / 'docs').mkdir(exist_ok=True)
    for name in ['PORTABLE_BUILD.md', 'THIRD_PARTY_NOTICES.md']:
        shutil.copy2(root / 'docs' / name, destination / 'docs' / name)
        copied.append('docs/' + name)
    for name in ['pyproject.toml']:
        shutil.copy2(root / name, destination / name)
        copied.append(name)
    shutil.copy2(root / 'docs/PORTABLE_BUILD.md', destination / 'README.md')
    copied.append('README.md')
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('dist'))
    parser.add_argument('--cmake-data', type=Path)
    parser.add_argument('--ninja', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    target = 'windows-x64' if os.name == 'nt' else 'linux-x86_64'
    work = root / '.aster/packaging' / target
    work.mkdir(parents=True, exist_ok=True)
    entry = root / 'apps/launcher/portable_entry.py'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
               '--name', 'AsterNative', '--distpath', str(output / target),
               '--workpath', str(work / 'build'), '--specpath', str(work),
               '--paths', str(root), '--collect-submodules', 'native_port',
               '--collect-submodules', 'games', '--collect-submodules', 'tkinter',
               '--hidden-import', 'ssl', '--hidden-import', 'tomllib',
               '--hidden-import', 'urllib.request', '--hidden-import', 'zipfile',
               '--hidden-import', 'shlex', str(entry)]
    if os.name == 'nt':
        command.insert(4, '--windowed')
    else:
        command[4:4] = ['--hidden-import', 'resource']
    env = os.environ.copy()
    env['PYINSTALLER_CONFIG_DIR'] = str(work / 'cache')
    subprocess.run(command, check=True, cwd=root, env=env)
    bundle = output / target / 'AsterNative'
    sources = copy_public(root, bundle / 'app')
    if args.cmake_data:
        cmake = bundle / 'app/tools/cmake'
        for directory in ('bin', 'share'):
            shutil.copytree(args.cmake_data / directory, cmake / directory, dirs_exist_ok=True)
    if args.ninja:
        ninja = bundle / 'app/tools/ninja'
        ninja.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.ninja, ninja / args.ninja.name)
    licenses = bundle / 'LICENSES'
    licenses.mkdir(exist_ok=True)
    candidates = [Path(sys.base_prefix) / 'LICENSE.txt',
                  Path(sys.base_prefix) / 'lib' / ('python' + str(sys.version_info.major) + '.' + str(sys.version_info.minor)) / 'LICENSE.txt']
    for candidate in candidates:
        if candidate.is_file():
            shutil.copy2(candidate, licenses / 'Python-LICENSE.txt')
    import importlib.metadata
    distribution = importlib.metadata.distribution('pyinstaller')
    for relative in distribution.files or []:
        if relative.name in ('COPYING.txt', 'LICENSE', 'LICENSE.txt'):
            source = Path(distribution.locate_file(relative))
            if source.is_file():
                shutil.copy2(source, licenses / ('PyInstaller-' + source.name))
    if args.cmake_data and (args.cmake_data / 'doc').is_dir():
        shutil.copytree(args.cmake_data / 'doc', licenses / 'CMake', dirs_exist_ok=True)
    if args.ninja:
        wheel_root = args.ninja.resolve().parents[2]
        for directory in wheel_root.glob('ninja-*.dist-info'):
            for source in directory.rglob('*'):
                if source.is_file() and ('license' in str(source).lower() or 'copying' in source.name.lower()):
                    shutil.copy2(source, licenses / ('Ninja-' + source.name))
    for base in [Path(sys.base_prefix) / 'tcl', Path(sys.base_prefix) / 'lib']:
        if base.is_dir():
            for terms in base.glob('*/license.terms'):
                shutil.copy2(terms, licenses / ('TclTk-' + terms.parent.name + '.txt'))
    shutil.copy2(root / 'docs/THIRD_PARTY_NOTICES.md', bundle / 'THIRD_PARTY_NOTICES.md')
    notice = bundle / 'LEIA-ME.txt' 
    notice.write_text('Aster Native - launcher experimental\n\n'
        'Extraia TODA a pasta. Abra AsterNative.exe (Windows) ou AsterNative (Linux).\n'
        'Selecione seu dump extraido, abra Jogo e arquivos e clique Gerar port nativo.\n'
        'O primeiro uso requer Clang >=18 / C++23. Windows: VS Build Tools C++ x64,\n'
        'Windows SDK e Clang. Linux: toolchain Clang e headers C/C++ do sistema.\n'
        'O SDK ReXGlue fixado e baixado com verificacao de hash. Nenhum arquivo do\n'
        'jogo ou codigo recompilado e distribuido neste pacote.\n'
        'Revisao suportada: SHA256 do default.xex\n'
        '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1\n'
        'Use uma pasta gravavel. Veja app/docs/PORTABLE_BUILD.md.\n', encoding='utf8')
    manifest = {'platform': target, 'public_sources': sources, 'game_content_included': False,
                'files': {str(p.relative_to(bundle)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in bundle.rglob('*') if p.is_file()}}
    (bundle / 'PACKAGE.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if os.name == 'nt':
        archive = output / 'AsterNative-windows-x64.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for p in bundle.rglob('*'):
                if p.is_file():
                    z.write(p, Path('AsterNative') / p.relative_to(bundle))
    else:
        archive = output / 'AsterNative-linux-x86_64.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            tar.add(bundle, arcname='AsterNative')
    print(json.dumps({'bundle': str(bundle), 'archive': str(archive),
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Link one local host hook against existing CPU objects, without main build/codegen/staging."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess


def compiler_segment(line):
    words = shlex.split(line)
    starts = [i for i, word in enumerate(words) if Path(word).name == 'clang++']
    if len(starts) != 1:
        raise ValueError('Expected exactly one Clang compiler segment')
    begin = starts[0]
    end = next((i for i in range(begin, len(words)) if words[i] in ('&&', ';', '||', '|')), len(words))
    return words[begin:end]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('--hook', type=Path, default=Path('integrations/rexglue/experiments/frame_pacing.cpp'))
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,55}', args.label):
        parser.error('Invalid experiment label')
    root = Path(__file__).resolve().parents[1]
    original = root / '.aster/build/rex-green'
    hook = (root / args.hook).resolve(strict=True)
    if not hook.is_relative_to(root) or hook.suffix != '.cpp':
        parser.error('Hook must be a C++ source inside this workspace')
    output = root / '.aster/build' / ('rex-' + args.label)
    output.mkdir(exist_ok=False)
    shutil.copy2(hook, output / 'hook.cpp')
    main_binary = original / 'aster_green_lantern'
    plugin = original / 'librexgpu-xenosrd.so'
    before = {str(p): digest(p) for p in (main_binary, plugin)}
    def commands(target):
        return subprocess.check_output(['ninja', '-C', str(original), '-t', 'commands', target], text=True).splitlines()
    compile_cmd = compiler_segment(commands('CMakeFiles/aster_green_lantern.dir/src/main.cpp.o')[-1])
    for flag, value in [('-c', output / 'hook.cpp'), ('-o', output / 'hook.o'), ('-MF', output / 'hook.o.d'), ('-MT', output / 'hook.o')]:
        compile_cmd[compile_cmd.index(flag) + 1] = str(value)
    link_cmd = compiler_segment(commands('aster_green_lantern')[-1])
    objects = []
    for i, word in enumerate(link_cmd):
        if word.endswith('.o'):
            path = (original / word).resolve(strict=True)
            if not path.is_relative_to(original):
                raise ValueError('CPU object outside original build')
            link_cmd[i] = str(path)
            objects.append(path)
        elif word.startswith('--dependency-file='):
            link_cmd[i] = '--dependency-file=' + str(output / 'link.d')
        elif word.startswith('-Wl,-rpath,'):
            # Ninja's shell command quotes $ORIGIN for an additional shell
            # layer. argv execution needs the literal token, without slashes.
            if word.removeprefix('-Wl,-rpath,').replace('\\', '') != '$ORIGIN':
                raise ValueError('Unexpected runtime search path')
            link_cmd[i] = '-Wl,-rpath,$ORIGIN'
    if len(objects) != 114:
        raise ValueError('Expected the reviewed 114 existing CPU host/recomp objects')
    link_cmd[link_cmd.index('-o') + 1] = str(output / 'aster_green_lantern')
    link_cmd.insert(link_cmd.index('-o'), str(output / 'hook.o'))
    identities = {str(p): digest(p) for p in objects}
    manifest = {'compile_command': compile_cmd, 'link_command': link_cmd,
                'cwd': str(original), 'original_before': before, 'objects_before': identities,
                'hook_source': str(hook), 'hook_snapshot': str(output / 'hook.cpp'), 'hook_sha256': digest(hook), 'post_build_executed': False,
                'codegen_executed': False}
    with (output / 'build.log').open('w') as log:
        subprocess.run(compile_cmd, cwd=original, stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(link_cmd, cwd=original, stdout=log, stderr=subprocess.STDOUT, check=True)
    for name in ('librexgpu-xenosrd.so', 'librexruntimerd.so', 'libTracyClientrd.so'):
        shutil.copy2(original / name, output / name)
    if before != {path: digest(Path(path)) for path in before} or identities != {path: digest(Path(path)) for path in identities}:
        raise RuntimeError('Original artifacts changed unexpectedly')
    manifest.update(executable_sha256=digest(output / 'aster_green_lantern'), original_preserved=True,
                    plugin_sha256=digest(output / plugin.name))
    (output / 'experiment-build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'output': str(output), 'executable_sha256': manifest['executable_sha256'],
                      'original_preserved': True, 'reused_cpu_objects': len(objects)}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

import hashlib
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

from native_port.errors import PortError
from native_port.native_build import build_native, read_install, safe_extract, verify_install
from native_port.native_cache import apply_patch_exact
from native_port.tasks import Cancellation
from native_port.workspace import Workspace


class NativeBuildTests(unittest.TestCase):
    def test_zip_cannot_escape_or_create_symlinks(self):
        for name, mode in [('../outside', 0), ('C:/outside', 0), ('/outside', 0),
                           ('link', 0o120777 << 16)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / 'input.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    item = zipfile.ZipInfo(name)
                    item.external_attr = mode
                    z.writestr(item, 'unsafe')
                with self.assertRaises(PortError):
                    safe_extract(archive, root / 'out')
                self.assertFalse((root / 'outside').exists())

    def test_reviewed_patch_rejects_wrong_context_without_changing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'file.cpp'
            source.write_text('one\ntwo\n')
            patch_text = ('diff --git a/file.cpp b/file.cpp\n--- a/file.cpp\n+++ b/file.cpp\n'
                          '@@ -1,2 +1,2 @@\n one\n-wrong\n+new\n')
            with self.assertRaises(PortError):
                apply_patch_exact(root, patch_text)
            self.assertEqual(source.read_text(), 'one\ntwo\n')
            changed = apply_patch_exact(root, patch_text.replace('-wrong', '-two'))
            self.assertEqual(changed, [source])
            self.assertEqual(source.read_text(), 'one\nnew\n')

    def test_local_generation_is_cached_preserves_case_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'Green_Lantern Assets'
            game.mkdir()
            xex = game / 'Default.XEX'
            xex.write_bytes(b'original synthetic dump')
            sha = hashlib.sha256(xex.read_bytes()).hexdigest()
            for relative in ['games/green_lantern_rex_hints.toml',
                             'integrations/rexglue/portable_timing.cpp',
                             'integrations/rexglue/plugin-only/CMakeLists.txt',
                             'integrations/rexglue/patches/0001-vulkan-driver-pipeline-cache.patch',
                             'integrations/rexglue/patches/0003-vulkan-deferred-pipelines.patch',
                             'integrations/rexglue/presenter-filter/CMakeLists.txt']:
                p = root / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('public fixture')
            prefix = root / 'sdk'
            (prefix / 'bin').mkdir(parents=True)
            (prefix / 'lib').mkdir()
            (prefix / 'lib/librexruntimerd.so').write_bytes(b'runtime')
            cache = root / '.aster/tools/cache-plugin/librexgpu-xenosrd.so'
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b'patched cache')
            work = Workspace(root / '.aster', root)
            info = {'game_directory': str(game), 'path': str(xex)}
            def process(arguments, cwd, cancel, **options):
                if 'init' in arguments:
                    project = Path(arguments[arguments.index('--project-root') + 1])
                    project.mkdir(parents=True)
                    (project / 'aster_green_lantern_manifest.toml').write_text('[entrypoint]\nincludes=[]\n')
                    (project / 'CMakeLists.txt').write_text('rexglue_setup_target(aster_green_lantern)\n')
                if 'codegen' in arguments:
                    manifest = Path(arguments[-1])
                    parsed = tomllib.loads(manifest.read_text())
                    self.assertEqual(parsed['entrypoint']['includes'], ['hints.toml'])
                    self.assertEqual((manifest.parent / parsed['entrypoint']['file_path']).resolve(), xex)
                    generated = manifest.parent / 'generated/default/file.cpp'
                    generated.parent.mkdir(parents=True)
                    generated.write_text('synthetic generated fixture')
                if '--build' in arguments:
                    build = Path(arguments[arguments.index('--build') + 1])
                    build.mkdir(parents=True, exist_ok=True)
                    (build / 'aster_green_lantern').write_bytes(b'fresh generated executable')
                return {'stdout': 'ok', 'stderr': '', 'returncode': 0}
            with patch('native_port.native_build.XEX_SHA256', sha), \
                    patch('native_port.native_build.inspect_source', return_value=info), \
                    patch('native_port.native_build.ensure_sdk', return_value=prefix), \
                    patch('native_port.native_build.toolchain', return_value=('cmake', 'ninja', 'clang++', {})), \
                    patch('native_port.native_build.run_process', side_effect=process) as command, \
                    patch('native_port.native_cache.build_cache_plugin', return_value=cache), \
                    patch('native_port.native_cache.build_presenter_filter', return_value=cache):
                first = build_native(game, work)
                count = command.call_count
                second = build_native(game, work)
                self.assertEqual(first, second)
                self.assertEqual(command.call_count, count, 'cache hit must not run codegen/compiler')
                before_codegen = sum('codegen' in call.args[0] for call in command.call_args_list)
                (root / '.aster/config/native-install.json').unlink()
                resumed = build_native(game, work)
                self.assertEqual(sum('codegen' in call.args[0] for call in command.call_args_list), before_codegen)
                self.assertEqual(resumed['binary'], first['binary'])
                self.assertFalse(first['ready'])
                self.assertFalse(first['gameplay_verified'])
                verify_install(root, first)
                self.assertEqual(read_install(root), first)
                previous_codegen = sum('codegen' in call.args[0] for call in command.call_args_list)
                previous_host = (root / first['binary']).read_bytes()
                (root / 'integrations/rexglue/patches/0003-vulkan-deferred-pipelines.patch').write_text('updated renderer only')
                first = build_native(game, work)
                self.assertEqual(sum('codegen' in call.args[0] for call in command.call_args_list), previous_codegen,
                                 'renderer-only updates must reuse the verified CPU host')
                self.assertEqual((root / first['binary']).read_bytes(), previous_host)
                verify_install(root, first)
                (root / first['binary']).write_bytes(b'changed')
                with self.assertRaises(PortError):
                    verify_install(root, first)
            self.assertEqual(xex.read_bytes(), b'original synthetic dump')
            self.assertFalse((root / '.aster/runtime').exists())

    def test_malformed_install_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / '.aster/config/native-install.json'
            path.parent.mkdir(parents=True)
            from native_port.native_build import XEX_SHA256
            for files in [['bad'], {'../escape': 'a' * 64}]:
                path.write_text(json.dumps({'schema': 1, 'state': 'built', 'xex_sha256': XEX_SHA256,
                                           'binary': '../escape', 'files': files,
                                           'game_root': 'dump', 'renderer': 'vulkan-fsi'}))
                with self.assertRaises(PortError):
                    read_install(root)

    def test_unsupported_dump_stops_before_downloading_or_compiling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'dump'
            game.mkdir()
            source = game / 'default.xex'
            source.write_bytes(b'unsupported')
            with patch('native_port.native_build.inspect_source', return_value={
                    'path': str(source), 'game_directory': str(game)}), \
                    patch('native_port.native_build.toolchain') as compiler, \
                    self.assertRaises(PortError) as error:
                build_native(game, Workspace(root / '.aster', root), allow_download=True)
            self.assertEqual(error.exception.code, 'BUILD_REVISION')
            compiler.assert_not_called()
            self.assertFalse((root / '.aster').exists())

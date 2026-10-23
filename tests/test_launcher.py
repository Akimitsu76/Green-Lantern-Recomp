import json
import os
import subprocess
import threading
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from fixtures import xex


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Sem DISPLAY; execute com xvfb-run para testar GUI.')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f'Display inacessível: {e}; execute xvfb-run')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        project_patch = patch('native_port.launcher.PROJECT', self.project)
        project_patch.start()
        self.addCleanup(project_patch.stop)
        from native_port.launcher import Launcher
        self.app = Launcher(self.root)
        self.addCleanup(self.app.close)

    def wait_task(self):
        deadline = time.monotonic() + 5
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy)

    def test_launch_disabled_and_invalid_source(self):
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')
        self.app.source.set('/nonexistent/source.iso')
        self.app.inspect()
        self.wait_task()
        self.assertIn('SOURCE_PATH', self.app.status.get())
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')

    def test_inspect_synthetic_xex(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'fixture.xex'
            p.write_bytes(xex())
            self.app.source.set(str(p))
            self.app.inspect()
            self.wait_task()
        self.assertIn('575207E9', self.app.summary.get('1.0', 'end'))
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')

    @patch('native_port.diagnostics.local_tool', return_value=None)
    @patch('native_port.diagnostics.shutil.which', return_value=None)
    def test_missing_dependencies_visible(self, _, __):
        self.app.doctor()
        self.wait_task()
        self.assertIn('cmake: não encontrado', self.app.environment.get('1.0', 'end'))
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')

    def test_desktop_layout_snapshot(self):
        try:
            from PIL import ImageGrab
        except ImportError:
            self.skipTest('Pillow opcional ausente; snapshot não executado.')
        from native_port.workspace import Workspace
        PROJECT = Path(__file__).resolve().parents[1]
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if self.root.winfo_screenwidth() < w or self.root.winfo_screenheight() < h:
            self.skipTest('Xvfb menor que a janela; use -screen 0 1440x900x24 para o snapshot.')
        for button in (self.app.inspect_button, self.app.prepare_button, self.app.launch_button,
                       self.app.experimental_button, self.app.stop_experimental_button,
                       self.app.folder_button, self.app.select_button):
            self.assertTrue(button.winfo_ismapped(), str(button))
            self.assertGreater(button.winfo_width(), 10)
            self.assertGreater(button.winfo_height(), 10)
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), x + w)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), y + h)
            parent = button.master
            self.assertLessEqual(button.winfo_y() + button.winfo_height(), parent.winfo_height())
        self.app.tabs.select(self.app.graphics_tab)
        self.root.update()
        for button in list(self.app.preset_buttons.values()) + list(self.app.target_buttons.values()):
            self.assertTrue(button.winfo_ismapped(), str(button))
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), x + w)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), y + h)
        self.app.tabs.select(self.app.play_tab)
        self.root.update()
        path = Workspace(PROJECT / '.aster', PROJECT).path('reports/launcher.png')
        path.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=(x, y, x+w, y+h), xdisplay=os.environ['DISPLAY']).save(path)

    @patch('native_port.launcher.filedialog.askdirectory')
    def test_select_extracted_folder_and_persist(self, choose):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        (folder / 'assets.dat').write_bytes(b'synthetic')
        choose.return_value = str(folder)
        self.app.select_folder()
        self.wait_task()
        self.assertEqual(self.app.source.get(), str(folder))
        self.assertIn('2 arquivos', self.app.summary.get('1.0', 'end'))
        from native_port.settings import load
        self.assertEqual(load(self.project)['source'], str(folder))
        self.assertEqual(str(self.app.launch_button['state']), 'normal')
        self.assertIn('GERAR PORT', str(self.app.launch_button['text']))

    def test_layout_at_minimum_size(self):
        self.root.geometry('1088x696')
        self.root.update()
        x, y = self.app.play_tab.winfo_rootx(), self.app.play_tab.winfo_rooty()
        for button in (self.app.inspect_button, self.app.prepare_button, self.app.launch_button,
                       self.app.folder_button, self.app.select_button, self.app.experimental_button,
                       self.app.stop_experimental_button, self.app.open_profile_button):
            self.assertTrue(button.winfo_ismapped(), str(button))
            self.assertGreater(button.winfo_width(), 10)
            self.assertGreater(button.winfo_height(), 10)
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), x+self.app.play_tab.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), y+self.app.play_tab.winfo_height())
            parent = button.master
            self.assertLessEqual(button.winfo_y() + button.winfo_height(), parent.winfo_height())

    def test_export_diagnostic_stays_in_workspace(self):
        self.app.export_report()
        path = Path(self.app.report_path.get())
        self.assertTrue(path.is_relative_to(self.project / '.aster/reports'))
        self.assertTrue(path.is_file())

    @patch('native_port.pipeline.diagnostics', return_value={'tools': {}})
    def test_prepare_folder_records_blocker(self, _):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        (folder / 'assets').write_bytes(b'synthetic')
        self.app.source.set(str(folder))
        self.app.prepare()
        self.wait_task()
        import json
        report = json.loads((self.project / '.aster/reports/latest.json').read_text())
        self.assertEqual(report['state'], 'blocked')
        self.assertFalse(report['ready'])
        self.assertIn('compilação bloqueada', self.app.status.get())
        self.assertEqual(str(self.app.launch_button['state']), 'normal')
        self.assertEqual(str(self.app.launch_button['text']), 'GERAR PORT NATIVO')

    def test_cancel_worker_is_visible(self):
        def action():
            while True:
                self.app.cancel.check()
                self.app.cancel.event.wait(.01)
        self.app.start(action, 'Cancelamento de teste')
        self.assertEqual(str(self.app.cancel_button['state']), 'normal')
        self.app.cancel_button.invoke()
        self.wait_task()
        self.assertEqual(str(self.app.cancel_button['state']), 'disabled')
        self.assertIn('CANCELLED', self.app.status.get())
        self.assertEqual(self.app.task_tree.item('Cancelamento de teste')['values'][0], 'cancelled')

    def experimental_folder(self):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        from native_port.launcher import MODE_FILES
        for binary, report in MODE_FILES.values():
            binary_path = self.project / binary
            binary_path.parent.mkdir(parents=True, exist_ok=True)
            binary_path.write_bytes(b'synthetic executable')
            report_path = self.project / report
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text('{}')
        self.app.source.set(str(folder))
        self.app._refresh_engine_status()
        return folder

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_validates_in_worker_and_restores_play(self, validate, spawn):
        folder = self.experimental_folder()
        threads = []
        def validation(*args, **kwargs):
            threads.append(threading.current_thread())
            return subprocess.CompletedProcess(args[0], 0, stdout='Validado', stderr='')
        validate.side_effect = validation
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        self.app.play_experimental()
        self.wait_task()
        self.assertNotEqual(threads[0], threading.main_thread())
        self.assertEqual(validate.call_args.args[0][-1], '--dry-run')
        self.assertEqual(spawn.call_args.args[0][-1], str(folder))
        self.assertEqual(spawn.call_args.args[0][2:6], ['--shader-mode', 'async', '--vsync', 'on'])
        self.assertFalse(self.app.last_result['ready'])
        self.assertEqual(str(self.app.launch_button['state']), 'normal')
        self.assertEqual(str(self.app.compile_button['state']), 'normal')
        self.assertEqual(str(self.app.experimental_button['state']), 'normal')
        self.assertIsNone(self.app.experimental_process)

    @patch('native_port.launcher.messagebox.askyesno', return_value=True)
    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_60fps_forwards_flag_and_isolated_mode(self, validate, spawn, confirm):
        folder = self.experimental_folder()
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        self.app.play_experimental_60fps()
        self.wait_task()
        confirm.assert_called_once()
        command = spawn.call_args.args[0]
        self.assertEqual(command[2:6], ['--shader-mode', 'async', '--vsync', 'on'])
        self.assertIn('--fps-target', command)
        self.assertEqual(command[command.index('--fps-target') + 1], '60')
        self.assertEqual(command[-1], str(folder))
        self.assertIn('--fps-target', validate.call_args.args[0])
        self.assertEqual(validate.call_args.args[0][-1], '--dry-run')
        self.assertEqual(self.app.last_result['fps_target'], '60')
        self.assertIn('Sessão 60 fps encerrada', self.app.status.get())
        self.assertEqual(self.app.task_tree.item('Jogar 60 fps experimental')['values'][0], 'completed')

    @patch('native_port.launcher.messagebox.askyesno', return_value=False)
    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_60fps_warning_cancel_does_not_spawn(self, validate, spawn, confirm):
        self.experimental_folder()
        self.app.play_experimental_60fps()
        confirm.assert_called_once()
        validate.assert_not_called()
        spawn.assert_not_called()
        self.assertIn('cancelado', self.app.status.get())

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_forwards_selected_next_session_options(self, validate, spawn):
        self.experimental_folder()
        self.app.shader_mode.set('blocking')
        self.app.vsync.set(False)
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        self.app.play_experimental()
        self.wait_task()
        self.assertEqual(spawn.call_args.args[0][2:6], ['--shader-mode', 'blocking', '--vsync', 'off'])
        self.assertEqual(validate.call_args.args[0][:-1], spawn.call_args.args[0])
        self.assertEqual(str(self.app.shader_combo['state']), 'readonly')

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_validation_failure_does_not_spawn(self, validate, spawn):
        self.experimental_folder()
        validate.return_value = subprocess.CompletedProcess([], 2, stdout='', stderr='Hash divergente')
        self.app.play_experimental()
        self.wait_task()
        spawn.assert_not_called()
        self.assertIn('Hash divergente', self.app.status.get())

    @patch('native_port.launcher.subprocess.Popen', side_effect=OSError('Execução recusada'))
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_spawn_error_recovers_controls(self, validate, spawn):
        self.experimental_folder()
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        self.app.play_experimental()
        self.wait_task()
        self.assertIn('Execução recusada', self.app.status.get())
        self.assertEqual(str(self.app.experimental_button['state']), 'normal')
        self.assertIsNone(self.app.experimental_process)

    def test_graphics_controls_switch_preset_and_experimental_target(self):
        self.app.choose_preset('ultra')
        self.assertEqual(self.app.graphics_preset.get(), 'ultra')
        self.assertIn('3840x2160', self.app.graphics_summary.get())
        self.assertEqual(self.app.preset_buttons['ultra']['style'], 'PresetOn.TButton')
        self.app.choose_target('unlimited')
        self.root.update()
        self.assertEqual(self.app.fps_target.get(), 'unlimited')
        self.assertFalse(self.app.vsync.get())
        self.assertTrue(self.app.warning_frame.winfo_ismapped())
        self.assertIn('ILIMITADO', self.app.warning_text.get())
        self.assertEqual(self.app.target_buttons['unlimited']['style'], 'PresetOn.TButton')
        self.app.choose_target('30')
        self.root.update()
        self.assertTrue(self.app.vsync.get())
        self.assertFalse(self.app.warning_frame.winfo_ismapped())

    def test_play_command_forwards_selected_preset_without_custom_overrides(self):
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        command = self.app.play_command(folder)
        self.assertEqual(command[2:6], ['--shader-mode', 'async', '--vsync', 'on'])
        self.assertEqual(command[command.index('--fps-target') + 1], '30')
        self.assertEqual(command[command.index('--graphics-preset') + 1], 'high')
        self.assertNotIn('--render-scale', command)
        self.assertNotIn('--present-mode', command)

    def test_custom_graphics_command_forwards_every_override(self):
        folder = self.experimental_folder()
        self.app.choose_preset('custom')
        self.app.custom_render_scale.set(2)
        self.app.custom_msaa.set(False)
        self.app.custom_aniso.set('8x')
        self.app.custom_texture.set('Alta')
        self.app.custom_dither.set(True)
        command = self.app.play_command(folder)
        self.assertEqual(command[command.index('--render-scale') + 1], '2')
        self.assertNotIn('--msaa', command)
        self.assertEqual(str(self.app.msaa_check['state']), 'disabled')
        self.assertEqual(command[command.index('--anisotropic') + 1], '4')
        self.assertEqual(command[command.index('--texture-quality') + 1], 'high')
        self.assertEqual(command[command.index('--dither') + 1], 'on')

    def test_unlimited_command_forces_vsync_off_and_immediate_mode(self):
        folder = self.experimental_folder()
        self.app.choose_target('unlimited')
        command = self.app.play_command(folder)
        self.assertEqual(command[command.index('--fps-target') + 1], 'unlimited')
        self.assertEqual(command[command.index('--vsync') + 1], 'off')
        self.assertEqual(command[command.index('--present-mode') + 1], 'immediate')
        self.assertFalse((self.project / '.aster/runtime').exists())

    def test_save_writes_schema_two_preferences_only(self):
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        self.app.choose_target('60')
        with patch('native_port.launcher.messagebox.showerror') as showerror:
            self.assertTrue(self.app.save_settings())
        showerror.assert_not_called()
        path = self.project / '.aster/config/settings.json'
        data = json.loads(path.read_text())
        self.assertEqual(data['schema'], 2)
        self.assertEqual(data['source'], str(folder))
        self.assertEqual(data['graphics']['preset'], 'high')
        self.assertEqual(data['graphics']['fps_target'], '60')
        self.assertFalse((self.project / '.aster/runtime').exists())

    def test_play_missing_build_routes_to_generation_without_launching_game(self):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        self.app.source.set(str(folder))
        with patch.object(self.app, 'generate_native') as build, \
                patch('native_port.launcher.subprocess.run') as validate:
            self.app.play()
        validate.assert_not_called()
        build.assert_called_once()

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_close_during_validation_never_spawns_after_destroy(self, validate, spawn):
        self.experimental_folder()
        started, release = threading.Event(), threading.Event()
        def validation(*args, **kwargs):
            started.set()
            release.wait(2)
            return subprocess.CompletedProcess([], 0, stdout='', stderr='')
        validate.side_effect = validation
        self.app.play_experimental()
        self.assertTrue(started.wait(1))
        self.app.close()
        release.set()
        deadline = time.monotonic() + 2
        while self.app.queue.empty() and time.monotonic() < deadline:
            time.sleep(.01)
        spawn.assert_not_called()
        self.assertTrue(self.app.closed)

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_stop_only_terminates_own_experimental_child(self, validate, spawn):
        self.experimental_folder()
        started, stopped = threading.Event(), threading.Event()
        def wait(timeout=None):
            started.set()
            stopped.wait(2)
            return -15
        child = Mock(pid=123, wait=Mock(side_effect=wait), terminate=Mock(side_effect=stopped.set))
        spawn.return_value = child
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        self.app.play_experimental()
        self.assertTrue(started.wait(1))
        self.assertEqual(str(self.app.experimental_button['state']), 'disabled')
        self.app.play_experimental()
        self.assertEqual(spawn.call_count, 1)
        self.app.stop_experimental()
        self.wait_task()
        child.terminate.assert_called_once()
        self.assertIn('CANCELLED', self.app.status.get())

    @patch('native_port.launcher.threading.Thread')
    def test_close_sends_terminate_before_starting_non_daemon_cleanup(self, thread):
        child = Mock()
        child.wait.side_effect = [subprocess.TimeoutExpired('owned child', 3), -9]
        self.app.experimental_process = child
        def create_thread(*args, **kwargs):
            child.terminate.assert_called_once()
            self.assertFalse(kwargs['daemon'])
            cleanup = Mock()
            cleanup.start.side_effect = kwargs['target']
            return cleanup
        thread.side_effect = create_thread
        self.app.close()
        child.wait.assert_any_call(timeout=3)
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)
        self.assertTrue(self.app.closed)

    @patch('native_port.launcher.threading.Thread')
    def test_close_tolerates_child_already_gone(self, thread):
        child = Mock(terminate=Mock(side_effect=ProcessLookupError))
        self.app.experimental_process = child
        self.app.close()
        thread.assert_not_called()
        self.assertTrue(self.app.closed)

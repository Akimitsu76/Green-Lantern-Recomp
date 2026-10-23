#!/usr/bin/env python3
"""Bounded local ReXGlue startup probe; never certifies a playable port."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import re
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from native_port import graphics
from native_port.runtime_evidence import read_runtime_logs, summarize_runtime_log


SUPPORTED_XEX = "3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1"
CONTROL_KEYS = ('Return', 'space', 'BackSpace', 'Up', 'Down', 'Left', 'Right',
                'w', 'a', 's', 'd', 'q', 'e', 'l', 'p', '1', '3', 'f', 'k', 'Tab',
                'w+space', 'a+space', 's+space', 'd+space', 'q+l', 'e+l')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop_probe_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def capture_own_x11_window(pid: int, output: Path) -> dict:
    """Capture only a window whose _NET_WM_PID matches this probe's child."""
    try:
        result = subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"],
                                capture_output=True, text=True, timeout=2)
        if result.returncode:
            return {"error": result.stderr.strip() or "X11 property query failed"}
        window_ids = re.findall(r"0x[0-9a-fA-F]+", result.stdout)
        if not window_ids:
            # Bare X servers have no EWMH window manager/client list. Enumerate
            # root children, then still require this child's exact PID below.
            x11 = ctypes.CDLL("libX11.so.6")
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            x11.XDefaultRootWindow.restype = ctypes.c_ulong
            x11.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                      ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                                      ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
                                      ctypes.POINTER(ctypes.c_uint)]
            x11.XFree.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            display = x11.XOpenDisplay(None)
            if not display:
                return {"error": "Cannot open X11 display for selected-window lookup"}
            children = ctypes.POINTER(ctypes.c_ulong)()
            try:
                root_return, parent_return = ctypes.c_ulong(), ctypes.c_ulong()
                count = ctypes.c_uint()
                if x11.XQueryTree(display, x11.XDefaultRootWindow(display),
                                  ctypes.byref(root_return), ctypes.byref(parent_return),
                                  ctypes.byref(children), ctypes.byref(count)):
                    window_ids = [hex(children[i]) for i in range(min(count.value, 256))]
            finally:
                if children:
                    x11.XFree(children)
                x11.XCloseDisplay(display)
        for window_id in window_ids:
            prop = subprocess.run(["xprop", "-id", window_id, "_NET_WM_PID"],
                                  capture_output=True, text=True, timeout=2)
            match = re.search(r"=\s*(\d+)\s*$", prop.stdout)
            if not match or int(match.group(1)) != pid:
                continue
            image = subprocess.run(["import", "-silent", "-window", window_id, str(output)],
                                   capture_output=True, text=True, timeout=3)
            if image.returncode == 0 and output.is_file():
                return {"pid": pid, "window_id": window_id, "path": str(output)}
            # Screenshot tools can fail on Xwayland while the window is still
            # valid for keyboard input. Keep the verified window identity.
            return {"pid": pid, "window_id": window_id, "path": str(output),
                    "error": "Selected-window capture failed", "returncode": image.returncode}
        return {"error": "No X11 client window matched the child PID"}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_root", type=Path)
    parser.add_argument('--finish-human-session', metavar='LABEL',
                        help='Request graceful exit of the identified human session after the player authorizes it.')
    parser.add_argument("--seconds", type=int, default=30, choices=range(1, 901), metavar="1..900")
    parser.add_argument("--label", help="Unique local attempt name (letters, digits, hyphens).")
    parser.add_argument("--capture-window", action="store_true",
                        help="Capture this process's X11 window only, using xprop/ImageMagick.")
    parser.add_argument('--keyboard', action='store_true', help='Enable SDK keyboard controller mapping.')
    parser.add_argument('--human-session', action='store_true',
                        help='Observe a human-controlled session until the player closes the game; no automatic inputs.')
    parser.add_argument('--executable-dir', type=Path, help='Isolated local build directory under .aster/build.')
    parser.add_argument('--runtime-root', type=Path, help='Isolated profile/cache directory under .aster/runtime.')
    parser.add_argument('--vsync', choices=('on', 'off'))
    parser.add_argument('--shader-mode', choices=('async', 'blocking'), default='async')
    parser.add_argument('--fps-target', choices=graphics.TARGETS,
                        help='30 (default), 60 or unlimited. The latter two require an isolated hook build.')
    parser.add_argument('--experimental-unlimited-fps', action='store_true',
                        help='Legacy alias for --fps-target unlimited.')
    parser.add_argument('--graphics-preset', choices=graphics.PRESETS,
                        help='Apply a real graphics preset to this isolated probe.')
    parser.add_argument('--render-scale', type=int, choices=(1, 2, 3))
    parser.add_argument('--msaa', choices=('on', 'off'))
    parser.add_argument('--anisotropic', type=int, choices=tuple(graphics.ANISOTROPIC_LABELS))
    parser.add_argument('--texture-quality', choices=graphics.TEXTURE_QUALITIES)
    parser.add_argument('--dither', choices=('on', 'off'))
    parser.add_argument('--output-report', type=Path,
                        help='Write the reference report here instead of rexglue-runtime-probe.json.')
    parser.add_argument('--gpu-metrics', action='store_true', help='Sample read-only NVIDIA GPU telemetry every five seconds.')
    parser.add_argument('--primary-submit', choices=('on', 'off'), default='on',
                        help='Diagnostic: submit at each primary PM4 buffer end or batch until other required boundaries.')
    parser.add_argument('--gpu-timing', action='store_true',
                        help='Enable opt-in GPU submission timestamps in a diagnostic plugin.')
    parser.add_argument('--frame-diagnostics', action='store_true',
                        help='Observe original guest frame/present functions in a hook-enabled experimental host.')
    parser.add_argument('--experimental-60fps', action='store_true',
                        help='Legacy alias for --fps-target 60; simulation not validated.')
    parser.add_argument('--present-mode', choices=('auto', 'fifo', 'mailbox', 'immediate'), default='auto',
                        help='Diagnostic host swapchain mode; does not change guest vblank/VSync by itself.')
    parser.add_argument('--live-input', action='store_true',
                        help='Accept local, recorded control requests for this bounded probe.')
    parser.add_argument('--audio-check-at', type=float,
                        help='Measure only this process playback streams at the given elapsed seconds.')
    parser.add_argument('--allow-invalid-fetch', action='store_true',
                        help='Test SDK compatibility mode for invalid-type GPU fetch descriptors.')
    parser.add_argument('--presenter-compat', type=Path,
                        help='Load the pinned local presenter compatibility library for this child only.')
    parser.add_argument('--press', action='append', default=[], metavar='SECONDS:KEY[:HOLD]',
                        help='Send controller-mapped keys (Return, space, WASD, arrows) to this window only.')
    args = parser.parse_args()
    if args.experimental_60fps and args.experimental_unlimited_fps:
        parser.error('Choose either 60 fps or unlimited, not both.')
    if args.fps_target and (
            (args.experimental_60fps and args.fps_target != '60') or
            (args.experimental_unlimited_fps and args.fps_target != 'unlimited')):
        parser.error('FPS target conflicts with a legacy flag.')
    fps_target = args.fps_target or ('60' if args.experimental_60fps else
                                     'unlimited' if args.experimental_unlimited_fps else '30')
    if fps_target == 'unlimited':
        if args.vsync == 'on':
            parser.error('Unlimited requires --vsync off.')
        if args.present_mode in ('fifo', 'mailbox'):
            parser.error('Unlimited requires immediate presentation.')
        args.vsync, args.present_mode = 'off', 'immediate'
    elif args.vsync is None:
        args.vsync = 'on'
    if fps_target != 'unlimited' and args.vsync == 'off' and args.present_mode == 'auto':
        args.present_mode = 'immediate'
    if args.msaa == 'off':
        parser.error('FSI preserves guest MSAA; disabling it is unsupported.')
    args.frame_diagnostics = args.frame_diagnostics or fps_target != '30'
    if args.finish_human_session:
        root = Path(__file__).resolve().parent.parent
        label = args.finish_human_session
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', label):
            parser.error('Invalid session label.')
        attempt = root / '.aster/reports/rex-history' / label
        try:
            session = json.loads((attempt / 'session.json').read_text())
            if not session.get('human_session') or (attempt / 'report.json').exists():
                parser.error('Human session is not active.')
            pid = session['pid']
            proc = Path(f'/proc/{pid}')
            binary = root / '.aster/build/rex-green/aster_green_lantern'
            if proc.joinpath('exe').resolve(strict=True) != binary.resolve(strict=True):
                parser.error('Process executable does not match this game session.')
            if proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] != session['proc_start_ticks']:
                parser.error('Process identity changed.')
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(str(exc))
        print('Graceful exit requested for the identified game process.')
        return 0
    if args.human_session and (args.press or args.live_input or args.audio_check_at is not None):
        parser.error('--human-session does not accept automated input or audio recording.')
    actions = []
    for spec in args.press:
        try:
            parts = spec.split(':')
            assert len(parts) in (2, 3)
            at, key = parts[:2]
            hold = float(parts[2]) if len(parts) == 3 else 0.18
            at = float(at)
            assert 0 <= at < args.seconds and 0.01 <= hold <= 3 and at + hold < args.seconds and key in CONTROL_KEYS
        except (ValueError, AssertionError):
            parser.error('Invalid --press action.')
        actions.append((at, key, hold))
    if actions and not args.keyboard:
        parser.error('--press requires --keyboard.')
    if args.live_input and not args.keyboard:
        parser.error('--live-input requires --keyboard.')
    if args.audio_check_at is not None and not 0 <= args.audio_check_at < args.seconds - 35:
        parser.error('--audio-check-at must leave 35 seconds before the deadline.')
    actions.sort()
    root = Path(__file__).resolve().parent.parent
    if args.frame_diagnostics or fps_target != '30':
        if not args.executable_dir or not args.runtime_root:
            parser.error('Frame experiments require isolated executable and runtime directories.')
        if (args.executable_dir.resolve() == (root / '.aster/build/rex-green').resolve() or
                args.runtime_root.resolve() == (root / '.aster/runtime/green-lantern').resolve()):
            parser.error('Frame experiments cannot use the main executable or human profile.')
    game = args.game_root.resolve(strict=True)
    xex = game / "default.xex"
    before = sha256(xex)
    if before != SUPPORTED_XEX:
        parser.error("XEX hash differs from the image used for this build.")
    binary = root / ".aster/build/rex-green/aster_green_lantern"
    if args.executable_dir:
        directory = args.executable_dir.resolve(strict=True)
        if not any(directory.is_relative_to((root / allowed).resolve())
                   for allowed in ('.aster/build', '.aster/native')):
            parser.error('Experimental executable must be under .aster/build or .aster/native.')
        binary = directory / 'aster_green_lantern'
    if not binary.is_file():
        parser.error("Build the local ReXGlue host first.")
    # Check staging before attempting to create a window.
    libraries = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=True)
    if "not found" in libraries.stdout:
        parser.error("Missing shared libraries:\n" + libraries.stdout)
    run = root / ".aster/runtime/green-lantern"
    if args.runtime_root:
        run = args.runtime_root.resolve()
        if not run.is_relative_to((root / '.aster/runtime').resolve()):
            parser.error('Experimental runtime must be under .aster/runtime.')
    reports = root / ".aster/reports"
    reports.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    from play_green_lantern import lock_session
    try:
        session_lock = lock_session(run / 'play.lock')
    except BlockingIOError:
        parser.error('Já existe uma sessão do jogo ou um probe usando estes saves.')
    label = args.label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{os.getpid()}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", label):
        parser.error("Invalid attempt label.")
    attempt = reports / "rex-history" / label
    try:
        attempt.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("Attempt label already exists; evidence will not be overwritten.")
    env = os.environ.copy()
    if args.presenter_compat:
        compatibility = args.presenter_compat.resolve(strict=True)
        if not compatibility.is_relative_to((root / '.aster/build').resolve()) or compatibility.suffix != '.so':
            parser.error('Compatibility library must be a local .aster/build shared library.')
        env['LD_PRELOAD'] = str(compatibility)
    for key, name in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "xdg-cache"),
                      ("XDG_DATA_HOME", "data")):
        directory = run / name
        directory.mkdir(exist_ok=True)
        env[key] = str(directory)
    command = [str(binary), "--gpu_plugin=xenos", "--render_target_path_vulkan=fsi",
               f"--game_data_root={game}",
               f"--user_data_root={run / 'user'}", f"--cache_root={run / 'cache'}",
               f"--log_file={attempt / 'runtime.log'}", "--log_level=debug",
               "--allow_game_relative_writes=false"]
    command.extend(['--store_shaders=true', f'--async_shader_compilation={str(args.shader_mode == "async").lower()}',
                    f'--vsync={str(fps_target != "unlimited").lower()}'])
    command.append(f'--vulkan_submit_on_primary_buffer_end={str(args.primary_submit == "on").lower()}')
    if args.gpu_timing:
        command.append('--vulkan_submission_timing=true')
    if args.frame_diagnostics:
        command.append('--aster_frame_diagnostics=true')
    if fps_target == '60':
        command.append('--aster_experimental_60fps=true')
    elif fps_target == 'unlimited':
        command.append('--aster_experimental_unlimited_fps=true')
    graphics_data = None
    if (args.graphics_preset or args.render_scale is not None or args.msaa is not None or
            args.anisotropic is not None or args.texture_quality is not None or args.dither is not None):
        try:
            graphics_data = graphics.from_options(
                args.graphics_preset or 'default',
                render_scale=args.render_scale,
                msaa_2x=None if args.msaa is None else args.msaa == 'on',
                anisotropic=args.anisotropic,
                texture_quality=args.texture_quality,
                present_dither=None if args.dither is None else args.dither == 'on',
                fps_target=fps_target, vsync=args.vsync == 'on', shader_mode=args.shader_mode)
        except Exception as exc:
            parser.error(str(exc))
        command.extend(graphics.cvar_arguments(graphics_data))
    if args.present_mode != 'auto':
        command.extend([
            f'--vulkan_allow_present_mode_immediate={str(args.present_mode == "immediate").lower()}',
            f'--vulkan_allow_present_mode_mailbox={str(args.present_mode == "mailbox").lower()}',
            '--vulkan_allow_present_mode_fifo_relaxed=false'])
    if args.keyboard:
        command.append('--mnk_mode=true')
    if args.allow_invalid_fetch:
        command.append('--gpu_allow_invalid_fetch_constants=true')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    start = time.monotonic()
    timed_out = False
    interrupted = False
    operator_stop = False
    captures = []
    next_capture = 0.8
    next_status = 0.0
    capture_total = 0
    input_results = []
    control_offset = 0
    audio_check = None
    gpu_metrics = []
    next_gpu_sample = 0.0
    stdout = attempt / "stdout.log"
    with stdout.open("w") as log:
        process = subprocess.Popen(command, cwd=run, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            (attempt / 'session.json').write_text(json.dumps({
                'pid': process.pid, 'executable': str(binary),
                'proc_start_ticks': Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19],
                'command': command, 'attempt': label,
                'live_input': args.live_input,
                'human_session': args.human_session,
            }, indent=2) + '\n')
            deadline = None if args.human_session else start + args.seconds
            print(f'Sessão {label} aberta. PID {process.pid}. ' +
                  ('Você controla o jogo; feche a janela para concluir a coleta.' if args.human_session else
                   f'Limite: {args.seconds} segundos.'), flush=True)
            while process.poll() is None:
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    raise subprocess.TimeoutExpired(command, args.seconds)
                if args.gpu_metrics and now - start >= next_gpu_sample:
                    try:
                        sample = subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,power.draw,clocks.current.graphics,memory.used',
                                                 '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
                        gpu_metrics.append({'elapsed_seconds': round(now - start, 2), 'returncode': sample.returncode,
                                            'csv': sample.stdout.strip(), 'error': sample.stderr.strip()})
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        gpu_metrics.append({'elapsed_seconds': round(now - start, 2), 'error': str(exc)})
                    next_gpu_sample = time.monotonic() - start + 5
                    now = time.monotonic()
                if args.human_session and now - start >= next_status:
                    status = {'attempt': label, 'pid': process.pid, 'state': 'running',
                              'elapsed_seconds': round(now - start, 2), 'human_session': True,
                              'automatic_input': False, 'capture_total': capture_total,
                              'last_capture': captures[-1] if captures else None}
                    temp_status = attempt / 'status.tmp'
                    temp_status.write_text(json.dumps(status, indent=2) + '\n')
                    temp_status.replace(attempt / 'status.json')
                    next_status = now - start + 5
                if args.audio_check_at is not None and audio_check is None and now - start >= args.audio_check_at:
                    try:
                        check = subprocess.run([sys.executable, str(root / 'scripts/probe_game_audio.py'), label],
                                               capture_output=True, text=True, timeout=35)
                        audio_check = {'returncode': check.returncode, 'stdout': check.stdout, 'stderr': check.stderr}
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        audio_check = {'error': str(exc)}
                    now = time.monotonic()
                queue = attempt / 'control.jsonl'
                if args.live_input and queue.exists():
                    with queue.open() as requests:
                        requests.seek(control_offset)
                        line = requests.readline(4096)
                        if line.endswith('\n'):
                            control_offset = requests.tell()
                        else:
                            line = ''
                    if line:
                        result = {'elapsed_seconds': round(now - start, 2)}
                        try:
                            request = json.loads(line)
                            result['request'] = request
                            if request.get('stop') is True:
                                operator_stop = True
                            else:
                                key = request.get('key')
                                hold = float(request.get('hold', 0.18))
                                if key is not None and (key not in CONTROL_KEYS or not 0.01 <= hold <= 3):
                                    raise ValueError('Invalid control key or hold.')
                                lookup = capture_own_x11_window(process.pid, attempt / f'live-{control_offset}.png')
                                result['capture'] = lookup
                                if key is not None:
                                    if 'window_id' not in lookup:
                                        raise ValueError('Probe window unavailable.')
                                    from rex_x11_input import send_window_key
                                    result['input'] = send_window_key(process.pid, lookup['window_id'], key, hold)
                        except (ValueError, TypeError, AttributeError) as exc:
                            result['error'] = str(exc)
                        with (attempt / 'live-results.jsonl').open('a') as results:
                            results.write(json.dumps(result) + '\n')
                        if operator_stop:
                            break
                while actions and now - start >= actions[0][0]:
                    at, key, hold = actions.pop(0)
                    lookup = capture_own_x11_window(process.pid, attempt / f'input-before-{len(input_results)}.png')
                    if 'window_id' in lookup and process.poll() is None:
                        from rex_x11_input import send_window_key
                        result = send_window_key(process.pid, lookup['window_id'], key, hold)
                    else:
                        result = {'key': key, 'error': 'Probe window unavailable'}
                    input_results.append({'scheduled_seconds': at, **result})
                    next_capture = min(next_capture, now - start + 0.5)
                if args.capture_window and now - start >= next_capture:
                    capture_total += 1
                    captures.append(capture_own_x11_window(
                        process.pid, attempt / f"window-{capture_total}.png"))
                    if args.human_session and len(captures) > 120:
                        previous = captures.pop(0)
                        if previous.get('path'):
                            Path(previous['path']).unlink(missing_ok=True)
                    next_capture = now - start + (15 if args.human_session else 2 if next_capture < 5 else 5)
                try:
                    process.wait(timeout=0.2 if deadline is None else min(0.2, max(0.01, deadline - time.monotonic())))
                except subprocess.TimeoutExpired:
                    continue
        except subprocess.TimeoutExpired:
            timed_out = True
        except KeyboardInterrupt:
            interrupted = True
        finally:
            stop_probe_process(process)
    after = sha256(xex)
    runtime_log = attempt / "runtime.log"
    log_text, log_files = read_runtime_logs(attempt)
    plugin_match = re.search(r"GPU plugin 'xenos' loaded \(([^)]+)\)", log_text)
    loaded_plugin = binary.parent / plugin_match.group(1) if plugin_match else None
    report = {**summarize_runtime_log(log_text), "command": command, "exit_code": process.returncode,
              "timeout": timed_out, "elapsed_seconds": round(time.monotonic() - start, 2),
              "xex_sha256_before": before, "xex_sha256_after": after,
              "executable_sha256": sha256(binary), "stdout_log": str(stdout),
              "runtime_log": str(runtime_log), "attempt": label,
              "window_captures": captures,
              "input_actions": input_results,
              "human_session": args.human_session,
              "capture_total": capture_total,
              "gpu_metrics_global": gpu_metrics,
              "gpu_plugin_path": str(loaded_plugin) if loaded_plugin else None,
              "gpu_plugin_sha256": sha256(loaded_plugin) if loaded_plugin and loaded_plugin.exists() else None,
              "runtime_root": str(run),
              "fps_target": fps_target,
              "graphics": graphics_data,
              "audio_check": audio_check,
              "live_results": str(attempt / 'live-results.jsonl') if args.live_input else None,
              "retained_log_files": log_files,
              "stop_reason": "operator_stop" if operator_stop else "interrupted" if interrupted else "probe_deadline" if timed_out else "process_exit"}
    encoded = json.dumps(report, indent=2) + "\n"
    (attempt / "report.json").write_text(encoded)
    if args.human_session:
        (attempt / 'status.json').write_text(json.dumps({
            'attempt': label, 'pid': process.pid, 'state': 'ended',
            'exit_code': process.returncode, 'report': str(attempt / 'report.json'),
            'human_session': True, 'elapsed_seconds': report['elapsed_seconds'],
        }, indent=2) + '\n')
        (reports / 'human-session-latest.json').write_text(encoded)
        print(encoded)
        os.close(session_lock)
        if after != before:
            raise RuntimeError('Original XEX changed during the session.')
        return 0 if process.returncode == 0 and not interrupted else 1
    default_report = reports / "rexglue-runtime-probe.json"
    if args.output_report:
        output_report = args.output_report.expanduser().resolve()
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(encoded)
    else:
        output_report = default_report
        output_report.write_text(encoded)
    if output_report == default_report:
        shutil.copyfile(stdout, reports / "rexglue-runtime-stdout.log")
        if runtime_log.exists():
            (reports / "rexglue-runtime.log").write_text(log_text, errors="replace")
    print(json.dumps(report, indent=2))
    print(stdout.read_text(errors="replace")[-9000:])
    if after != before:
        raise RuntimeError("Original XEX changed during the probe.")
    os.close(session_lock)
    return 0 if process.returncode == 0 and not timed_out and not interrupted else 1


if __name__ == "__main__":
    raise SystemExit(main())

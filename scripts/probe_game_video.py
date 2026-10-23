#!/usr/bin/env python3
"""Record one opted-in game probe window and a repeatable short input sequence."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from probe_rex_runtime import capture_own_x11_window
from rex_x11_input import send_window_key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    history = root / '.aster/reports/rex-history'
    attempt = history / args.attempt
    if attempt.resolve().parent != history.resolve():
        parser.error('Invalid attempt label.')
    session = json.loads((attempt / 'session.json').read_text())
    if not session.get('live_input') or session.get('human_session'):
        parser.error('Requires an automated probe with live input explicitly enabled.')
    def check_identity():
        if (attempt / 'report.json').exists():
            raise ValueError('Probe ended.')
        proc = Path('/proc') / str(session['pid'])
        if (proc / 'exe').resolve(strict=True) != Path(session['executable']).resolve(strict=True):
            raise ValueError('Executable changed.')
        if (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19] != session['proc_start_ticks']:
            raise ValueError('Process identity changed.')
    check_identity()
    video = attempt / 'validation-clip.mkv'
    if video.exists():
        parser.error('Clip already exists; preserving evidence.')
    lookup = capture_own_x11_window(session['pid'], attempt / 'validation-before.png')
    if 'window_id' not in lookup:
        parser.error(str(lookup))
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'warning',
               '-f', 'x11grab', '-window_id', str(int(lookup['window_id'], 16)),
               '-draw_mouse', '0', '-framerate', '60', '-i', os.environ['DISPLAY'],
               '-t', '24', '-an', '-vf', 'scale=960:540', '-c:v', 'libx264',
               '-preset', 'ultrafast', '-crf', '18', str(video)]
    result = {'session': session, 'capture_scope': 'pid_verified_game_window_only_no_audio',
              'window': lookup, 'command': command, 'actions': [],
              'start_utc': datetime.now(timezone.utc).isoformat()}
    start = time.monotonic()
    with (attempt / 'validation-video.log').open('w') as log:
        recorder = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            for at, key, hold in [(3, 'w', 1), (6, 's', 1), (10, 'l', .1), (17, 'p', .1)]:
                while time.monotonic() - start < at:
                    if recorder.poll() is not None:
                        raise ValueError('Recorder ended before sequence completed.')
                    time.sleep(.02)
                check_identity()
                action = {'at': time.monotonic() - start, 'key': key, 'hold': hold}
                action['input'] = send_window_key(session['pid'], lookup['window_id'], key, hold)
                action['end'] = time.monotonic() - start
                result['actions'].append(action)
            result['returncode'] = recorder.wait(timeout=20)
            result['elapsed_seconds'] = time.monotonic() - start
        finally:
            if recorder.poll() is None:
                recorder.terminate()
                recorder.wait(timeout=5)
            (attempt / 'validation-clip.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'video': str(video), 'returncode': result.get('returncode'),
                      'actions': result['actions']}, indent=2))


if __name__ == '__main__':
    main()

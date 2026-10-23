#!/usr/bin/env python3
"""Measure only the active game's PulseAudio playback streams; never a microphone or mixed sink."""
import argparse
import array
import json
import math
from pathlib import Path
import signal
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    history = root / '.aster/reports/rex-history'
    attempt = history / args.attempt
    if attempt.resolve().parent != history.resolve():
        parser.error('Invalid attempt label.')
    try:
        if (attempt / 'report.json').exists():
            raise ValueError('Probe already ended.')
        session = json.loads((attempt / 'session.json').read_text())
        pid = session['pid']
        proc = Path(f'/proc/{pid}')
        if proc.joinpath('exe').resolve(strict=True) != Path(session['executable']).resolve(strict=True):
            raise ValueError('Process executable changed.')
        if proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19] != session['proc_start_ticks']:
            raise ValueError('Process identity changed.')
        inventory = json.loads(subprocess.check_output(['pactl', '-f', 'json', 'list', 'sink-inputs'], text=True, timeout=5))
        streams = [s for s in inventory if str(s.get('properties', {}).get('application.process.id')) == str(pid)]
        nodes = json.loads(subprocess.check_output(['pw-dump'], text=True, timeout=5))
        game_nodes = []
        candidates = []
        for node in nodes:
            props = node.get('info', {}).get('props', {})
            if props.get('media.class') != 'Stream/Output/Audio':
                continue
            if str(props.get('application.process.id')) == str(pid):
                game_nodes.append({'index': props['object.serial'], 'properties': props, 'native_pipewire': True})
            candidates.append({k: props.get(k) for k in ('application.name', 'application.process.id',
                                                       'application.process.binary', 'node.name', 'object.serial')})
        if not streams:
            streams = game_nodes
        result = {'game_pid': pid, 'capture_scope': 'individual_game_sink_inputs_only', 'streams': [],
                  'audible_quality_verified': False, 'playback_candidates_metadata': candidates}
        for s in streams[:4]:
            index = int(s['index'])
            path = attempt / f'audio-stream-{index}.s16le'
            with path.open('wb') as raw:
                command = (['pw-record', '--target', str(index), '--properties',
                            '{ stream.capture.sink = true node.dont-reconnect = true }',
                            '--raw', '--format=s16', '--rate=48000', '--channels=2', '-']
                           if s.get('native_pipewire') else
                           ['parec', f'--monitor-stream={index}', '--raw', '--format=s16le',
                            '--rate=48000', '--channels=2'])
                record = subprocess.Popen(command, stdout=raw, stderr=subprocess.PIPE)
                try:
                    record.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    record.send_signal(signal.SIGINT)
                    try:
                        record.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        record.kill()
                        record.wait()
                finally:
                    if record.poll() is None:
                        record.kill()
                        record.wait()
                error = record.stderr.read().decode(errors='replace')
            data = path.read_bytes()
            values = array.array('h')
            values.frombytes(data[:len(data) // 2 * 2])
            if sys.byteorder != 'little':
                values.byteswap()
            peak = max((abs(v) for v in values), default=0)
            rms = math.sqrt(sum(v*v for v in values) / len(values)) if values else 0
            result['streams'].append({'index': index, 'properties': s.get('properties', {}),
                                      'muted': s.get('mute'), 'corked': s.get('corked'),
                                      'sample_count': len(values), 'peak_s16': peak, 'rms_s16': round(rms, 3),
                                      'signal_nonzero': peak > 0, 'raw_path': str(path), 'recorder_stderr': error})
        (attempt / 'audio-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

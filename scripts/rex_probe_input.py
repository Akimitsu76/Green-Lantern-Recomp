#!/usr/bin/env python3
"""Queue recorded input or a capture for one explicitly enabled local probe."""
import argparse
import fcntl
import json
from pathlib import Path

from probe_rex_runtime import CONTROL_KEYS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('attempt', help='Label do probe ativo com --live-input.')
    parser.add_argument('--key', choices=CONTROL_KEYS)
    parser.add_argument('--hold', type=float, default=0.18)
    parser.add_argument('--repeat', type=int, default=1, choices=range(1, 21))
    parser.add_argument('--stop', action='store_true', help='Encerra o probe e preserva seu relatório.')
    args = parser.parse_args()
    if not 0.01 <= args.hold <= 3:
        parser.error('--hold deve estar entre 0.01 e 3 segundos.')
    if args.stop and (args.key or args.repeat != 1):
        parser.error('--stop não pode ser combinado com teclas/repetições.')
    root = Path(__file__).resolve().parent.parent
    history = root / '.aster/reports/rex-history'
    attempt = history / args.attempt
    if attempt.parent.resolve() != history.resolve() or attempt.resolve().parent != history.resolve():
        parser.error('Label inválido.')
    try:
        if (attempt / 'report.json').exists():
            raise ValueError('Este probe já terminou.')
        session = json.loads((attempt / 'session.json').read_text())
        if not isinstance(session, dict) or not session.get('live_input'):
            raise ValueError('Este probe não habilitou --live-input.')
        request = {'stop': True} if args.stop else {'key': args.key, 'hold': args.hold}
        with (attempt / 'control.jsonl').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            for _ in range(args.repeat):
                stream.write(json.dumps(request) + '\n')
        print('Solicitação enfileirada; confira live-results.jsonl para execução e captura.')
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

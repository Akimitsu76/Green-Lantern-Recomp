import argparse
import json
from pathlib import Path
import sys
from games.green_lantern import GreenLantern
from .diagnostics import diagnostics
from .errors import PortError
from .native_build import build_native
from .paths import project_root
from .pipeline import prepare
from .sources import inspect_source
from .workspace import Workspace

PROJECT = project_root(__file__)


def main():
    parser = argparse.ArgumentParser(description='Aster Native — framework experimental de portabilidade')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('gui')
    for name in ('inspect', 'prepare'):
        p = sub.add_parser(name)
        p.add_argument('source')
        if name == 'prepare':
            p.add_argument('--workspace', type=Path, default=PROJECT / '.aster')
    builder = sub.add_parser('build', help='Gerar e compilar o port a partir do dump local')
    builder.add_argument('source')
    builder.add_argument('--jobs', type=int, default=2)
    builder.add_argument('--download-sdk', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'gui':
            from .launcher import main as launch
            launch()
            return 0
        if args.command == 'doctor':
            result = diagnostics()
        elif args.command == 'build':
            result = build_native(args.source, Workspace(PROJECT / '.aster', PROJECT),
                                  jobs=args.jobs, allow_download=args.download_sdk,
                                  emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
        elif args.command == 'inspect':
            result = inspect_source(args.source)
        else:
            result = prepare(args.source, Workspace(args.workspace, PROJECT), GreenLantern(),
                             emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 3 if result.get('state') == 'blocked' else 0
    except PortError as e:
        print(json.dumps({'error': e.as_dict(), 'ready': False}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())

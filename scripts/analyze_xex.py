"""Explicit local decoding and optional isolated native-function experiment."""
import argparse
import json
from pathlib import Path
import sys
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from native_port.errors import PortError
from native_port.workspace import Workspace
from native_port.xenon import analyze
from games.green_lantern import GreenLantern

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source')
    p.add_argument('--allow-decode',action='store_true',help='Explicitly permit local XEX decoding')
    p.add_argument('--probe',action='store_true',help='Run the bounded function experiment, not the game')
    args=p.parse_args()
    try:
        r=analyze(args.source,Workspace(PROJECT/'.aster',PROJECT),args.allow_decode,args.probe,
                  emit=lambda e: print(json.dumps(e,ensure_ascii=False),file=sys.stderr),game=GreenLantern())
        print(json.dumps({k:v for k,v in r.items() if k not in ('logs','pe')},indent=2,ensure_ascii=False))
    except PortError as e:
        print(json.dumps(e.as_dict(),ensure_ascii=False),file=sys.stderr)
        raise SystemExit(2)

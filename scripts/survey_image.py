"""Explicit, streaming, read-only image survey; no extraction or decryption."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from native_port.errors import PortError
from native_port.sources import MAGIC, source_path
from native_port.workspace import Workspace


def survey(path):
    source = source_path(path)
    needles = (MAGIC, b'XEX2', b'CD001')
    counts = {n.decode(): 0 for n in needles}
    offsets = {n.decode(): [] for n in needles}
    h, carry, total = hashlib.sha256(), b'', 0
    t = time.monotonic()
    with source.open('rb') as f:
        before = os.fstat(f.fileno())
        while chunk := f.read(8*1024*1024):
            h.update(chunk)
            data = carry + chunk
            start = total - len(carry)
            for needle in needles:
                at = 0
                while (at := data.find(needle, at)) >= 0:
                    absolute = start + at
                    # Count only matches that could not fit in the previous block.
                    if absolute + len(needle) > total:
                        counts[needle.decode()] += 1
                        if len(offsets[needle.decode()]) < 32:
                            offsets[needle.decode()].append(absolute)
                    at += 1
            total += len(chunk)
            carry = data[-(len(MAGIC)-1):]
        after = os.fstat(f.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise PortError('SOURCE_CHANGED', 'Fonte mudou durante a leitura.')
        candidates = []
        for off in offsets['XEX2']:
            f.seek(off)
            raw = f.read(24)
            if len(raw) == 24:
                _, flags, payload, reserved, security, count = struct.unpack('>4s5I', raw)
                plausible = count <= 4096 and 24 + count*8 <= security < payload < total-off
                candidates.append({'offset': off, 'plausible_header': plausible,
                                   'optional_header_count': count, 'payload_offset': payload,
                                   'security_offset': security})
    return {'schema': 1, 'source': str(source), 'size': total, 'mtime_ns': before.st_mtime_ns,
            'sha256': h.hexdigest(), 'signature_counts': counts, 'signature_offsets': offsets,
            'xex_candidates': candidates, 'seconds': time.monotonic()-t,
            'read_only': True, 'extracted': False, 'ready': False,
            'note': 'Assinaturas e plausibilidade não demonstram identidade nem integridade do jogo.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    args = parser.parse_args()
    result = survey(args.source)
    work = Workspace(PROJECT / '.aster', PROJECT)
    p = work.write_json('reports/image-survey.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f'Relatório local: {p}', file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130)
    except PortError as e:
        print(json.dumps(e.as_dict(), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)

#!/usr/bin/env python3
"""Inspeciona alvos guest no PE normalizado e guarda evidencia reproduzivel.

Ferramenta de analise estatica: le o PE normalizado (mesmo hash dos hints),
decodifica a tabela ``.pdata``, delimita vaos sem entrada de funcao e
confere cada alvo por desassemblagem. Nao executa codigo do jogo.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from native_port.errors import PortError
from native_port.guest import (DEFAULT_CODE_RANGE, GuestImage, analyze_gap,
                               classify_gap, find_constructed_pointers,
                               find_unregistered_data_targets, propose_hints)
from native_port.workspace import Workspace

PE_RELATIVE = 'analysis/green-lantern/normalized.pe'
TARGETS_RELATIVE = 'analysis/green-lantern/runtime-targets'


def _parse_address(value: str) -> tuple[int, int | None]:
    """Aceita ``0xADDR`` ou ``0xADDR:0xEND`` (fim exclusivo)."""
    if ':' in value:
        left, right = value.split(':', 1)
        return int(left, 0), int(right, 0)
    return int(value, 0), None


def _gap_report(image: GuestImage, start: int, end: int, code_range) -> dict:
    report = analyze_gap(image, start, end)
    report['classification'] = classify_gap(report)
    report['in_code_range'] = code_range[0] <= start < code_range[1]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pe', type=Path, default=None,
                        help='PE normalizado (padrao: .aster/analysis/green-lantern/normalized.pe)')
    parser.add_argument('--address', type=_parse_address, action='append', default=[],
                        metavar='ADDR[:END]',
                        help='Endereco guest alvo, com fim opcional (repetivel)')
    parser.add_argument('--end', type=lambda value: int(value, 0), default=None,
                        help='Fim exclusivo do alvo (padrao: proxima entrada do .pdata)')
    parser.add_argument('--gaps', action='store_true',
                        help='Lista os vaos do .pdata na faixa de codigo')
    parser.add_argument('--min-gap', type=int, default=8,
                        help='Tamanho minimo do vao para ser listado (padrao: 8)')
    parser.add_argument('--limit', type=int, default=20,
                        help='Maximo de vaos listados no relatorio')
    parser.add_argument('--constructed', action='store_true',
                        help='Procura enderecos montados por lis/addi em runtime')
    parser.add_argument('--constructed-gaps-only', action='store_true',
                        help='No relatorio de construidos, destaca alvos dentro de vaos')
    parser.add_argument('--data-refs', action='store_true',
                        help='Lista enderecos de codigo sem entrada .pdata apontados por dados')
    parser.add_argument('--batch-hints', type=int, default=0, metavar='N',
                        help='Gera ate N hints aceitos e grava um trecho TOML')
    parser.add_argument('--batch-out', type=Path, default=None,
                        help='Arquivo TOML de saida para os hints gerados')
    parser.add_argument('--json-out', type=Path, default=None,
                        help='Caminho alternativo para o relatorio (relativo a .aster)')
    parser.add_argument('--no-write', action='store_true',
                        help='Nao grava o relatorio em disco')
    args = parser.parse_args()

    workspace = Workspace(PROJECT / '.aster', PROJECT)
    pe_path = args.pe if args.pe else workspace.path(PE_RELATIVE)
    try:
        image = GuestImage.from_file(pe_path)
    except (OSError, PortError) as exc:
        print(f'falha: {exc}', file=sys.stderr)
        return 2

    digest = hashlib.sha256(pe_path.read_bytes()).hexdigest()
    code_range = DEFAULT_CODE_RANGE
    lo, hi = image.code_range()
    if not (code_range[0] <= lo and hi <= code_range[1]):
        code_range = (lo, hi)

    entries = image.pdata_entries()
    gaps = image.pdata_gaps(*code_range)
    big_gaps = [(a, b) for a, b in gaps if b - a >= args.min_gap]

    report: dict = {
        'pe_sha256': digest,
        'pe_path': str(pe_path),
        'code_range': [code_range[0], code_range[1]],
        'pdata_entries': len(entries),
        'pdata_gaps': len(gaps),
        'gaps_over_min': len(big_gaps),
        'gaps_over_min_bytes': sum(b - a for a, b in big_gaps),
    }

    if args.gaps:
        report['gaps'] = [
            {'start': a, 'end': b, 'size': b - a,
             'classification': classify_gap(analyze_gap(image, a, b))}
            for a, b in big_gaps[:args.limit]
        ]

    if args.constructed:
        constructed = find_constructed_pointers(image, *code_range)
        rows = []
        for item in constructed:
            row = dict(item)
            row['in_gap'] = any(a <= item['target'] < b for a, b in gaps)
            rows.append(row)
        if args.constructed_gaps_only:
            rows = [r for r in rows if r['in_gap']]
        report['constructed_pointers'] = rows[:max(args.limit, 50)]
        report['constructed_pointers_total'] = len(constructed)
        report['constructed_pointers_in_gaps'] = sum(1 for r in rows if r['in_gap'])

    if args.data_refs:
        data_targets = find_unregistered_data_targets(image, *code_range)
        report['unregistered_data_targets'] = data_targets[:args.limit]
        report['unregistered_data_targets_total'] = len(data_targets)

    if args.batch_hints:
        candidates = find_unregistered_data_targets(image, *code_range)
        proposals = propose_hints(image, *code_range, candidates)
        accepted = [p for p in proposals if p.get('accepted')]
        accepted.sort(key=lambda p: (-p['ref_count'], p['address']))
        selected = accepted[:args.batch_hints]
        report['batch_proposals_total'] = len(proposals)
        report['batch_proposals_accepted'] = len(accepted)
        report['batch_selected'] = len(selected)
        report['batch'] = [
            {'address': p['address'], 'size': p['size'], 'ref_count': p['ref_count'],
             'terminator': p.get('terminator'),
             'references': [r['address'] for r in p['references'][:4]]}
            for p in selected]
        if args.batch_out and not args.no_write:
            lines = ['# Gerado por scripts/inspect_guest_target.py --batch-hints',
                     f'# PE SHA-256: {digest}',
                     f'# Candidatos aceitos: {len(accepted)} de {len(proposals)}',
                     '']
            for p in selected:
                lines.append(f'"0x{p["address"]:08X}" = {{ size = 0x{p["size"]:02X} }}')
            out_path = Path(args.batch_out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            print(f'hints gerados: {out_path}')

    targets = []
    for address, explicit_end in args.address:
        entry = image.pdata_covering(address)
        end = explicit_end if explicit_end is not None else args.end
        if end is None:
            if entry is not None:
                end = entry.end
            else:
                end = next((b for a, b in gaps if a <= address < b), address + 0x100)
        target = _gap_report(image, address, end, code_range)
        target['pdata_entry'] = (
            {'begin': entry.begin, 'data': entry.data, 'size': entry.size,
             'prolog_length': entry.prolog_length,
             'thirty_two_bit': entry.thirty_two_bit,
             'exception_flag': entry.exception_flag} if entry else None)
        target['address'] = address
        targets.append(target)

    if targets:
        report['targets'] = targets

    if not args.no_write:
        if args.json_out:
            out = workspace.write_json(str(args.json_out), report)
        elif targets:
            for target in targets:
                name = f'{target["address"]:08x}.json'
                out = workspace.write_json(f'{TARGETS_RELATIVE}/{name}', target)
        else:
            out = workspace.write_json('analysis/green-lantern/guest-analysis.json', report)
        print(f'relatorio: {out}')

    summary = {k: v for k, v in report.items()
               if k not in ('gaps', 'constructed_pointers', 'targets',
                            'unregistered_data_targets')}
    print(json.dumps(summary, indent=2))
    for item in report.get('unregistered_data_targets', []):
        where = ', '.join(f"{ref['section']}@{ref['address']:#x}"
                          for ref in item['references'][:3])
        print(f"  {item['address']:#010x} refs={item['ref_count']}  {where}")
    for target in targets:
        print(f'\n== 0x{target["address"]:08X} ==')
        print(f'  extent      : 0x{target["start"]:08X}..0x{target["end"]:08X} '
              f'({target["size"]} bytes)')
        print(f'  class       : {target["classification"]}')
        print(f'  padding     : {target["trailing_padding"]} bytes no fim')
        print(f'  terminador  : {target["terminator"]}')
        print(f'  branches    : {target["branches"]}')
        print(f'  refs de dados: {target["data_pointer_references"]}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Mescla um lote de hints no arquivo de hints do ReXGlue.

O lote sai de ``scripts/inspect_guest_target.py --batch-hints`` e carrega
apenas extents aceitos pelos filtros de analise. Esta ferramenta valida o
lote contra o arquivo de hints ja existente antes de escrever:

* endereco repetido (o lote muda o extent de um hint validado a mao);
* extent sobreposto (duas funcoes nao podem ocupar os mesmos bytes);
* tamanho invalido (zero, nao multiplo de 4 ou acima do limite).

Nada e escrito quando a validacao falha. O arquivo original e lido apenas
para extrair os hints; o conteudo final preserva os comentarios existentes
e acrescenta um bloco descritivo para o lote.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_HINTS = Path('games/green_lantern_rex_hints.toml')


def load_functions(path: Path) -> dict[int, int]:
    """Extrai ``{endereco: tamanho}`` de um arquivo de hints do ReXGlue.

    O ReXGlue aceita duas notacoes: ``size = 0xNN`` (tamanho) e
    ``end = 0xADDR`` (fim exclusivo). Ambas viram tamanho aqui.
    """
    with path.open('rb') as handle:
        data = tomllib.load(handle)
    # O arquivo de hints usa a tabela [functions]; os lotes gerados sao um
    # trecho solto de chaves, sem cabecalho de tabela.
    functions = data.get('functions', data)
    result: dict[int, int] = {}
    for key, value in functions.items():
        address = int(key, 0)
        if isinstance(value, dict):
            if 'size' in value:
                size = int(value['size'])
            else:
                size = int(value['end']) - address
        else:
            size = int(value)
        result[address] = size
    return result


def validate(existing: dict[int, int], batch: dict[int, int]) -> tuple[list[str], dict[int, int]]:
    """Valida o lote e devolve ``(problemas, entradas_novas)``.

    Uma entrada ja presente com o mesmo tamanho e reentrada: o lote e
    reaplicado sem mudanca e ela e descartada da mesclagem. Entrada ja
    presente com tamanho diferente e conflito.
    """
    problems: list[str] = []
    fresh: dict[int, int] = {}
    for address, size in sorted(batch.items()):
        if size <= 0 or size % 4 or size > 0x10000:
            problems.append(f'{address:#010x}: tamanho invalido ({size})')
        if address % 4:
            problems.append(f'{address:#010x}: endereco nao alinhado a 4 bytes')
        if address in existing:
            if existing[address] != size:
                problems.append(f'{address:#010x}: ja existe com tamanho '
                                f'{existing[address]:#x}, lote pede {size:#x}')
            continue
        fresh[address] = size
    combined = dict(existing)
    combined.update(fresh)
    ordered = sorted(combined.items())
    for (address_a, size_a), (address_b, _) in zip(ordered, ordered[1:]):
        if address_a + size_a > address_b:
            problems.append(f'{address_a:#010x}: extent de {size_a:#x} bytes '
                            f'invade {address_b:#010x}')
    return problems, fresh


def format_entries(batch: dict[int, int]) -> list[str]:
    return [f'"0x{address:08X}" = {{ size = 0x{size:02X} }}'
            for address, size in sorted(batch.items())]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hints', type=Path, default=DEFAULT_HINTS,
                        help=f'Arquivo de hints (padrao: {DEFAULT_HINTS})')
    parser.add_argument('--batch', type=Path, required=True,
                        help='Lote TOML gerado por inspect_guest_target.py')
    parser.add_argument('--note', default='',
                        help='Comentario de origem gravado no bloco do lote')
    parser.add_argument('--out', type=Path, default=None,
                        help='Grava em outro arquivo em vez de atualizar o original')
    parser.add_argument('--check', action='store_true',
                        help='So valida: nao escreve nada')
    args = parser.parse_args()

    hints_path = args.hints if args.hints.is_absolute() else PROJECT / args.hints
    batch_path = args.batch if args.batch.is_absolute() else PROJECT / args.batch
    for path in (hints_path, batch_path):
        if not path.exists():
            print(f'falha: arquivo ausente: {path}', file=sys.stderr)
            return 2

    # Bind automatically generated hints to the image being configured.
    import re
    import hashlib
    batch_text = batch_path.read_text()
    identity = re.search(r'PE SHA-256:\s*([0-9a-fA-F]{64})', batch_text)
    hints_text = hints_path.read_text()
    expected = re.search(r'Normalized PE SHA-256:\s*([0-9a-fA-F]{64})', hints_text)
    pe = PROJECT / '.aster/analysis/green-lantern/normalized.pe'
    if not identity or not expected or identity[1].lower() != expected[1].lower():
        print('falha: hash PE do lote ausente ou divergente dos hints', file=sys.stderr)
        return 2
    if not pe.is_file() or hashlib.sha256(pe.read_bytes()).hexdigest() != identity[1].lower():
        print('falha: PE local nao corresponde ao lote', file=sys.stderr)
        return 2

    existing = load_functions(hints_path)
    batch = load_functions(batch_path)
    if not batch:
        print('falha: o lote nao tem entradas', file=sys.stderr)
        return 2

    problems, fresh = validate(existing, batch)
    if problems:
        print(f'lote rejeitado: {len(problems)} problema(s)')
        for problem in problems[:20]:
            print(f'  {problem}')
        if len(problems) > 20:
            print(f'  ... e mais {len(problems) - 20}')
        return 1

    repeated = len(batch) - len(fresh)
    print(f'lote aceito: {len(batch)} hints '
          f'({len(fresh)} novas, {repeated} ja aplicadas com o mesmo extent)')
    print(f'  antes: {len(existing)}  depois: {len(existing) + len(fresh)}')
    if args.check:
        return 0
    if not fresh:
        return 0

    text = hints_path.read_text(encoding='utf-8')
    if not text.endswith('\n'):
        text += '\n'
    block = ['']
    if args.note:
        block.append(f'# {args.note}')
    block.append(f'# Lote de analise estatica: {batch_path.name} '
                 f'({len(fresh)} entradas novas aceitas pelos filtros do .pdata/CFG).')
    block.append('# Extents derivados por construcao de CFG dentro do vao do .pdata;')
    block.append('# nao sao simbolos originais nem garantia de cobertura completa.')
    block.extend(format_entries(fresh))
    out_path = args.out if args.out else hints_path
    if args.out and not args.out.is_absolute():
        out_path = PROJECT / args.out
    out_path.write_text(text + '\n'.join(block) + '\n', encoding='utf-8')
    print(f'  gravado: {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

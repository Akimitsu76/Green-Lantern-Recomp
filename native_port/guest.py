"""Analise estatica do codigo guest (PowerPC big-endian) da imagem Xbox 360.

Este modulo expoe a leitura do PE normalizado (mesmo hash usado nos hints) e,
sobre ela, tres fontes de verdade:

* a tabela ``.pdata`` (Exception DataDirectory), que registra extents de
  funcoes com metadados de runtime, sem garantir cobertura de todas as folhas
  (``IMAGE_CE_RUNTIME_FUNCTION``: ``{BeginAddress, Data}``);
* o fluxo de bytes, decodificado com Capstone, para confirmar limites;
* varreduras de referencia, para distinguir ponteiro em dados de endereco
  montado em tempo de execucao (``lis`` + ``addi``).

Nada aqui executa codigo do jogo: apenas le o PE local ja decodificado.
"""
from __future__ import annotations

from dataclasses import dataclass
import functools
import re
import struct

from .errors import PortError
from .pe import inspect_pe

# --- .pdata / IMAGE_CE_RUNTIME_FUNCTION -------------------------------------
PDATA_PROLOG_MASK = 0xFF
PDATA_LENGTH_SHIFT = 8
PDATA_LENGTH_MASK = 0x3FFFFF
PDATA_THIRTY_TWO_BIT = 1 << 30
PDATA_EXCEPTION_FLAG = 1 << 31

# O intervalo de codigo recompilado observado no log do runtime.
DEFAULT_CODE_RANGE = (0x82140000, 0x827758EC)

# Espelho de ``IMAGE_CE_RUNTIME_FUNCTION`` do ReXGlue
# (``src/codegen/phase_register.cpp``).
@dataclass(frozen=True)
class PdataEntry:
    begin: int
    data: int

    @property
    def prolog_length(self) -> int:
        return self.data & PDATA_PROLOG_MASK

    @property
    def function_length(self) -> int:
        return (self.data >> PDATA_LENGTH_SHIFT) & PDATA_LENGTH_MASK

    @property
    def thirty_two_bit(self) -> bool:
        return bool(self.data & PDATA_THIRTY_TWO_BIT)

    @property
    def exception_flag(self) -> bool:
        return bool(self.data & PDATA_EXCEPTION_FLAG)

    @property
    def size(self) -> int:
        """Tamanho do extent em bytes (``FunctionLength * 4``)."""
        length = self.function_length
        return length * 4 if length else 4

    @property
    def end(self) -> int:
        return self.begin + self.size


def parse_pdata(blob: bytes) -> list[PdataEntry]:
    """Decodifica a tabela ``.pdata`` de 8 bytes big-endian."""
    if len(blob) % 8:
        blob = blob[:len(blob) - (len(blob) % 8)]
    return [PdataEntry(*struct.unpack_from('>II', blob, i * 8)) for i in range(len(blob) // 8)]


# --- imagem guest ------------------------------------------------------------

class GuestImage:
    """Leitura posicional do PE normalizado com semantica de endereco guest."""

    def __init__(self, data: bytes, info: dict):
        self.data = data
        self.info = info
        self.image_base = info['image_base']
        self.sections = info['sections']
        self._by_name = {s['name']: s for s in self.sections}

    @classmethod
    def from_file(cls, path) -> 'GuestImage':
        raw = path.read_bytes() if hasattr(path, 'read_bytes') else open(path, 'rb').read()
        return cls(raw, inspect_pe(raw))

    # -- endereco <-> arquivo -------------------------------------------------

    def section_of(self, address: int) -> dict | None:
        rva = address - self.image_base
        for section in self.sections:
            span = max(section['virtual_size'], section['raw_size'])
            if section['rva'] <= rva < section['rva'] + span:
                return section
        return None

    def offset_of(self, address: int) -> int | None:
        section = self.section_of(address)
        if section is None:
            return None
        if address - self.image_base - section['rva'] >= section['raw_size']:
            return None
        return section['raw_offset'] + (address - self.image_base - section['rva'])

    def read(self, address: int, size: int) -> bytes:
        section = self.section_of(address)
        if size < 0 or section is None or address - self.image_base - section['rva'] + size > section['raw_size']:
            raise PortError('GUEST_RANGE', 'Leitura fora dos bytes da secao.', address=hex(address), size=size)
        offset = self.offset_of(address)
        if offset is None:
            raise PortError('GUEST_RANGE', 'Endereco guest fora das secoes.', address=hex(address))
        end = offset + size
        if offset < 0 or end > len(self.data):
            raise PortError('GUEST_RANGE', 'Leitura fora da imagem.', address=hex(address), size=size)
        return self.data[offset:end]

    def executable_sections(self) -> list[dict]:
        return [s for s in self.sections if s['executable']]

    def code_range(self) -> tuple[int, int]:
        """Intervalo guest contiguo das secoes executaveis."""
        lo = min(self.image_base + s['rva'] for s in self.executable_sections())
        hi = max(self.image_base + s['rva'] + s['virtual_size'] for s in self.executable_sections())
        return lo, hi

    # -- pdata ----------------------------------------------------------------

    def pdata_entries(self) -> list[PdataEntry]:
        section = self._by_name.get('.pdata')
        if section is None:
            raise PortError('GUEST_PDATA', 'Secao .pdata ausente no PE normalizado.')
        if not section['raw_size']:
            return []
        blob = self.read(self.image_base + section['rva'], section['raw_size'])
        return parse_pdata(blob)

    def pdata_in_range(self, lo: int, hi: int) -> list[PdataEntry]:
        return sorted((e for e in self.pdata_entries() if lo <= e.begin < hi),
                      key=lambda e: e.begin)

    def pdata_gaps(self, lo: int, hi: int) -> list[tuple[int, int]]:
        """Vãos do mapa ``.pdata``: regiões sem entrada de função."""
        gaps: list[tuple[int, int]] = []
        cursor = lo
        for entry in self.pdata_in_range(lo, hi):
            if entry.begin > cursor:
                gaps.append((cursor, entry.begin))
            cursor = max(cursor, entry.end)
        if cursor < hi:
            gaps.append((cursor, hi))
        return gaps

    def pdata_covering(self, address: int) -> PdataEntry | None:
        for entry in self.pdata_entries():
            if entry.begin <= address < entry.end:
                return entry
        return None

    # -- referencias ----------------------------------------------------------

    def find_pointer_references(self, address: int) -> list[dict]:
        """Aponta valores big-endian de 32 bits iguais a ``address`` nos dados."""
        needle = struct.pack('>I', address)
        found = []
        for section in self.sections:
            if section['raw_size'] == 0:
                continue
            blob = self.data[section['raw_offset']:section['raw_offset'] + section['raw_size']]
            pos = blob.find(needle)
            while pos >= 0:
                guest = self.image_base + section['rva'] + pos
                found.append({'section': section['name'], 'address': guest,
                              'aligned4': pos % 4 == 0})
                pos = blob.find(needle, pos + 1)
        return found

    # -- desassamblagem -------------------------------------------------------

    def code_pointers_in_data(self, lo: int, hi: int,
                              skip_sections: tuple[str, ...] = ('.text', '.pdata')) -> dict[int, list[dict]]:
        """Endereços da faixa de código apontados por valores de 32 bits nos dados.

        Varre as seções de dados em passos de 4 bytes alinhados e devolve, para
        cada endereço da faixa ``[lo, hi)`` encontrado, onde ele aparece.
        """
        import array
        import sys as _sys

        found: dict[int, list[dict]] = {}
        for section in self.sections:
            if section['name'] in skip_sections or not section['raw_size']:
                continue
            blob = self.data[section['raw_offset']:section['raw_offset'] + section['raw_size']]
            usable = len(blob) - (len(blob) % 4)
            if usable <= 0:
                continue
            words = array.array('I')
            words.frombytes(blob[:usable])
            if _sys.byteorder == 'little':
                words.byteswap()  # big-endian na imagem
            base = self.image_base + section['rva']
            for index, value in enumerate(words):
                if lo <= value < hi:
                    found.setdefault(value, []).append(
                        {'section': section['name'], 'address': base + index * 4,
                         'aligned4': True})
        return found

    # -- desassemblagem -------------------------------------------------------

    def disassemble(self, address: int, size: int = 0x40, count: int | None = None) -> list[dict]:
        """Decodifica instrucoes PowerPC big-endian a partir de ``address``.

        Palavras que nao formam instrucao valida sao devolvidas com
        ``data=True``: sem isso o Capstone interrompe a decodificacao no
        primeiro padding e o resto do bloco se perde.
        """
        out = []
        for insn in _iter_instructions(self, address, size):
            out.append(insn)
            if count is not None and len(out) >= count:
                break
        return out

    def words(self, address: int, count: int) -> list[int]:
        blob = self.read(address, count * 4)
        return [struct.unpack_from('>I', blob, i * 4)[0] for i in range(count)]


@functools.lru_cache(maxsize=1)
def _powerpc_disassembler():
    try:
        import capstone
    except ImportError as exc:  # pragma: no cover - depende do ambiente
        raise PortError('GUEST_DISASM', 'Capstone nao esta disponivel para desassemblagem.') from exc
    md = capstone.Cs(capstone.CS_ARCH_PPC,
                     capstone.CS_MODE_BIG_ENDIAN | capstone.CS_MODE_64)
    # Sem skipdata o Capstone para na primeira palavra invalida e todo o
    # resto do vao (padding interno entre funcoes) fica sem decodificar.
    md.skipdata = True
    return md


def _iter_instructions(image: 'GuestImage', address: int, size: int):
    """Itera instrucoes PPC de forma preguicosa.

    O ``md.disasm`` do Capstone é um gerador: interrompe-lo no primeiro
    branch evita materializar milhares de instrucoes para blocos que terminam
    em poucos bytes. Sem isso, a analise de milhares de candidatos consome
    horas de CPU.
    """
    md = _powerpc_disassembler()
    blob = image.read(address, size)
    for insn in md.disasm(blob, address):
        yield {'address': insn.address, 'mnemonic': insn.mnemonic,
               'operands': insn.op_str, 'bytes': insn.bytes.hex(),
               'data': insn.mnemonic.startswith('.')}


# --- vãos do .pdata como candidatos a função -------------------------------

# Opcodes PPC relevantes para o reconhecimento de limites de bloco.
OP_BRANCH = 18      # b / bl
OP_COND_BRANCH = 16  # bc
OP_BRANCH_LINK = 19  # bclr / bcctr
OP_ADDI = 14
OP_ADDIS = 15        # lis when rA == 0
OP_ORI = 24

# Common printed aliases; control-flow decoding below uses raw opcode/LK/AA.
BRANCH_MNEMONICS = frozenset({
    'b', 'bl', 'ba', 'bla', 'bc', 'bcl', 'bclr', 'bcctr',
    'blr', 'blrl', 'bctr', 'bctrl',
})


def _branch_target(address: int, word: int) -> int | None:
    """Decode PPC I/B-form displacement, excluding AA/LK control bits."""
    opcode = word >> 26
    if opcode == OP_BRANCH:
        displacement = word & 0x03FFFFFC
        if displacement & 0x02000000:
            displacement -= 0x04000000
    elif opcode == OP_COND_BRANCH:
        displacement = word & 0xFFFC
        if displacement & 0x8000:
            displacement -= 0x10000
    else:
        return None
    return (displacement if word & 2 else address + displacement) & 0xFFFFFFFF


def analyze_gap(image: GuestImage, start: int, end: int) -> dict:
    """Descreve um vao do ``.pdata`` como candidato a função ausente."""
    size = end - start
    words = image.words(start, size // 4)
    by_address = {start + index * 4: word for index, word in enumerate(words)}
    decoded = image.disassemble(start, size=size)
    instructions = [insn for insn in decoded if not insn.get('data')]
    data_words = sum(1 for insn in decoded if insn.get('data'))
    branches = []
    for insn in instructions:
        mnemonic = insn['mnemonic']
        address = insn['address']
        word = by_address.get(address, 0)
        opcode = word >> 26
        if opcode not in (OP_BRANCH, OP_COND_BRANCH) and not (
                opcode == 19 and ((word >> 1) & 0x3FF) in (16, 528)):
            continue
        target = _branch_target(address, word) if opcode in (OP_BRANCH, OP_COND_BRANCH) else None
        branches.append({'address': address, 'kind': mnemonic, 'target': target,
                         'linked_call': bool(word & 1)})
    trailing = 0
    for word in reversed(words):
        if word:
            break
        trailing += 4
    return {
        'start': start,
        'end': end,
        'size': size,
        'word_count': len(words),
        'instruction_count': len(instructions),
        'data_words': data_words,
        'instructions': instructions,
        'branches': branches,
        'internal_branches': [b for b in branches
                              if b['target'] is not None and start <= b['target'] < end],
        'external_branches': [b for b in branches
                              if b['target'] is not None and not (start <= b['target'] < end)],
        'trailing_padding': trailing,
        'body_size': size - trailing,
        'terminator': branches[-1] if branches else None,
        'data_pointer_references': image.find_pointer_references(start),
    }


def classify_gap(report: dict) -> str:
    """Rotulo curto para o vao, sem afirmar mais do que a evidencia mostra."""
    if not report['instructions']:
        return 'sem codigo'
    if report['internal_branches']:
        return 'bloco interno (branch interno presente)'
    terminator = report['terminator']
    if terminator is None:
        return 'sem terminador de branch no vao'
    if (not terminator.get('linked_call') and
            terminator['address'] == report['instructions'][-1]['address'] and
            terminator['kind'] in ('blr', 'bctr', 'b', 'ba')):
        return f"funcao candidata (termina em {terminator['kind']})"
    return 'bloco interno (branch condicional)'


# --- enderecos montados em tempo de execucao -------------------------------

def find_constructed_pointers(image: GuestImage, lo: int, hi: int,
                              window: int = 8) -> list[dict]:
    """Localiza pares ``lis``/``addi`` que montam um endereco guest absoluto.

    Enderecos de funcao que so existem em tabelas montadas em runtime nao
    aparecem como literal na imagem; este detector encontra a construcao.
    """
    section = None
    for candidate in image.executable_sections():
        start = image.image_base + candidate['rva']
        end = start + candidate['virtual_size']
        if lo < end and hi > start:
            section = candidate
            break
    if section is None:
        return []
    base = image.image_base + section['rva']
    span = min(section['virtual_size'], section['raw_size'])
    blob = image.read(base, span)
    total = span // 4
    words = [struct.unpack_from('>I', blob, i * 4)[0] for i in range(total)]
    found = []
    for index, word in enumerate(words):
        if word >> 26 != OP_ADDI:
            continue
        source = (word >> 16) & 0x1F
        if source == 0:
            continue
        immediate = word & 0xFFFF
        if immediate & 0x8000:
            immediate -= 0x10000
        for back in range(1, min(window, index) + 1):
            prior = words[index - back]
            if prior >> 26 != OP_ADDIS:
                continue
            if ((prior >> 21) & 0x1F) != source or ((prior >> 16) & 0x1F) != 0:
                continue
            # Nenhuma escrita intermediaria no mesmo registrador.
            clobbered = False
            for step in range(index - back + 1, index):
                if ((words[step] >> 21) & 0x1F) == source:
                    clobbered = True
                    break
            if clobbered:
                continue
            high = prior & 0xFFFF
            target = ((high << 16) + immediate) & 0xFFFFFFFF
            found.append({'address': base + index * 4, 'target': target,
                          'lis_address': base + (index - back) * 4})
            break
    return found


# --- alvos nao registrados apontados por dados -----------------------------
def find_unregistered_branch_targets(image: GuestImage, lo: int, hi: int,
                                      gaps: list[tuple[int, int]] | None = None,
                                      edges: set[tuple[int, int]] | None = None) -> list[dict]:
    """Destinos de branch relativo que caem em vaos do ``.pdata``.

    Uma funcao chamada por ``bl`` direto nao aparece como ponteiro em dados,
    entao a varredura de dados nao a encontra. O destino do branch e um forte
    candidato, e o filtro de "branch externo" separa a entrada da funcao de
    um bloco interno da mesma funcao.

    Devolve ``{address, references, ref_count}``, no mesmo formato de
    :func:`find_unregistered_data_targets`.
    """
    if gaps is None:
        gaps = image.pdata_gaps(lo, hi)
    if edges is None:
        edges = branch_edges(image, lo, hi)
    incoming: dict[int, list[int]] = {}
    for source, target in edges:
        if lo <= target < hi:
            incoming.setdefault(target, []).append(source)
    results = []
    for target, sources in incoming.items():
        if target % 4:
            # Endereco de instrucao e sempre alinhado a 4 bytes.
            continue
        if image.pdata_covering(target) is not None:
            continue
        if not any(start <= target < end for start, end in gaps):
            continue
        results.append({'address': target,
                        'references': [{'section': '.text', 'address': source,
                                        'aligned4': True} for source in sorted(sources)],
                        'ref_count': len(sources)})
    results.sort(key=lambda item: (-item['ref_count'], item['address']))
    return results


def find_unregistered_data_targets(image: GuestImage, lo: int, hi: int) -> list[dict]:
    """Endereços de código sem entrada no ``.pdata`` apontados por dados.

    Ausencia no .pdata nao prova ausencia no codigo gerado: o recompilador
    tambem descobre funcoes por outras varreduras. O resultado e uma lista
    de candidatos para conferencia com o mapa gerado e os bytes originais.
    """
    covered = bytearray(hi - lo)
    for entry in image.pdata_in_range(lo, hi):
        start = max(entry.begin, lo) - lo
        stop = min(entry.end, hi) - lo
        if stop > start:
            covered[start:stop] = b'\x01' * (stop - start)
    results = []
    for target, refs in image.code_pointers_in_data(lo, hi).items():
        if covered[target - lo]:
            continue
        if target % 4:
            # Valor de dados que por acaso cai na faixa de código: nao e
            # ponteiro de funcao, porque um endereco de instrucao e sempre
            # alinhado a 4 bytes.
            continue
        results.append({'address': target, 'references': refs, 'ref_count': len(refs)})
    results.sort(key=lambda item: (-item['ref_count'], item['address']))
    return results


# --- inferência de extent para candidatos ----------------------------------

# Terminações que encerram uma função (não retornam ao chamador por lr).
TERMINATOR_MNEMONICS = frozenset({'blr', 'bctr'})
# Branches que deixam a função corrente.
EXIT_MNEMONICS = frozenset({'b', 'ba'})
# Chamadas: o fluxo continua depois delas.
CALL_MNEMONICS = frozenset({'bl', 'bla', 'blrl', 'bctrl'})
# Branches condicionais: indicam mais de um bloco na função.
CONDITIONAL_MNEMONICS = frozenset({
    'bc', 'bcl', 'beq', 'bne', 'bge', 'blt', 'bgt', 'ble', 'bso', 'bns',
    'bdnz', 'bdz', 'bdzf', 'bdnzf', 'bt', 'bf',
})


def branch_edges(image: GuestImage, lo: int, hi: int) -> set[tuple[int, int]]:
    """Arestas ``(origem, destino)`` de branches relativos na faixa de código.

    Decodifica só as palavras de branch (opcode 16 e 18) sem depender do
    Capstone, para varrer megabytes de código rapidamente. A origem importa:
    um branch que sai de dentro do extent e volta para ele é interno à
    função; só o branch que *entra* no extent indica bloco interno.
    """
    edges: set[tuple[int, int]] = set()
    for section in image.executable_sections():
        base = image.image_base + section['rva']
        span = min(section['virtual_size'], section['raw_size'])
        end = base + span
        if end <= lo or base >= hi:
            continue
        blob = image.read(base, span)
        for index in range(0, len(blob) - 3, 4):
            word = struct.unpack_from('>I', blob, index)[0]
            opcode = word >> 26
            if opcode not in (OP_BRANCH, OP_COND_BRANCH):
                continue
            address = base + index
            target = _branch_target(address, word)
            if target is not None:
                edges.add((address, target))
    return edges


def infer_function_extent(image: GuestImage, start: int, max_end: int) -> dict:
    """Infere o extent de uma função ausente construindo o CFG dentro do vão.

    A abordagem linear (terminar no primeiro branch) erra em laços rotacionados,
    onde o cabeçalho do laço salta para o meio do corpo. Aqui os blocos são
    percorridos como um grafo: só um branch *para fora* do vão encerra a
    função; um branch para dentro vira sucessor.
    """
    return build_gap_extent(image, start, start, max_end)


def build_gap_extent(image: GuestImage, start: int, gap_start: int, gap_end: int,
                      max_blocks: int = 96) -> dict:
    """Extent de uma função por construção de CFG confinada ao vão ``[gap_start, gap_end)``."""
    if not gap_start <= start < gap_end:
        return {'start': start, 'end': None, 'reason': 'inicio fora do vao'}
    blocks: dict[int, list[dict]] = {}
    successors: dict[int, list[int]] = {}
    block_ends: dict[int, int] = {}
    worklist = [start]
    ordered: list[int] = []
    reject = None
    exit_blocks = set()

    while worklist:
        addr = worklist.pop(0)
        if addr in blocks:
            continue
        if len(blocks) >= max_blocks:
            reject = 'CFG grande demais para inferir com confianca'
            break
        if not start <= addr < gap_end:
            reject = 'bloco fora do vao ou anterior ao inicio'
            break
        body, next_address, succ, kind = _decode_block(image, addr, gap_start, gap_end)
        if body is None:
            reject = 'instrucao invalida no bloco'
            break
        if body:
            blocks[addr] = body
            ordered.append(addr)
            block_ends[addr] = next_address
        successors[addr] = succ
        for target in succ:
            if target not in blocks:
                worklist.append(target)
        if kind == 'out_of_gap':
            reject = 'branch condicional sai do vao: multiplos blocos'
            break
        if kind in ('data', 'invalid', 'fallthrough'):
            reject = 'caminho sem terminador ou instrucao nao reconhecida'
            break
        if kind in ('terminator', 'exit', 'conditional_return'):
            exit_blocks.add(addr)

    if reject:
        return {'start': start, 'end': None, 'reason': reject}
    if not exit_blocks:
        return {'start': start, 'end': None, 'reason': 'nenhuma saida comprovada no CFG'}
    if not block_ends:
        return {'start': start, 'end': None, 'reason': 'sem codigo executavel no vao'}

    end = max(block_ends.values())
    body_all = [insn for addr in ordered for insn in blocks[addr]]
    conditional_targets = []
    for addr in ordered:
        for insn in blocks[addr]:
            if insn['mnemonic'] in CONDITIONAL_MNEMONICS:
                target = _parse_target(insn['operands'])
                if target is not None:
                    conditional_targets.append(target)
    terminator = None
    for addr in reversed(ordered):
        last = blocks[addr][-1]['mnemonic']
        if last in TERMINATOR_MNEMONICS or last in EXIT_MNEMONICS:
            terminator = last
            break
    return {
        'start': start,
        'end': end,
        'terminator': terminator,
        'block_count': len(blocks),
        'block_addresses': sorted(blocks),
        'conditional_inside': bool(conditional_targets),
        'conditional_targets': conditional_targets,
        'instruction_count': len(body_all),
        'frame': _cfg_frame_balance(blocks, successors, exit_blocks, start),
    }


def _decode_block(image: GuestImage, addr: int, gap_start: int, gap_end: int):
    """Decode until a control transfer; unknown reachable bytes reject the CFG.

    LK denotes a call with fallthrough, including bctrl/blrl. Conditional
    returns have both an exit and a fallthrough edge.
    """
    limit = min(gap_end, addr + 0x2000)
    if limit <= addr:
        return None, None, [], 'invalid'
    body = []
    for insn in _iter_instructions(image, addr, limit - addr):
        if insn.get('data'):
            return body, insn['address'], [], 'data'
        body.append(insn)
        pc = insn['address']
        word = int.from_bytes(bytes.fromhex(insn['bytes']), 'big')
        opcode = word >> 26
        if opcode in (OP_BRANCH, OP_COND_BRANCH):
            if word & 1:  # linked direct or conditional call
                continue
            target = _branch_target(pc, word)
            unconditional = opcode == OP_BRANCH or (((word >> 21) & 0x14) == 0x14)
            if unconditional:
                if gap_start <= target < gap_end:
                    return body, pc + 4, [target], 'branch'
                return body, pc + 4, [], 'exit'
            if not gap_start <= target < gap_end or pc + 4 >= gap_end:
                return body, pc + 4, [], 'out_of_gap'
            return body, pc + 4, [target, pc + 4], 'conditional'
        if opcode == 19 and ((word >> 1) & 0x3FF) in (16, 528):
            if word & 1:  # blrl / bctrl and their conditional variants
                continue
            if ((word >> 21) & 0x14) == 0x14:
                return body, pc + 4, [], 'terminator'
            if pc + 4 >= gap_end:
                return body, pc + 4, [], 'out_of_gap'
            return body, pc + 4, [pc + 4], 'conditional_return'
    return body, limit, [], 'invalid'


def _cfg_frame_balance(blocks, successors, exit_blocks, start):
    """Propagate r1 deltas; every return/tail exit must restore entry r1.

    Unmodelled writes and incompatible states are rejected conservatively.
    This proves only stack-pointer balance, not the full calling convention.
    """
    incoming = {start: 0}
    pending = [start]
    opened = False
    while pending:
        addr = pending.pop()
        delta = incoming[addr]
        for insn in blocks[addr]:
            mnemonic = insn['mnemonic']
            operands = insn['operands'].replace(' ', '')
            if mnemonic in ('stwu', 'stdu') and operands.startswith('r1,'):
                match = re.fullmatch(r'r1,(-?(?:0x[0-9a-fA-F]+|[0-9]+))\(r1\)', operands)
                if not match:
                    return {'frame_opened': True, 'frame_closed': None, 'balanced': False}
                amount = int(match.group(1), 0)
                opened = opened or amount < 0
                delta += amount
            elif mnemonic == 'addi' and operands.startswith('r1,r1,'):
                delta += int(operands.split(',')[-1], 0)
            elif operands.split(',')[0] == 'r1' and mnemonic not in (
                    'stw', 'std', 'stb', 'sth', 'stwx', 'stdx', 'cmpw', 'cmpd',
                    'cmplw', 'cmpld', 'cmpwi', 'cmpdi', 'cmplwi', 'cmpldi', 'mtlr', 'mtctr'):
                return {'frame_opened': opened, 'frame_closed': None, 'balanced': False}
        if addr in exit_blocks and delta != 0:
            return {'frame_opened': opened, 'frame_closed': None, 'balanced': False}
        for target in successors[addr]:
            if target in incoming:
                if incoming[target] != delta:
                    return {'frame_opened': opened, 'frame_closed': None, 'balanced': False}
            else:
                incoming[target] = delta
                pending.append(target)
    return {'frame_opened': opened, 'frame_closed': None, 'balanced': True,
            'method': 'per-path-r1-delta'}


def _parse_target(operands: str) -> int | None:
    """Extrai o destino numérico do último operando de um branch."""
    for token in reversed(operands.replace(',', ' ').split()):
        try:
            return int(token, 0)
        except ValueError:
            continue
    return None


def frame_balance(instructions: list[dict]) -> dict:
    """Heuristica para um trecho linear; nao prova equilibrio entre caminhos.

    A aceitacao de candidatos usa _cfg_frame_balance, que considera cada
    caminho do CFG. Esta funcao e mantida apenas para inspecao linear.
    """
    opened = None
    closed = None
    for insn in instructions:
        mnemonic = insn['mnemonic']
        operands = insn['operands'].replace(' ', '')
        if mnemonic == 'stwu' and operands.startswith('r1,'):
            # O deslocamento vem antes do parêntese: "r1,-0x70(r1)".
            match = re.search(r'(-?0x[0-9a-fA-F]+|-?\d+)\(', operands)
            opened = int(match.group(1), 0) if match else 'desconhecido'
        elif mnemonic == 'addi' and operands.startswith('r1,r1,'):
            try:
                closed = int(operands.split(',')[-1], 0)
            except ValueError:
                closed = 'desconhecido'
    if opened is None:
        return {'frame_opened': False, 'frame_closed': None, 'balanced': True}
    balanced = closed is not None and opened != 'desconhecido' and closed == -opened
    return {'frame_opened': True, 'frame_closed': closed, 'balanced': balanced}


def propose_hints(image: GuestImage, lo: int, hi: int,
                  candidates: list[dict],
                  branch_targets: set[tuple[int, int]] | None = None) -> list[dict]:
    """Propõe hints de função para candidatos não registrados.

    Cada proposta passa por quatro filtros, e qualquer um reprova a proposta:

    1. existe um terminador reconhecível dentro do limite;
    2. nenhum branch de fora entra no extent (seria bloco interno);
    3. o extent não contém outro candidato aceito;
    4. o extent não invade a próxima entrada do ``.pdata``.
    """
    entries = image.pdata_in_range(lo, hi)
    gaps = image.pdata_gaps(lo, hi)

    import bisect

    if branch_targets is None:
        branch_targets = branch_edges(image, lo, hi)

    proposals = []
    for candidate in candidates:
        start = candidate['address']
        gap = next(((a, b) for a, b in gaps if a <= start < b), (start, hi))
        gap_start, gap_end = gap
        index = bisect.bisect_right([entry.begin for entry in entries], start)
        limit = entries[index].begin if index < len(entries) else hi
        if limit <= start:
            limit = hi
        inference = build_gap_extent(image, start, gap_start, gap_end)
        row = dict(candidate)
        row.update(inference)
        row['gap'] = [gap_start, gap_end]
        if inference.get('end') is None:
            row['accepted'] = False
            row['reject_reason'] = inference.get('reason', 'sem extent')
            proposals.append(row)
            continue
        end = inference['end']
        # Branch que *entra* no extent vindo de fora: o extent seria um
        # bloco interno de uma funcao maior. Branch de dentro para dentro
        # e normal (caminho alternativo da propria funcao).
        foreign = sorted(t for s, t in branch_targets
                         if not (start <= s < end) and start < t < end)
        row['foreign_branch_targets'] = foreign
        row['frame_balanced'] = inference.get('frame', {}).get('balanced', True)
        conditional_targets = inference.get('conditional_targets', [])
        escaping = [t for t in conditional_targets if not start <= t < end]
        row['escaping_conditional_targets'] = escaping
        if foreign:
            row['accepted'] = False
            row['reject_reason'] = 'branch externo aponta para dentro do extent'
        elif end > limit:
            row['accepted'] = False
            row['reject_reason'] = 'extent invade a proxima entrada do .pdata'
        elif not row['frame_balanced']:
            row['accepted'] = False
            row['reject_reason'] = 'quadro de pilha aberto e nao fechado: extent truncado'
        elif escaping:
            row['accepted'] = False
            row['reject_reason'] = 'branch condicional sai do extent: multiplos blocos'
        else:
            row['accepted'] = True
            row['size'] = end - start
        proposals.append(row)

    # Duas funções irmãs dentro do mesmo vão não podem ter extents sobrepostos.
    accepted = sorted((p for p in proposals if p.get('accepted')),
                      key=lambda p: p['address'])
    for index, row in enumerate(accepted):
        end = row['end']
        for other in accepted[index + 1:]:
            if other['address'] >= end:
                break
            row['accepted'] = False
            row['reject_reason'] = (f"extent engole outro candidato em "
                                    f"{other['address']:#x}")
            break
    return proposals

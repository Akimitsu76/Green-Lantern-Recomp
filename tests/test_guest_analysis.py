"""Testes da analise estatica do codigo guest (native_port.guest).

O PE usado aqui e sintetico econstructed para os testes: nada do jogo real e
necessario, e nenhum arquivo original e tocado.
"""
import struct
import unittest

from native_port.guest import (GuestImage, analyze_gap, build_gap_extent,
                               classify_gap, find_constructed_pointers,
                               find_unregistered_data_targets, frame_balance,
                               parse_pdata, propose_hints)
from native_port.guest import _branch_target
from native_port.pe import inspect_pe
from native_port.errors import PortError

IMAGE_BASE = 0x82000000
CODE_RVA = 0x1000
RDATA_RVA = 0x2000
PDATA_RVA = 0x3000
IMAGE_SIZE = 0x4000
CODE = IMAGE_BASE + CODE_RVA

BLR = 0x4E800020
BCTR = 0x4E800420
NOP = 0x60000000


# --- codificacao de instrucoes PowerPC big-endian ---------------------------

def enc_b(target, current):
    """Branch incondicional relativo (deslocamento em bytes, bits 2-25)."""
    return 0x48000000 | ((target - current) & 0x03FFFFFC)


def enc_beq(target, current):
    """``beq cr6``: deslocamento de 16 bits nos bits 0-15."""
    return 0x419A0000 | ((target - current) & 0xFFFF)


def enc_bne(target, current):
    return 0x409A0000 | ((target - current) & 0xFFFF)


def enc_bdzf(target, current):
    return 0x405A0000 | ((target - current) & 0xFFFF)


def enc_lis(reg, value):
    return 0x3C000000 | (reg << 21) | (value & 0xFFFF)


def enc_addi(dst, src, value):
    return 0x38000000 | (dst << 21) | (src << 16) | (value & 0xFFFF)


def enc_lwz(dst, base, offset):
    return 0x80000000 | (dst << 21) | (base << 16) | (offset & 0xFFFF)


def enc_stw(src, base, offset):
    return 0x90000000 | (src << 21) | (base << 16) | (offset & 0xFFFF)


def enc_stwu(src, base, offset):
    return 0x94000000 | (src << 21) | (base << 16) | (offset & 0xFFFF)


def enc_mtctr(reg):
    return 0x7D6903A6 - ((11 - reg) << 21)


def pdata_record(begin, size, prolog=0x20, thirty_two=False, exception=False):
    """Registro ``IMAGE_CE_RUNTIME_FUNCTION`` de 8 bytes big-endian."""
    data = prolog | ((size // 4) << 8)
    if thirty_two:
        data |= 1 << 30
    if exception:
        data |= 1 << 31
    return struct.pack('>II', begin, data)


# --- PE sintetico ------------------------------------------------------------

def _align(value, alignment=0x200):
    return (value + alignment - 1) & ~(alignment - 1)


def build_pe(text, rdata=b'', pdata=b''):
    """PE PowerPC BE com ``.text`` (executavel), ``.rdata`` e ``.pdata``."""
    text_raw = 0x400
    rdata_raw = _align(text_raw + len(text))
    pdata_raw = _align(rdata_raw + len(rdata))
    image = bytearray(pdata_raw + len(pdata))
    image[0:2] = b'MZ'
    struct.pack_into('<I', image, 0x3C, 0x80)
    image[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', image, 0x84, 0x1F2, 3, 0, 0, 0, 224, 0x102)
    opt = 0x98
    struct.pack_into('<H', image, opt, 0x10B)
    struct.pack_into('<I', image, opt + 16, CODE_RVA)
    struct.pack_into('<III', image, opt + 28, IMAGE_BASE, 0x1000, 0x200)
    struct.pack_into('<II', image, opt + 56, IMAGE_SIZE, 0x400)
    struct.pack_into('<H', image, opt + 68, 14)
    table = opt + 224
    layout = (('.text', CODE_RVA, len(text), text_raw, len(text), 0x60000020),
              ('.rdata', RDATA_RVA, len(rdata), rdata_raw, len(rdata), 0x40000040),
              ('.pdata', PDATA_RVA, len(pdata), pdata_raw, len(pdata), 0x40000040))
    for index, (name, rva, vsize, raw, raw_size, flags) in enumerate(layout):
        off = table + index * 40
        image[off:off + 8] = name.encode('ascii').ljust(8, b'\0')
        struct.pack_into('<IIII', image, off + 8, vsize, rva, raw_size, raw)
        struct.pack_into('<I', image, off + 36, flags)
    image[text_raw:text_raw + len(text)] = text
    if rdata:
        image[rdata_raw:rdata_raw + len(rdata)] = rdata
    if pdata:
        image[pdata_raw:pdata_raw + len(pdata)] = pdata
    return bytes(image)


def make_image(text_words, pdata=(), rdata_words=()):
    text = b''.join(struct.pack('>I', word) for word in text_words)
    pdata_blob = b''.join(pdata)
    rdata = b''.join(struct.pack('>I', word) for word in rdata_words)
    pe = build_pe(text, rdata, pdata_blob)
    return GuestImage(pe, inspect_pe(pe))


class PdataTests(unittest.TestCase):
    def test_parse_pdata_decodes_bitfields(self):
        entries = parse_pdata(pdata_record(0x82001000, 0x20, prolog=0x2C))
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.begin, 0x82001000)
        self.assertEqual(entry.prolog_length, 0x2C)
        self.assertEqual(entry.function_length, 8)
        self.assertEqual(entry.size, 0x20)
        self.assertEqual(entry.end, 0x82001020)
        self.assertFalse(entry.thirty_two_bit)
        self.assertFalse(entry.exception_flag)

    def test_parse_pdata_flags_are_independent(self):
        entry = parse_pdata(pdata_record(0x82001000, 0x10, thirty_two=True,
                                         exception=True))[0]
        self.assertTrue(entry.thirty_two_bit)
        self.assertTrue(entry.exception_flag)
        self.assertEqual(entry.size, 0x10)

    def test_function_length_zero_means_four_bytes(self):
        entry = parse_pdata(pdata_record(0x82001000, 0))[0]
        self.assertEqual(entry.function_length, 0)
        self.assertEqual(entry.size, 4)

    def test_parse_pdata_ignores_partial_trailing_record(self):
        blob = pdata_record(0x82001000, 0x10) + b'\x00\x00\x00'
        self.assertEqual(len(parse_pdata(blob)), 1)

    def test_pdata_gaps_and_covering(self):
        image = make_image(
            [NOP] * 8,
            pdata=[pdata_record(CODE, 0x10), pdata_record(CODE + 0x20, 0x08)])
        lo, hi = image.code_range()
        gaps = image.pdata_gaps(lo, hi)
        self.assertIn((CODE + 0x10, CODE + 0x20), gaps)
        covering = image.pdata_covering(CODE + 0x04)
        self.assertIsNotNone(covering)
        self.assertEqual(covering.begin, CODE)
        self.assertIsNone(image.pdata_covering(CODE + 0x18))

    def test_pdata_entry_covers_only_its_own_function(self):
        image = make_image([NOP] * 8, pdata=[pdata_record(CODE, 0x10)])
        lo, hi = image.code_range()
        self.assertEqual(image.pdata_gaps(lo, hi), [(CODE + 0x10, hi)])


class ReferenceTests(unittest.TestCase):
    def test_virtual_tail_cannot_read_bytes_from_another_section(self):
        image = make_image([NOP, BLR], rdata_words=[CODE])
        image.sections[0]['virtual_size'] = 0x800
        self.assertIsNone(image.offset_of(CODE + 0x200))
        with self.assertRaises(PortError):
            image.read(CODE + 0x200, 4)
        with self.assertRaises(PortError):
            image.read(CODE + 4, 8)

    def test_find_pointer_references_reports_alignment(self):
        image = make_image([NOP] * 4, rdata_words=[CODE, 0, CODE])
        refs = image.find_pointer_references(CODE)
        self.assertEqual(len(refs), 2)
        self.assertTrue(all(ref['aligned4'] for ref in refs))

    def test_find_unregistered_data_targets_filters_covered_and_unaligned(self):
        # CODE esta coberto pelo .pdata; CODE+0x20 nao esta e alinhado;
        # CODE+0x24 nao esta e alinhado; CODE+0x30 nao esta e alinhado.
        image = make_image(
            [NOP] * 16,
            pdata=[pdata_record(CODE, 0x10)],
            rdata_words=[CODE, CODE + 0x22, CODE + 0x30])
        lo, hi = image.code_range()
        targets = find_unregistered_data_targets(image, lo, hi)
        addresses = [item['address'] for item in targets]
        self.assertEqual(addresses, [CODE + 0x30])
        self.assertEqual(targets[0]['ref_count'], 1)

    def test_find_constructed_pointers_matches_lis_addi(self):
        image = make_image([enc_lis(11, 0x8277), enc_addi(11, 11, 0x1968)])
        lo, hi = image.code_range()
        found = find_constructed_pointers(image, lo, hi)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['target'], 0x82771968)
        self.assertEqual(found[0]['address'], CODE + 4)

    def test_find_constructed_pointers_ignores_clobbered_register(self):
        image = make_image([enc_lis(11, 0x8277), enc_addi(11, 11, 0),
                            enc_addi(11, 11, 0x1968)])
        lo, hi = image.code_range()
        found = find_constructed_pointers(image, lo, hi)
        self.assertEqual([item['target'] for item in found], [0x82770000])

    def test_find_constructed_pointers_requires_previous_lis(self):
        image = make_image([enc_addi(11, 11, 0x1968)])
        lo, hi = image.code_range()
        self.assertEqual(find_constructed_pointers(image, lo, hi), [])


class ExtentTests(unittest.TestCase):
    def test_leaf_accessor_extent(self):
        image = make_image([enc_lwz(3, 3, 0x1F0), BLR])
        lo, hi = image.code_range()
        result = build_gap_extent(image, lo, lo, hi)
        self.assertEqual(result['end'], lo + 8)
        self.assertEqual(result['block_count'], 1)
        self.assertEqual(result['terminator'], 'blr')

    def test_sibling_accessors_in_one_gap(self):
        image = make_image([enc_lwz(3, 3, 0x1F0), BLR,
                            enc_addi(3, 3, 0x21C), BLR])
        lo, hi = image.code_range()
        first = build_gap_extent(image, lo, lo, hi)
        second = build_gap_extent(image, lo + 8, lo, hi)
        self.assertEqual(first['end'], lo + 8)
        self.assertEqual(second['end'], lo + 16)
        self.assertEqual(second['block_count'], 1)

    def test_rotated_loop_extent(self):
        # O cabecalho salta para o meio do corpo: um branch linear trataria
        # o "b" como terminador e truncaria a funcao.
        body = [enc_lwz(11, 3, 0x18), enc_addi(10, 3, 0x18), enc_addi(9, 0, 0),
                enc_b(lo_at := CODE + 0x14, CODE + 0x0C),
                enc_lwz(11, 11, 0), enc_addi(9, 9, 1),
                enc_bne(CODE + 0x10, CODE + 0x18), enc_stw(9, 4, 0),
                enc_addi(3, 0, 0), BLR]
        image = make_image(body)
        lo, hi = image.code_range()
        result = build_gap_extent(image, lo, lo, hi)
        self.assertEqual(result['end'], hi)
        self.assertEqual(result['block_count'], 4)
        self.assertEqual(result['terminator'], 'blr')
        self.assertGreaterEqual(lo_at, CODE)

    def test_bdzf_dispatch_extent(self):
        body = [enc_mtctr(11), enc_bdzf(CODE + 0x20, CODE + 0x04),
                enc_bdzf(CODE + 0x30, CODE + 0x08), enc_bdzf(CODE + 0x40, CODE + 0x0C),
                enc_b(CODE + 0x50, CODE + 0x10)]
        body += [0] * 3
        for offset, value in ((0x20, 1), (0x30, 2), (0x40, 3), (0x50, 4)):
            body += [enc_addi(3, 0, value), BLR, 0, 0]
        image = make_image(body)
        lo, hi = image.code_range()
        result = build_gap_extent(image, lo, lo, hi)
        # O extent vai ate o fim do ultimo bloco alcançavel (0x58); os zeros
        # seguintes sao preenchimento e nao pertencem a funcao.
        self.assertEqual(result['end'], CODE + 0x58)
        self.assertEqual(result['block_count'], 8)
        self.assertEqual(result['terminator'], 'blr')

    def test_conditional_branch_outside_gap_is_rejected(self):
        image = make_image([enc_bne(CODE + 0x40, CODE), BLR])
        lo, hi = image.code_range()
        result = build_gap_extent(image, lo, lo, hi)
        self.assertIsNone(result['end'])
        self.assertIn('sai do vao', result['reason'])

    def test_tail_branch_outside_gap_ends_the_function(self):
        image = make_image([enc_b(CODE + 0x40, CODE)])
        lo, hi = image.code_range()
        result = build_gap_extent(image, lo, lo, hi)
        self.assertEqual(result['end'], lo + 4)
        self.assertEqual(result['terminator'], 'b')

    def test_frame_balance_detects_unclosed_frame(self):
        image = make_image([enc_stwu(1, 1, -0x70), BLR])
        body = image.disassemble(CODE, size=8)
        report = frame_balance(body)
        self.assertTrue(report['frame_opened'])
        self.assertFalse(report['balanced'])

    def test_frame_balance_accepts_closed_frame(self):
        image = make_image([enc_stwu(1, 1, -0x70), enc_addi(1, 1, 0x70), BLR])
        body = image.disassemble(CODE, size=12)
        report = frame_balance(body)
        self.assertTrue(report['frame_opened'])
        self.assertEqual(report['frame_closed'], 0x70)
        self.assertTrue(report['balanced'])

    def test_frame_balance_ignores_leaf_functions(self):
        image = make_image([enc_lwz(3, 3, 0x10), BLR])
        report = frame_balance(image.disassemble(CODE, size=8))
        self.assertFalse(report['frame_opened'])
        self.assertTrue(report['balanced'])


class BranchTargetTests(unittest.TestCase):
    """Branch displacements exclude the AA and LK bits in both forms."""

    def test_absolute_branch_and_conditional_link(self):
        self.assertEqual(_branch_target(CODE, 0x48000102), 0x100)
        self.assertEqual(_branch_target(CODE, 0x419A0011), CODE + 0x10)

    def test_b_uses_24_bit_displacement(self):
        word = enc_b(CODE + 0x100, CODE)
        self.assertEqual(_branch_target(CODE, word), CODE + 0x100)

    def test_b_with_negative_displacement(self):
        word = enc_b(CODE - 0x40, CODE)
        self.assertEqual(_branch_target(CODE, word), CODE - 0x40)

    def test_bc_uses_16_bit_displacement(self):
        word = enc_beq(CODE + 0x20, CODE)
        self.assertEqual(_branch_target(CODE, word), CODE + 0x20)

    def test_bc_with_negative_displacement(self):
        word = enc_bne(CODE - 0x18, CODE)
        self.assertEqual(_branch_target(CODE, word), CODE - 0x18)

    def test_branch_target_agrees_with_capstone(self):
        image = make_image([enc_beq(CODE + 0x20, CODE), enc_b(CODE + 0x40, CODE + 4)])
        decoded = image.disassemble(CODE, size=8)
        self.assertEqual(decoded[0]['mnemonic'], 'beq')
        self.assertEqual(int(decoded[0]['operands'].split(',')[-1], 0), CODE + 0x20)
        self.assertEqual(decoded[1]['mnemonic'], 'b')
        self.assertEqual(int(decoded[1]['operands'], 0), CODE + 0x40)

    def test_non_branch_opcode_has_no_target(self):
        self.assertIsNone(_branch_target(CODE, 0x4E800020))


class AnalyzeGapTests(unittest.TestCase):
    def test_analyze_gap_reports_branches_and_padding(self):
        # O "b" salta para CODE+0x10, dentro do vao: e branch interno.
        image = make_image([enc_addi(3, 3, 0), enc_b(CODE + 0x10, CODE + 4),
                            0, 0, BLR, 0])
        lo, hi = image.code_range()
        report = analyze_gap(image, lo, hi)
        self.assertEqual(report['size'], 24)
        self.assertEqual(report['trailing_padding'], 4)
        self.assertEqual(report['body_size'], 20)
        self.assertTrue(report['internal_branches'])
        self.assertFalse(report['external_branches'])

    def test_analyze_gap_counts_branch_outside_gap_as_external(self):
        image = make_image([enc_addi(3, 3, 0), enc_b(CODE + 0x40, CODE + 4),
                            0, 0, BLR, 0])
        lo, hi = image.code_range()
        report = analyze_gap(image, lo, hi)
        self.assertFalse(report['internal_branches'])
        self.assertTrue(report['external_branches'])

    def test_classify_gap_labels_candidates(self):
        image = make_image([enc_lwz(3, 3, 0x10), BLR])
        lo, hi = image.code_range()
        self.assertIn('funcao candidata', classify_gap(analyze_gap(image, lo, hi)))

    def test_classify_gap_reports_empty_code(self):
        image = make_image([NOP] * 4)
        lo, hi = image.code_range()
        report = analyze_gap(image, lo, lo)
        self.assertEqual(classify_gap(report), 'sem codigo')


class ProposeHintsTests(unittest.TestCase):
    def _proposals(self, image, addresses):
        lo, hi = image.code_range()
        candidates = [{'address': address, 'references': [], 'ref_count': 1}
                      for address in addresses]
        return propose_hints(image, lo, hi, candidates)

    def test_leaf_candidate_is_accepted(self):
        image = make_image([enc_lwz(3, 3, 0x1F0), BLR])
        proposals = self._proposals(image, [CODE])
        self.assertTrue(proposals[0]['accepted'])
        self.assertEqual(proposals[0]['size'], 8)

    def test_unknown_reachable_word_cannot_truncate_function(self):
        proposals = self._proposals(make_image([NOP, 0, BLR]), [CODE])
        self.assertFalse(proposals[0]['accepted'])

    def test_indirect_call_keeps_fallthrough(self):
        image = make_image([0x4E800421, enc_addi(3, 0, 7), BLR])
        proposal = self._proposals(image, [CODE])[0]
        self.assertTrue(proposal['accepted'])
        self.assertEqual(proposal['size'], 12)

    def test_every_return_path_must_restore_stack(self):
        image = make_image([enc_stwu(1, 1, -0x70), enc_beq(CODE + 16, CODE + 4),
                            enc_addi(1, 1, 0x70), BLR, BLR])
        self.assertFalse(self._proposals(image, [CODE])[0]['accepted'])

    def test_sibling_candidates_do_not_overlap(self):
        image = make_image([enc_lwz(3, 3, 0x1F0), BLR, enc_addi(3, 3, 0x21C), BLR])
        proposals = self._proposals(image, [CODE, CODE + 8])
        accepted = [p for p in proposals if p['accepted']]
        self.assertEqual(len(accepted), 2)
        self.assertEqual(accepted[0]['end'], accepted[1]['start'])

    def test_function_with_unclosed_frame_is_rejected(self):
        image = make_image([enc_stwu(1, 1, -0x70), BLR])
        proposals = self._proposals(image, [CODE])
        self.assertFalse(proposals[0]['accepted'])
        self.assertIn('quadro de pilha', proposals[0]['reject_reason'])

    def test_candidate_without_terminator_is_rejected(self):
        image = make_image([NOP, NOP, NOP, NOP])
        proposals = self._proposals(image, [CODE])
        self.assertFalse(proposals[0]['accepted'])

    def test_internal_branch_inside_extent_is_accepted(self):
        # Caminho alternativo da propria funcao (branch de dentro para
        # dentro): nao a torna bloco interno.
        image = make_image([enc_lwz(11, 3, 0x68), enc_beq(CODE + 0x10, CODE + 4),
                            enc_lwz(3, 11, 0x34), BLR, enc_addi(3, 0, 0), BLR])
        proposals = self._proposals(image, [CODE])
        self.assertTrue(proposals[0]['accepted'])
        self.assertEqual(proposals[0]['size'], 0x18)

    def test_branch_entering_extent_from_outside_is_rejected(self):
        # Um branch de fora entra no extent: o extent e bloco interno.
        image = make_image([enc_beq(CODE + 0x08, CODE), enc_lwz(11, 3, 0x68), BLR])
        proposals = self._proposals(image, [CODE + 4])
        self.assertFalse(proposals[0]['accepted'])
        self.assertIn('branch externo', proposals[0]['reject_reason'])


if __name__ == '__main__':
    unittest.main()

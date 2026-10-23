"""Original synthetic XEX/PE used to verify the local decoding adapter."""
from pathlib import Path
import struct


def make():
    image = bytearray(8192)
    image[:2] = b'MZ'
    struct.pack_into('<I', image, 0x3c, 0x80)
    image[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', image, 0x84, 0x1F2, 1, 0, 0, 0, 224, 0x102)
    opt = 0x98
    struct.pack_into('<H', image, opt, 0x10b)
    struct.pack_into('<I', image, opt+16, 0x1000)
    struct.pack_into('<III', image, opt+28, 0x82000000, 0x1000, 0x200)
    struct.pack_into('<II', image, opt+56, len(image), 0x200)
    struct.pack_into('<H', image, opt+68, 14)
    section = opt+224
    image[section:section+8] = b'.text\0\0\0'
    struct.pack_into('<IIII', image, section+8, 4, 0x1000, 4, 0x1000)
    struct.pack_into('<I', image, section+36, 0x60000020)
    image[0x1000:0x1004] = bytes.fromhex('4e800020')  # original synthetic blr
    xex = bytearray(0x400)
    struct.pack_into('>4s5I', xex, 0, b'XEX2', 1, len(xex), 0, 0x80, 3)
    struct.pack_into('>6I', xex, 24, 0x10100, 0x82001000, 0x10201, 0x82000000, 0x3ff, 0x50)
    struct.pack_into('>IHHII', xex, 0x50, 16, 0, 1, len(image), 0)
    struct.pack_into('>II', xex, 0x80, 0x184, len(image))
    struct.pack_into('>I', xex, 0x80+0x110, 0x82000000)
    return bytes(xex+image), bytes(image)


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]/'.aster/fixtures'
    root.mkdir(parents=True, exist_ok=True)
    xex, pe = make()
    (root/'synthetic.xex').write_bytes(xex)
    (root/'expected.pe').write_bytes(pe)

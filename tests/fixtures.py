"""Synthetic format fixtures; no executable instructions or game content."""
import struct
from native_port.sources import MAGIC, SECTOR


def xex(title=0x575207E9):
    b = bytearray(1024)
    struct.pack_into('>4s5I', b, 0, b'XEX2', 0, 512, 0, 256, 3)
    struct.pack_into('>6I', b, 24, 0x40006, 64, 0x10100, 0x82000000, 0x3FF, 96)
    struct.pack_into('>6I', b, 64, 0, 0x100, 0, title, 0, 0)
    struct.pack_into('>IHH', b, 96, 8, 0, 0)
    return b


def iso():
    b = bytearray(40 * SECTOR)
    off = 32 * SECTOR
    b[off:off+20] = MAGIC
    b[off+SECTOR-20:off+SECTOR] = MAGIC
    struct.pack_into('<II', b, off+20, 33, 64)
    # Empty/synthetic volume: only descriptor validation is asserted.
    return b

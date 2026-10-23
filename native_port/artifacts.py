"""Host probe validation only. Never qualifies a game as playable."""
import hashlib
from pathlib import Path
import struct
from .errors import PortError


def verify_host_elf(path, root, expected_sha=None):
    p = Path(path).resolve()
    if not p.is_relative_to(Path(root).resolve()) or not p.is_file():
        raise PortError('ARTIFACT_PATH', 'Artefato fora da saída ou inexistente.')
    with p.open('rb') as f:
        h = f.read(64)
    if len(h) < 64 or h[:6] != b'\x7fELF\x02\x01':
        raise PortError('BAD_ARTIFACT', 'Esperado ELF64 little-endian.')
    kind, machine = struct.unpack_from('<HH', h, 16)
    if machine != 62 or kind not in (2, 3) or not p.stat().st_mode & 0o111:
        raise PortError('BAD_ARTIFACT', 'Esperado executável ELF x86_64.')
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if expected_sha is not None and digest != expected_sha:
        raise PortError('ARTIFACT_CHANGED', 'Hash do artefato divergente.')
    return {'path': str(p), 'sha256': digest, 'purpose': 'host-probe', 'game_ready': False}

"""Extract the pinned CMake wheel into project-local tools, without pip install."""
import hashlib
from pathlib import Path
import stat
import zipfile

PROJECT=Path(__file__).resolve().parents[1]
EXPECTED='2f766bb46367e5e0559fa33184653754bce044583a06014dcaebf8e6dff8a1f1'
if __name__=='__main__':
    wheel=PROJECT/'.aster/tools/downloads/cmake-3.31.10-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl'
    if hashlib.sha256(wheel.read_bytes()).hexdigest()!=EXPECTED:
        raise SystemExit('CMake wheel checksum differs from reviewed artifact')
    root=(PROJECT/'.aster/tools/cmake-runtime').resolve()
    with zipfile.ZipFile(wheel) as archive:
        for item in archive.infolist():
            if not (root/item.filename).resolve().is_relative_to(root) or stat.S_ISLNK(item.external_attr>>16):
                raise SystemExit('Unsafe archive member')
        archive.extractall(root)
    for name in ('cmake','ctest','cpack'):
        p=root/'cmake/data/bin'/name
        p.chmod(p.stat().st_mode|0o111)
    print(root/'cmake/data/bin/cmake')

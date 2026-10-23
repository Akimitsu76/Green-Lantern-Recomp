"""Compile and execute an original host utility, NEVER game code or a port."""
import json
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from native_port.artifacts import verify_host_elf
from native_port.diagnostics import diagnostics
from native_port.errors import PortError
from native_port.tasks import Cancellation, run_process
from native_port.workspace import Workspace


def main():
    workspace = Workspace(PROJECT / '.aster', PROJECT)
    compiler = shutil.which('c++')
    if not compiler:
        raise PortError('MISSING_COMPILER', 'Compilador C++ ausente.')
    out = workspace.path('output/aster-host-probe')
    out.parent.mkdir(parents=True, exist_ok=True)
    cancel = Cancellation()
    build = run_process([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                         str(PROJECT / 'scripts/host_probe.cpp'), '-o', str(out)], PROJECT, cancel)
    artifact = verify_host_elf(out, workspace.path('output'))
    execution = run_process([str(out)], PROJECT, cancel)
    report = {'purpose': 'host-probe', 'game_ready': False, 'artifact': artifact,
              'build': build, 'execution': execution, 'environment': diagnostics()}
    p = workspace.write_json('reports/host-probe.json', report)
    print(execution['stdout'], end='')
    print(f'Relatório: {p}')


if __name__ == '__main__':
    try:
        main()
    except PortError as e:
        print(json.dumps(e.as_dict(), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)

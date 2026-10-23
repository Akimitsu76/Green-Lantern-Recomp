import os
import signal
import subprocess
import threading
import time
from .errors import PortError


class Cancellation:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise PortError('CANCELLED', 'Operação cancelada.')


def run_process(argv, cwd, cancel, timeout=120, env=None):
    """Internal trusted calls only; never accepts argv from a game manifest or UI.

    No shell, own process group; cancellation kills descendants and reaps parent.
    Output is spooled to temporary files, with a bounded diagnostic tail.
    """
    import tempfile
    start = time.monotonic()
    cancel.check()
    try:
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            with subprocess.Popen(argv, cwd=cwd, stdout=out, stderr=err,
                                  start_new_session=True, env=env) as proc:
                try:
                    while proc.poll() is None:
                        cancel.check()
                        if time.monotonic() - start > timeout:
                            raise PortError('TIMEOUT', 'Tempo limite da tarefa excedido.')
                        cancel.event.wait(0.025)
                except BaseException:
                    try:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if proc.poll() is None:
                                proc.kill()
                        else:
                            os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    raise
                def tail(f):
                    f.seek(0, 2)
                    f.seek(max(0, f.tell()-65536))
                    return f.read().decode('utf8', errors='replace')
                result = dict(argv=list(map(str, argv)), returncode=proc.returncode,
                              stdout=tail(out), stderr=tail(err), seconds=time.monotonic()-start)
    except OSError as e:
        raise PortError('PROCESS_START', str(e), argv=list(map(str, argv))) from e
    if result['returncode']:
        raise PortError('PROCESS_FAILED', 'Falha na ferramenta externa.', **result)
    return result

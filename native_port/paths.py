"""Paths and child invocation shared by source and portable launchers."""
import os
from pathlib import Path
import sys


def project_root(source):
    if getattr(sys, 'frozen', False):
        if os.environ.get('ASTER_LAUNCHER_ROOT'):
            return Path(os.environ['ASTER_LAUNCHER_ROOT']).resolve()
        return Path(sys.executable).resolve().parent / 'app'
    return Path(source).resolve().parents[1]


def python_command(script, *arguments):
    if getattr(sys, 'frozen', False):
        executable = os.environ.get('APPIMAGE', sys.executable)
        runtime = ['--appimage-extract-and-run'] if os.environ.get('APPIMAGE') else []
        return [executable, *runtime, '--aster-script', str(script), *map(str, arguments)]
    return [sys.executable, str(script), *map(str, arguments)]


def external_env():
    env = os.environ.copy()
    if getattr(sys, 'frozen', False):
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.SetDllDirectoryW(None)
        elif 'LD_LIBRARY_PATH_ORIG' in env:
            env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
        else:
            env.pop('LD_LIBRARY_PATH', None)
    return env

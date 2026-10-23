"""Send a key to one verified probe window, never to the desktop/root."""
import ctypes as C
import json
import os
import re
import subprocess
import time


def focus_verified_niri_window(window_id: str) -> dict:
    """Match the already PID-verified X11 title/class, never an arbitrary window."""
    if not os.environ.get('NIRI_SOCKET'):
        return {}
    try:
        prop = subprocess.run(['xprop', '-id', window_id, '_NET_WM_NAME', 'WM_CLASS'],
                              capture_output=True, text=True, timeout=2, check=True)
        title = re.search(r'_NET_WM_NAME[^=]*=\s*(".*")', prop.stdout)
        classes = re.search(r'WM_CLASS[^=]*=\s*(.*)', prop.stdout)
        if not title or not classes:
            return {'error': 'Verified X11 title/class unavailable'}
        title = json.loads(title.group(1))
        classes = [json.loads(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"', classes.group(1))]
        reply = subprocess.run(['niri', 'msg', '--json', 'windows'],
                               capture_output=True, text=True, timeout=2, check=True)
        matches = [x for x in json.loads(reply.stdout)
                   if x.get('title') == title and x.get('app_id') in classes]
        if len(matches) != 1:
            return {'error': 'No unique compositor match for verified probe window'}
        result = subprocess.run(['niri', 'msg', 'action', 'focus-window', '--id', str(matches[0]['id'])],
                                capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and not matches[0].get('is_focused'):
            # The compositor acknowledges the request before SDL necessarily
            # handles FocusIn. A key delivered first is intentionally ignored.
            time.sleep(0.2)
        return {'window_id': matches[0]['id'], 'returncode': result.returncode}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {'error': str(exc)}


class KeyEvent(C.Structure):
    _fields_ = [('type', C.c_int), ('serial', C.c_ulong), ('send_event', C.c_int),
                ('display', C.c_void_p), ('window', C.c_ulong), ('root', C.c_ulong),
                ('subwindow', C.c_ulong), ('time', C.c_ulong), ('x', C.c_int),
                ('y', C.c_int), ('x_root', C.c_int), ('y_root', C.c_int),
                ('state', C.c_uint), ('keycode', C.c_uint), ('same_screen', C.c_int)]


def send_window_key(pid: int, window_id: str, key: str, hold_seconds: float = 0.18) -> dict:
    if not 0.01 <= hold_seconds <= 3:
        raise ValueError('Key hold must be between 0.01 and 3 seconds.')
    prop = subprocess.run(['xprop', '-id', window_id, '_NET_WM_PID'],
                          capture_output=True, text=True, timeout=2)
    match = re.search(r'=\s*(\d+)\s*$', prop.stdout)
    if not match or int(match.group(1)) != pid:
        return {'key': key, 'error': 'Window PID does not match probe process'}
    compositor_focus = focus_verified_niri_window(window_id)
    x = C.CDLL('libX11.so.6')
    x.XOpenDisplay.argtypes = [C.c_char_p]
    x.XOpenDisplay.restype = C.c_void_p
    x.XCloseDisplay.argtypes = [C.c_void_p]
    x.XDefaultRootWindow.argtypes = [C.c_void_p]
    x.XDefaultRootWindow.restype = C.c_ulong
    x.XStringToKeysym.argtypes = [C.c_char_p]
    x.XStringToKeysym.restype = C.c_ulong
    x.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]
    x.XKeysymToKeycode.restype = C.c_ubyte
    x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
    x.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.c_void_p]
    x.XFlush.argtypes = [C.c_void_p]
    display = x.XOpenDisplay(None)
    if not display:
        return {'key': key, 'error': 'Cannot open X11 display'}
    try:
        window = int(window_id, 16)
        names = key.split('+')
        if not 1 <= len(names) <= 3 or len(set(names)) != len(names):
            return {'key': key, 'error': 'Invalid X11 key combination'}
        codes = [x.XKeysymToKeycode(display, x.XStringToKeysym(name.encode('ascii'))) for name in names]
        if not all(codes):
            return {'key': key, 'error': 'Unknown X11 key'}
        x.XSetInputFocus(display, window, 1, 0)
        event = KeyEvent(type=2, send_event=1, display=display, window=window,
                         root=x.XDefaultRootWindow(display), same_screen=1)
        sent = True
        pressed = []
        try:
            for code in codes:
                event.keycode = code
                pressed.append(code)
                sent = bool(x.XSendEvent(display, window, 0, 1, C.byref(event))) and sent
            x.XFlush(display)
            time.sleep(hold_seconds)
        finally:
            event.type = 3
            for code in reversed(pressed):
                event.keycode = code
                sent = bool(x.XSendEvent(display, window, 0, 2, C.byref(event))) and sent
            x.XFlush(display)
        return {'key': key, 'window_id': window_id, 'pid': pid,
                'events_sent': sent, 'hold_seconds': hold_seconds,
                'compositor_focus': compositor_focus}
    finally:
        x.XCloseDisplay(display)

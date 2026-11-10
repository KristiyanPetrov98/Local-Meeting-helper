"""Linux test fixture only: send a real XTest Ctrl+Shift+P sequence to the X server."""
import ctypes
from ctypes.util import find_library
x11 = ctypes.CDLL(find_library('X11'))
xtst = ctypes.CDLL(find_library('Xtst'))
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
x11.XKeysymToKeycode.restype = ctypes.c_ubyte
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
x11.XFlush.argtypes = [ctypes.c_void_p]
x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
display = x11.XOpenDisplay(None)
if not display:
    raise SystemExit('Test display unavailable')
try:
    codes = [x11.XKeysymToKeycode(display, key) for key in (0xffe3, 0xffe1, ord('p'))]
    for code in codes:
        if not xtst.XTestFakeKeyEvent(display, code, 1, 0):
            raise RuntimeError('XTest key press rejected')
    for code in reversed(codes):
        xtst.XTestFakeKeyEvent(display, code, 0, 0)
    x11.XFlush(display)
finally:
    x11.XCloseDisplay(display)

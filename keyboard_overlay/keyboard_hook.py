"""Windows low-level keyboard hook. Events are sent to the UI through a queue."""
import ctypes
import ctypes.wintypes as wt

WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
LLKHF_EXTENDED = 0x01

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]

class KeyboardHook:
    def __init__(self, event_queue):
        self.queue = event_queue
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self.result_type = ctypes.c_ssize_t
        self.callback_type = ctypes.WINFUNCTYPE(self.result_type, ctypes.c_int, wt.WPARAM, wt.LPARAM)
        self.callback = self.callback_type(self._callback)
        self.user32.SetWindowsHookExW.argtypes = (ctypes.c_int, self.callback_type, wt.HINSTANCE, wt.DWORD)
        self.user32.SetWindowsHookExW.restype = wt.HHOOK
        self.kernel32.GetModuleHandleW.argtypes = (wt.LPCWSTR,)
        self.kernel32.GetModuleHandleW.restype = wt.HMODULE
        self.user32.CallNextHookEx.argtypes = (wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM)
        self.user32.CallNextHookEx.restype = self.result_type
        self.user32.UnhookWindowsHookEx.argtypes = (wt.HHOOK,)
        self.user32.UnhookWindowsHookEx.restype = wt.BOOL
        self.handle = self.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self.callback, self.kernel32.GetModuleHandleW(None), 0
        )
        if not self.handle:
            raise OSError("Windows could not install the keyboard hook.")

    @staticmethod
    def scan_id(scan_code, flags):
        return f"{'E0' if flags & LLKHF_EXTENDED else ''}{scan_code:02X}"

    def _callback(self, n_code, w_param, l_param):
        if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
            event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            pressed = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
            self.queue.put((self.scan_id(event.scanCode, event.flags), pressed, event.vkCode))
        return self.user32.CallNextHookEx(self.handle, n_code, w_param, l_param)

    def close(self):
        if self.handle:
            self.user32.UnhookWindowsHookEx(self.handle)
            self.handle = None

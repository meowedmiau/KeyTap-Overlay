"""Windows low-level mouse hook. Events are sent to the UI through a queue."""
import ctypes
import ctypes.wintypes as wt

WH_MOUSE_LL = 14
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEWHEEL = 0x020A

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]

class MouseHook:
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
            WH_MOUSE_LL, self.callback, self.kernel32.GetModuleHandleW(None), 0
        )
        if not self.handle:
            raise OSError("Windows could not install the mouse hook.")

    def _callback(self, n_code, w_param, l_param):
        if n_code == 0:
            if w_param in (WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP):
                self.queue.put(("click", w_param))
            elif w_param == WM_MOUSEWHEEL:
                event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                delta = wt.HIWORD(event.mouseData)
                self.queue.put(("scroll", delta))
        return self.user32.CallNextHookEx(self.handle, n_code, w_param, l_param)

    def close(self):
        if self.handle:
            self.user32.UnhookWindowsHookEx(self.handle)
            self.handle = None
"""Windows job-object hard CPU limit for an external engine, not the GUI."""
import ctypes
import os
from ctypes import wintypes


class CpuBudget:
    def __init__(self):
        self.handle = None
        if os.name != 'nt':
            self.api = None
            return
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            'OpenProcess': ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            'AssignProcessToJobObject': ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            'SetInformationJobObject': ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            'CloseHandle': ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result

    def apply(self, pid, percent):
        if type(percent) is not int or not 1 <= percent <= 100:
            raise ValueError('CPU budget must be between 1 and 100 percent')
        if self.api is None:
            if percent != 100:
                raise OSError('CPU budgets require Windows')
            return
        if not self.handle:
            if percent == 100:
                return
            job = self.api.CreateJobObjectW(None, None)
            if not job:
                raise ctypes.WinError(ctypes.get_last_error())
            process = self.api.OpenProcess(0x0100 | 0x0001, False, pid)
            try:
                if not process or not self.api.AssignProcessToJobObject(job, process):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handle = job
            except OSError:
                self.api.CloseHandle(job)
                raise
            finally:
                if process:
                    self.api.CloseHandle(process)
        # JOBOBJECT_CPU_RATE_CONTROL_INFORMATION: flags and CpuRate union.
        # Rate is hundredths of a percent of the entire machine's CPU capacity.
        info = (wintypes.DWORD * 2)(0 if percent == 100 else 0x1 | 0x4, percent * 100)
        if not self.api.SetInformationJobObject(self.handle, 15, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

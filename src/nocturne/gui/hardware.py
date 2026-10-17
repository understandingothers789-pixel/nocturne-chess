"""Conservative memory admission for user-configured UCI hash allocation."""

import os


def hash_budget_mb(allocated_mb=0):
    """Include replaceable hash already acknowledged by the running engine."""
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("load", ctypes.c_ulong),
                    *[
                        (name, ctypes.c_ulonglong)
                        for name in (
                            "total",
                            "available",
                            "total_page",
                            "available_page",
                            "total_virtual",
                            "available_virtual",
                            "extended",
                        )
                    ],
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            total, available = status.total // 1048576, status.available // 1048576
        else:
            page = os.sysconf("SC_PAGE_SIZE")
            total = os.sysconf("SC_PHYS_PAGES") * page // 1048576
            available = os.sysconf("SC_AVPHYS_PAGES") * page // 1048576
        return max(16, min(total - 4096, available + max(0, allocated_mb) - 1024))
    except (OSError, ValueError, AttributeError):
        return None

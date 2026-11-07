"""Conservative memory admission for user-configured UCI hash allocation."""

import os


def has_discrete_gpu(inventory):
    """Recognize NVIDIA/AMD display adapters from the Windows inventory text."""
    names = str(inventory).casefold()
    return any(vendor in names for vendor in ("nvidia", "amd", "radeon"))


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


def automatic_hash_mb(allocated_mb=0, maximum=2048):
    """Grow to the configured ceiling when RAM permits, reserving app headroom.

    Include replaceable engine memory; hash_budget_mb already reserves 1 GB
    of free RAM, and this adds another 3 GB for other applications.
    """
    budget = hash_budget_mb(allocated_mb)
    target = 256 if budget is None else max(16, budget - 3072)
    if target >= maximum:
        return maximum
    # Stable steps avoid frequent small reallocations. The exact configured
    # maximum is reachable even when it is not a power of two.
    return min(maximum, max(16, 1 << max(0, int(target).bit_length() - 1)))

"""Read DirectML adapter indices through DXGI, without guessing WMI ordering."""
import ctypes
import os
import uuid


def directml_adapters():
    if os.name != 'nt':
        return []
    from ctypes import wintypes

    class Guid(ctypes.Structure):
        _fields_ = [('value', ctypes.c_ubyte * 16)]

    class Luid(ctypes.Structure):
        _fields_ = [('low', wintypes.DWORD), ('high', wintypes.LONG)]

    class Description(ctypes.Structure):
        _fields_ = [('name', wintypes.WCHAR * 128), ('vendor', wintypes.UINT),
                    ('device', wintypes.UINT), ('subsystem', wintypes.UINT),
                    ('revision', wintypes.UINT), ('dedicated', ctypes.c_size_t),
                    ('system', ctypes.c_size_t), ('shared', ctypes.c_size_t),
                    ('luid', Luid), ('flags', wintypes.UINT)]

    def method(pointer, index, result, *args):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *args)(table[index])

    factory = ctypes.c_void_p()
    iid = Guid((ctypes.c_ubyte * 16).from_buffer_copy(
        uuid.UUID('770aae78-f26f-4dba-a829-253c83d1b387').bytes_le))
    create = ctypes.WinDLL('dxgi.dll').CreateDXGIFactory1
    create.argtypes = [ctypes.POINTER(Guid), ctypes.POINTER(ctypes.c_void_p)]
    create.restype = wintypes.LONG
    if create(ctypes.byref(iid), ctypes.byref(factory)) < 0:
        raise OSError('DXGI adapter enumeration is unavailable')
    devices = []
    try:
        enumerate_adapter = method(factory, 12, wintypes.LONG, wintypes.UINT,
                                   ctypes.POINTER(ctypes.c_void_p))
        for index in range(32):
            adapter = ctypes.c_void_p()
            result = enumerate_adapter(factory, index, ctypes.byref(adapter))
            if result < 0:
                break
            try:
                description = Description()
                result = method(adapter, 10, wintypes.LONG, ctypes.POINTER(Description))(
                    adapter, ctypes.byref(description))
                if result >= 0:
                    devices.append(dict(index=index, name=description.name,
                                        memory_mb=description.dedicated // 1048576,
                                        vendor=description.vendor,
                                        software=bool(description.flags & 2)))
            finally:
                method(adapter, 2, wintypes.ULONG)(adapter)
    finally:
        method(factory, 2, wintypes.ULONG)(factory)
    return devices


def preferred_adapter(adapters):
    hardware = [item for item in adapters if not item.get('software', False)]
    if not hardware:
        return None
    return max(hardware, key=lambda item: (item.get('memory_mb', 0) > 1024,
                                          item.get('vendor') == 0x1002,
                                          item.get('memory_mb', 0)))

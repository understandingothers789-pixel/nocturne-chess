"""Build the small MIT-licensed local Syzygy probe with the platform compiler."""
import sys
from setuptools import Extension, setup

setup(ext_modules=[Extension(
    "nocturne.engine._syzygy",
    sources=["native/syzygy_module.c", "native/fathom/tbprobe.c"],
    include_dirs=["native/fathom"],
    define_macros=[("TB_NO_THREADS", "1"), ("TB_NO_HW_POP_COUNT", "1"),
                   ("TB_NO_HELPER_API", "1"), ("_CRT_SECURE_NO_WARNINGS", "1")],
    extra_compile_args=["/std:c11", "/experimental:c11atomics"] if sys.platform == "win32" else ["-std=c11"],
)])

# Run on Windows with: python -m PyInstaller --noconfirm Nocturne.spec
from pathlib import Path
import sys

root = Path(SPECPATH)
on_windows = sys.platform == 'win32'
common_data = [
    (str(root / 'src/nocturne/assets'), 'nocturne/assets'),
    (str(root / 'LICENSE'), '.'),
    (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
    (str(root / 'licenses'), 'licenses'),
]
# Retain the binding's installed license texts as well as our release notices.
import PySide6
pyside_licenses = Path(PySide6.__file__).parent / 'licenses'
if pyside_licenses.exists():
    common_data.append((str(pyside_licenses), 'licenses/PySide6'))

gui = Analysis(
    [str(root / 'scripts/launch_gui.py')], pathex=[str(root / 'src')],
    binaries=[], datas=common_data, hiddenimports=["nocturne.engine._syzygy"], hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=['chess', 'pytest', 'numpy', 'tkinter', 'PySide6.QtTest'],
    noarchive=False,
)
gui_pyz = PYZ(gui.pure)
gui_exe = EXE(
    gui_pyz, gui.scripts, [], exclude_binaries=True, name='Nocturne',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'src/nocturne/assets/icon.ico') if on_windows else None,
    version=str(root / 'scripts/windows-version.txt') if on_windows else None,
)
COLLECT(gui_exe, gui.binaries, gui.datas, strip=False, upx=False, name='Nocturne')

uci = Analysis(
    [str(root / 'scripts/launch_uci.py')], pathex=[str(root / 'src')],
    binaries=[], datas=[(str(root / 'LICENSE'), '.'),
                        (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
                        (str(root / 'licenses'), 'licenses')], hiddenimports=["nocturne.engine._syzygy"],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6', 'chess', 'pytest', 'numpy', 'tkinter'], noarchive=False,
)
uci_pyz = PYZ(uci.pure)
uci_exe = EXE(
    uci_pyz, uci.scripts, [], exclude_binaries=True, name='Nocturne-UCI',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True,
    icon=str(root / 'src/nocturne/assets/icon.ico') if on_windows else None,
    version=str(root / 'scripts/windows-version.txt') if on_windows else None,
)
COLLECT(uci_exe, uci.binaries, uci.datas, strip=False, upx=False, name='Nocturne-UCI')

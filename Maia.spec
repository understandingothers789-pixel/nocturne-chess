from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata
root = Path(SPECPATH)
a = Analysis([str(root / 'scripts/launch_maia.py')], pathex=[str(root / 'src')],
    excludes=['PySide6', 'tkinter', 'pytest', 'matplotlib', 'IPython', 'tensorboard'],
    datas=[(str(root / 'licenses/Maia3-AGPL-3.0.txt'), 'licenses')]
          + copy_metadata('torch') + copy_metadata('numpy'))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='NocturneMaia',
    console=True, upx=False, strip=False)
COLLECT(exe, a.binaries, a.datas, name='Maia', upx=False, strip=False)

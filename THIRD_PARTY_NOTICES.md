# Distribution notices

The custom Nocturne rules, engine, interface, SVG chess pieces and application
icon are original project code/assets, distributed under the MIT license in
`LICENSE`. No external engine or chess book is bundled.

## Runtime

* **Python**: Python Software Foundation License. The actual Python runtime's
  license text is retained in `licenses/PYTHON-LICENSE.txt`.
  https://www.python.org/psf/license/
* **PySide6 / Shiboken6 6.8.3**: Qt for Python, LGPL-3.0-only, GPL-3.0-only, or a
  commercial license, according to the component. https://doc.qt.io/qtforpython-6/licenses.html
* **Qt 6.8.3**: Qt Core, GUI, Widgets and SVG, with platform plugins and their
  dependencies. Preserve the applicable module and third-party notices from
  the installed distribution. https://doc.qt.io/qt-6/licensing.html

The packaging configuration uses a directory distribution with shared Qt
libraries, excludes unused Qt modules, includes the installed binding's license
directory when present, and includes LGPLv3/GPLv3 texts in `licenses/`.
Recipients can replace shared libraries and may exercise their rights under
the applicable licenses. For a distributed release, retain the exact version,
source availability information, Qt third-party notices, and the PSF notices
collected by PyInstaller. Qt/PySide source: https://download.qt.io/official_releases/
and https://code.qt.io/pyside/pyside-setup.git/ (tag `v6.8.3`).

## Build and development only

* **PyInstaller**: GPL-2.0-or-later with a bootloader exception permitting
  distribution of built applications under their own license. https://pyinstaller.org/en/stable/license.html
* **pytest / pytest-qt / Ruff**: MIT licensed developer tools, not bundled.
* **python-chess / chess**: GPL-3.0-or-later, used only as an optional independent
  testing oracle. Not imported by the app and explicitly excluded from bundles.
  https://python-chess.readthedocs.io/

## Optional external engines

Stockfish or another UCI executable must be selected from the user's own local
installation. No binary is downloaded or redistributed by Nocturne. Stockfish
is GPLv3; see https://stockfishchess.org/about/ and preserve its notices if you
separately distribute it. Nocturne's custom engine remains independent.

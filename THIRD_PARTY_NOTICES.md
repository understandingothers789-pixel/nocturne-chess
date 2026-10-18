# Distribution notices · Nocturne Analysis 0.5

The combined analysis application is distributed under GPL-3.0-or-later (COPYING)
because of its runtime python-chess dependency. Original Nocturne code and application
icon retain their MIT license grant (LICENSE). The bundled Cburnett pieces are
GPL-2.0-or-later, credited separately below. No Nibbler implementation
or assets, and no Stockfish executable/neural network/table files are bundled.

## Runtime

- **python-chess / chess 1.11.2**, Nikolaus Fiekas and contributors:
  GPL-3.0-or-later. `licenses/PYTHON-CHESS-LICENSE.txt`, `COPYING`.
  https://github.com/niklasf/python-chess/tree/v1.11.2
  https://pypi.org/project/chess/1.11.2/#files
  The corresponding Python modules are included in the release source archive
  under `dependencies/python-chess/chess/`. This is a rules/PGN library; the GUI
  supplies no search engine through it.
- **Python 3.12**: Python Software Foundation License. Retain
  `licenses/PYTHON-LICENSE.txt` and PyInstaller-collected runtime notices.
  https://www.python.org/psf/license/
- **PySide6 / Shiboken6 6.8.3, Qt 6.8.3**: LGPL-3.0-only/GPL-3.0-only or commercial
  terms according to component. Binding and module third-party notices from the
  installed distribution are retained when present, along with GPL/LGPL texts.
  https://doc.qt.io/qtforpython-6/licenses.html
  https://download.qt.io/official_releases/QtForPython/pyside6/
  https://code.qt.io/pyside/pyside-setup.git/ (v6.8.3)
  https://download.qt.io/official_releases/qt/6.8/6.8.3/single/

The directory distribution retains shared Qt libraries; recipients can replace
them and exercise their rights under the applicable licenses. Application source
is in the repository and accompanying source ZIP. Preserve notices and equivalent
source access when redistributing.

## Development and historical source only

- PyInstaller: GPL-2.0-or-later with its bootloader exception.
  https://pyinstaller.org/en/stable/license.html
- pytest, pytest-qt, Ruff, setuptools: development/build tooling, not runtime engines.
- Historical 0.4 native Fathom reader: MIT, pinned commit
  c9c6fef0dddc05d2e242c183acf5833149ab676d, https://github.com/jdart1/Fathom.
  Its source/license remain in the source archive; it is excluded from the 0.5 GUI.
- The UCI simulator is explicitly a development/test fixture, not a playing engine.
  It is not included in the application bundle.

Nibbler was inspected for behavior and workflow only. Its GPL code/assets were not
copied. User-selected external engines retain their respective licenses; this
application does not distribute or modify them.

### Lichess opening explorer service

Optional online integration calls https://explorer.lichess.org/masters and
/lichess according to https://lichess.org/api#tag/Opening-Explorer. Statistics
are credited to Lichess in the interface and cached locally on user request.
No server implementation, database dump or game collection is bundled. The
Lichess name identifies the service and does not imply endorsement.

### ChessDB cloud database service

Optional queries use https://www.chessdb.cn/cdb.php according to
https://chessdb.cn/cloudbookc_api_en.html. The interface credits ChessDB; no
server code or database dump is bundled. Lookups use queryall with learning
disabled. Service results are kept separate from local engine evaluations.

### Review metric references

The independent Python review implementation uses numerical score/accuracy curves
published by Lichess, with Nocturne-specific aggregation, classifications and
same-root search comparisons. No Lichess server/Scala code is bundled.
The estimates differ from Lichess game accuracy and are not endorsed by Lichess.
Method and upstream references: docs/REVIEW.md.


### Cburnett chess pieces from Lichess

The optional Original piece style in `assets/pieces/original` restores Nocturne's
own MIT SVG artwork from source commit b00711c9f41c67362d1afab3f176e9a6f81dad1e.
The default Cburnett pieces below retain their separate license and attribution.

All twelve SVG pieces are the exact Cburnett set by Colin M. L. Burnett, licensed
GPL-2.0-or-later. Source files are unchanged; filenames are normalized to lowercase.
Pinned upstream source:
https://github.com/lichess-org/lila/tree/cd2656d2787a766ba743da8da1dd3b24975e6329/public/piece/cburnett
The upstream COPYING.md exceptions table credits Colin M.L. Burnett and GPLv2+.
Retain licenses/CBURNETT-NOTICE.txt and
licenses/CBURNETT-GPL-2.0-or-later.txt, which accompany the native app, wheel and
source archive. The SVGs themselves are the preferred modifiable artwork source.
No Chess.com or Nibbler artwork is included; no Lichess endorsement is implied.

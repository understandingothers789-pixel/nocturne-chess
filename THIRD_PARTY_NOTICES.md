# Distribution notices · Nocturne Analysis 0.5

The combined analysis application is distributed under GPL-3.0-or-later (COPYING)
because of its runtime python-chess dependency. Original Nocturne code and application
icon retain their MIT license grant (LICENSE). The bundled Cburnett pieces are
GPL-2.0-or-later, credited separately below. The Nibbler/Merida piece images are
credited below; no Nibbler implementation or Stockfish executable/neural network/
table files are bundled.

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

The Nibbler option is the default: matching shaded Merida vectors are rendered
at device resolution; Nibbler's 12 original PNGs are retained as references. No Nibbler application code is copied. See the piece notice below.
User-selected external engines retain their respective licenses; this application
does not distribute or modify them.

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
This Cburnett set contains no Chess.com artwork; no Lichess endorsement is implied.
The separate Nibbler/Merida artwork is credited below.


### Nibbler / shaded Merida chess pieces (default)

Exact, unmodified PNGs from rooklift/nibbler commit
`6eb0f066402c0cf53d08d682dbc394acd9cb5fb9`, `files/src/pieces/` (GPL-3.0 repository).
Nibbler credits Lichess for these pieces. Merida is credited by Lichess to Armando
Hernandez Marroquin under GPL-2.0-or-later; shaded artwork also credits Felix Kling.
See `licenses/NIBBLER-PIECES-NOTICE.txt`, `licenses/MERIDA-GPL-2.0-or-later.txt`
and `licenses/GPL-3.0.txt`. The PNGs and upstream editable Merida SVGs are included
in `assets/pieces/nibbler/` and the accompanying source archive. Since 0.5.7.18,
the matching SVGs in `source/` provide runtime rendering at native display
resolution; original 240×240 PNGs remain archival references. No endorsement.

## Maia-3 79M (optional local prediction worker)

Maia-3 architecture/tokenization components in `src/nocturne/maia/vendor/`
are unmodified from [CSSLab/maia3](https://github.com/CSSLab/maia3), revision
`1e13597c42d4858b7cfd7cfdae01e297263364b2`, by the University of Toronto CSSLab.
They and the [official Maia3-79M checkpoint](https://huggingface.co/UofTCSSLab/Maia3-79M)
are licensed under AGPL-3.0; see `licenses/Maia3-AGPL-3.0.txt`.
The checkpoint is pinned to revision `a107d6ceb7b298cb04ae1da4edffe2939858b894`.
The corresponding worker source and upstream components accompany each Windows
build in its source ZIP. The local worker uses PyTorch (BSD-style license) and
NumPy (BSD-3-Clause); their license texts accompany the worker distribution.
Maia predicts human move likelihood. Its probabilities are not Stockfish evaluations.

## Lichess chess notation font

Game Line uses the Lichess/pgn4web notation glyphs from public/font/lichess-chess.woff2
in https://github.com/lichess-org/lila (GPL-2.0-or-later; see licenses/LICHESS-NOTATION-NOTICE.txt).
The bundled TTF preserves glyph outlines; only font-container conversion and family naming changed.

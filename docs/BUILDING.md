# Reproducible desktop builds

## Windows 11 / Python 3.12 x64

### For players

[Previous Windows test artifact (0.3.1)](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38960506947/artifacts/12073040643).
GitHub sign-in is required.

The user has opted into an unsigned Windows test executable. Open the latest
successful [Windows workflow run](https://github.com/understandingothers789-pixel/nocturne-chess/actions),
then download **Nocturne-0.3.2-Windows-x64-unsigned** under Artifacts. GitHub
requires you to be signed in. Extract the whole ZIP, then open
`Nocturne/Nocturne.exe`. Keep the accompanying `_internal` directory in place.
No Python installation or launcher scripts are required.

This is an unsigned test build and Windows may display a SmartScreen warning.
It is not a signed release. Artifacts expire after 30 days; rerun the workflow
to generate another. The signed release verification procedure below remains
available for future distribution.

### For developers building on Windows

The command below is for a developer who has the project source on a Windows
machine. It validates the build locally; it does not create a signed release.

Install Python 3.12 x64 with the Python launcher. To compile and test locally:

```text
py -3.12 scripts/build_windows.py --build-only
```

The tool creates `.venv-build`, installs pinned build/validation dependencies,
runs Ruff and the test suite, renders the application icon, and runs
`Nocturne.spec`. It smoke-tests the packaged GUI and UCI endpoint. This mode
creates local validation directories; it does not create a Windows release ZIP.
The CI workflow uses this mode and uploads successful unsigned test builds.

Before distribution, sign all `.exe`, `.dll` and `.pyd` files in the two
application directories using a legitimately issued, trusted code-signing
certificate or signing service, with trusted timestamps. No signing certificate
is generated/imported by Nocturne and no Windows protection is disabled.
After signing, use the installed Windows SDK SignTool to verify and package:

```text
py -3.12 scripts/build_windows.py --package-signed --signtool "C:\path\to\signtool.exe"
```

SignTool must accept every native file under the Authenticode trust policy;
missing/untrusted signatures and timestamp warnings stop packaging. Smoke
checks must also pass. The resulting `dist/Nocturne-0.3.2-win64-signed.zip`
contains the windowed `Nocturne/Nocturne.exe` and console
`Nocturne-UCI/Nocturne-UCI.exe`, plus their runtime directories and notices.
No launcher scripts are included. Unsigned or failed builds are not packaged
as Windows releases.

Valid signing does not guarantee the absence of Windows SmartScreen prompts:
Windows also applies publisher/file reputation and local policies. No signing
or warning-free Windows launch has been established in this environment.

The app uses shared Qt libraries in a directory bundle. Do not copy the `.exe`
alone. Libraries and notices must remain with it. No Stockfish executable is
downloaded or included. Build requirements need internet access once; playing
does not. For an air-gapped build, prepare a wheelhouse on a matching Windows
Python/architecture and set pip's `PIP_NO_INDEX` / `PIP_FIND_LINKS` accordingly.

The checked-in GitHub Actions workflow completed successfully on Windows in
run [#1](https://github.com/understandingothers789-pixel/nocturne-chess/actions/runs/38952576627).
It installed dependencies, passed Ruff and the full automated suite, built both
PyInstaller apps, and passed GUI/UCI smoke checks. That first run did not retain an artifact; subsequent runs now retain unsigned
test builds with user authorization. Signed distribution requires trusted signing and the separate
verification/packaging step above.

## Linux validation performed here

```sh
QT_QPA_PLATFORM=offscreen python scripts/make_icon.py
PYINSTALLER_CONFIG_DIR=/workspace/.pyinstaller-cache python -m PyInstaller --noconfirm --clean Nocturne.spec
QT_QPA_PLATFORM=offscreen dist/Nocturne/Nocturne --smoke-test
```

Both Linux executables were built; the packaged GUI played a legal human/AI
pair and exited 0. The packaged UCI executable completed handshake, depth-2
search and returned a move validated by the custom rules core. This validates
the build graph/assets and frozen process spawning on Linux. It is not a
Windows executable, a Windows test, or a cross-compiled release.

The pure Python wheel can also be built without fetching dependencies:

```sh
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
```

Setuptools must already be installed for `--no-build-isolation`.

## Release checks still requiring Windows

Manually check drag/drop and promotion, board resize at 100/150/200% DPI, clocks
through suspend/resume, cancellation on close/new game, library permissions,
and an explicitly installed UCI engine. Check the signed archive on a clean
Windows 11 machine without Python. Trusted signing is a release requirement. A
conventional installer remains future release work.

Preserve Qt's applicable license/source-availability notices and the supplied
license texts. Review the exact platform libraries collected by PyInstaller
before distribution. The pinned build describes dependency versions and steps;
byte-identical binaries across machines are not promised.

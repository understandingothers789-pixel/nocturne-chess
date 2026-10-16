# Reproducible desktop builds

## Windows 11 / Python 3.12 x64

### For players

There is no Windows app available to download from this workspace yet. The
`dist/Nocturne/Nocturne` file built here is for Linux and will not run on
Windows. The project is not connected to a GitHub repository, so its Windows
workflow has not run. Do not open that Linux file on Windows.

A Windows release must be built on Windows and signed with a trusted code
signing identity before it can be offered as a safety-checked download. This
workspace has neither a Windows build machine nor a signing identity. I cannot
promise a warning-free Windows executable until those are available. No batch
or PowerShell launchers and no warning-bypass steps are used.

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
The CI workflow uses this mode and does not upload unsigned application builds.

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
checks must also pass. The resulting `dist/Nocturne-0.3.0-win64-signed.zip`
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

The checked-in GitHub Actions workflow installs the oracle/test tools, runs
headless Qt tests and Ruff, then validates a developer build. Creating or
editing the workflow file did not execute GitHub Actions. Signed distribution
requires the separate verification/packaging step above.

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

Run the developer build, then manually check drag/drop and promotion, board resize at
100/150/200% DPI, clocks through suspend/resume, cancellation on close/new game,
library permissions, and an explicitly installed UCI engine. Check the built
signed archive on a clean Windows 11 machine without Python. Trusted signing
is a release requirement. A conventional installer remains future release work.

Preserve Qt's applicable license/source-availability notices and the supplied
license texts. Review the exact platform libraries collected by PyInstaller
before distribution. The pinned build describes dependency versions and steps;
byte-identical binaries across machines are not promised.

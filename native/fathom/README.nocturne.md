Fathom local Syzygy reader, MIT licensed.
Upstream: https://github.com/jdart1/Fathom
Pinned commit: c9c6fef0dddc05d2e242c183acf5833149ab676d
All upstream source headers retained. Local change: Windows open_tb uses
MultiByteToWideChar(CP_UTF8) and CreateFileW for Unicode tablebase paths.
The CPython wrapper serializes probes and releases the GIL. TB_NO_THREADS
is safe under this wrapper lock. No tablebase files are bundled in the app.

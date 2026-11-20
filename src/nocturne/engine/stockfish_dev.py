"""Install the official Stockfish development release for Windows."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

REPOSITORY = "https://github.com/official-stockfish/Stockfish"
RELEASES = "https://api.github.com/repos/official-stockfish/Stockfish/releases?per_page=30"
MAX_DOWNLOAD = 512 * 1024 * 1024


def _open(url):
    return urlopen(Request(url, headers={"User-Agent": "Nocturne Chess"}), timeout=20)


def install_development(root, architecture, status):
    filename = f"stockfish-windows-{architecture}-universal.zip"
    status("Checking official Stockfish releases…")
    with _open(RELEASES) as response:
        releases = json.load(response)
    release = next((release for release in releases if release["prerelease"]
                    and re.fullmatch(r"stockfish-dev-\d{8}-[a-f0-9]+", release["tag_name"])
                    and not release["draft"]), None)
    if release is None:
        raise ValueError("No official Stockfish development release was found.")
    tag = release["tag_name"]
    asset = next((asset for asset in release["assets"] if asset["name"] == filename), None)
    if asset is None:
        raise ValueError(f"{tag} has no Windows {architecture} download.")
    url = f"{REPOSITORY}/releases/download/{tag}/{filename}"
    digest = asset.get("digest") or ""
    size = asset["size"]
    if (asset["browser_download_url"] != url or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
            or not 0 < size <= MAX_DOWNLOAD):
        raise ValueError("The official release did not provide valid download verification data.")

    executable = Path(filename).with_suffix(".exe").name
    destination = root / tag / architecture
    installed = destination / executable
    if installed.is_file():
        return tag, installed
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        archive = Path(folder) / filename
        staged = Path(folder) / "stockfish"
        staged.mkdir()
        status(f"Downloading {tag} ({size / 1024**2:.0f} MB)…")
        check = hashlib.sha256()
        total = 0
        deadline = time.monotonic() + 300
        with _open(url) as response, archive.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > size or time.monotonic() > deadline:
                    raise ValueError("The download exceeded its expected size or time limit.")
                check.update(chunk)
                output.write(chunk)
        if total != size or f"sha256:{check.hexdigest()}" != digest:
            raise ValueError("The download does not match the official release checksum.")

        status("Verifying and installing Stockfish…")
        with ZipFile(archive) as source:
            matches = [entry for entry in source.infolist()
                       if not entry.is_dir() and PurePosixPath(entry.filename).name == executable]
            if len(matches) != 1 or matches[0].file_size > MAX_DOWNLOAD:
                raise ValueError("The archive does not contain the expected Stockfish executable.")
            with source.open(matches[0]) as binary, (staged / executable).open("wb") as output:
                shutil.copyfileobj(binary, output)
        if os.name == "nt":
            # Keep Windows' internet origin marker on the installed executable.
            with open(str(staged / executable) + ":Zone.Identifier", "w", encoding="ascii") as marker:
                marker.write(f"[ZoneTransfer]\nZoneId=3\nHostUrl={url}\n")
        try:
            staged.rename(destination)
        except OSError:
            if not installed.is_file():
                raise
    return tag, installed

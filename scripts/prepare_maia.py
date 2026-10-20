"""Download the pinned official checkpoint and verify its upstream LFS digest."""
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

from nocturne.maia import MODEL_REVISION, MODEL_URL


def main():
    folder = Path(__file__).resolve().parents[1] / "models"
    folder.mkdir(exist_ok=True)
    with urlopen(Request(
        f"https://huggingface.co/api/models/UofTCSSLab/Maia3-79M/revision/{MODEL_REVISION}?blobs=true",
        headers={"User-Agent": "Nocturne-Chess-build"}), timeout=60) as response:
        metadata = json.load(response)
    info = next(f for f in metadata["siblings"] if f["rfilename"] == "maia3-79m.pt")
    expected = info["lfs"]["sha256"]
    target = folder / "maia3-79m.pt"
    if not target.exists() or hashlib.file_digest(target.open("rb"), "sha256").hexdigest() != expected:
        temporary = target.with_suffix(".download")
        with urlopen(MODEL_URL, timeout=180) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if hashlib.file_digest(temporary.open("rb"), "sha256").hexdigest() != expected:
            temporary.unlink()
            raise RuntimeError("Official Maia checkpoint checksum mismatch")
        temporary.replace(target)
    print(f"Official Maia-3 79M: {target.stat().st_size:,} bytes, SHA-256 {expected}")


if __name__ == "__main__":
    main()

"""Explicit developer-only download of small, pinned Syzygy test fixtures.

Never called by the app. Files are not bundled in the Windows executable.
Reference table data from tablebase.sesse.net, mirrored by python-chess.
"""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

PIN = "0c6bdaccfcb3b09cdbe94b0f81e948cb2a356015"
FILES = [
    {
        "name": "KBvK.rtbw",
        "sha": "95919ca67c5255bfad2f93e820824ffe7a8c6ecd"
    },
    {
        "name": "KBvK.rtbz",
        "sha": "d48c792039bcc55e2d91e209637fe8e14310cf3f"
    },
    {
        "name": "KNvK.rtbw",
        "sha": "c2d9633254334a912dd546b313073215811e3fc1"
    },
    {
        "name": "KNvK.rtbz",
        "sha": "98383d656af5c441b64d2f967f6fcf1c20f8c3c9"
    },
    {
        "name": "KPvK.rtbw",
        "sha": "1af4d64c187464d79749bd7a9ef4e3c017d2508c"
    },
    {
        "name": "KPvK.rtbz",
        "sha": "06e9217b4e0c4c9fe10affd5d4039a6b0971795a"
    },
    {
        "name": "KQvK.rtbw",
        "sha": "0f4b29211eddd62f33b88471420f2674b35a5164"
    },
    {
        "name": "KQvK.rtbz",
        "sha": "507469523978f81d52701a12cddb47545865f242"
    },
    {
        "name": "KRvK.rtbw",
        "sha": "2a2855ae9521d28365f91fd611c55e828dbd0267"
    },
    {
        "name": "KRvK.rtbz",
        "sha": "6cd8607aacddaca6285ca5ec3904e71f2012411b"
    }
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(".tb-test-fixtures"))
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for item in FILES:
        url = f"https://raw.githubusercontent.com/niklasf/python-chess/{PIN}/data/syzygy/regular/{item['name']}"
        with urlopen(url, timeout=30) as response:
            data = response.read(1_000_000)
        digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if digest != item["sha"]:
            raise RuntimeError(f"Fixture integrity check failed: {item['name']}")
        (args.destination / item["name"]).write_bytes(data)
    print(f"Verified {len(FILES)} development-only table fixtures in {args.destination}")

if __name__ == "__main__":
    main()


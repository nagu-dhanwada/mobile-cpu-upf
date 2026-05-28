#!/usr/bin/env python3
"""Install the Nangate45 reference Liberty files used by the mapped demo flow."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


BASE_URL = "https://raw.githubusercontent.com/The-OpenROAD-Project/alpha-release/master/flow/platforms/nangate45"
FILES = {
    "NangateOpenCellLibrary_typical.lib": f"{BASE_URL}/NangateOpenCellLibrary_typical.lib",
    "NangateOpenCellLibrary.blackbox.v": f"{BASE_URL}/NangateOpenCellLibrary.blackbox.v",
    "OpenCellLibraryLicenseSi2.txt": f"{BASE_URL}/OpenCellLibraryLicenseSi2.txt",
}


def download(url: str, path: Path, force: bool) -> None:
    if path.exists() and not force:
        print(f"exists {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"download {url}")
    with urllib.request.urlopen(url, timeout=60) as response:
        path.write_bytes(response.read())
    print(f"wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("third_party/nangate45"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    written = {}
    for filename, url in FILES.items():
        path = args.out / filename
        download(url, path, args.force)
        written[filename] = {"path": str(path), "source": url}

    manifest = {
        "name": "nangate45",
        "source": BASE_URL,
        "files": written,
    }
    (args.out / "install_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out / 'install_manifest.json'}")


if __name__ == "__main__":
    main()

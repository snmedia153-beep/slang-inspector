"""Build-time only: fetch pinned OCR files, verify SHA-256, never download at runtime."""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path


def main():
    manifest = json.loads(Path(sys.argv[1]).read_text("utf-8"))
    target = Path(sys.argv[2])
    target.mkdir(parents=True, exist_ok=True)
    for item in manifest["files"]:
        if Path(item["name"]).name != item["name"]:
            raise ValueError("Model filename must be a basename")
        url = f"{manifest['source']}/resolve/{manifest['revision']}/{item['path']}"
        path = target / item["name"]
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=90) as response, path.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != item["sha256"]:
            path.unlink()
            raise ValueError(f"OCR file checksum mismatch: {item['name']}")
        print(f"Verified OCR file: {item['name']}", flush=True)


if __name__ == "__main__":
    main()

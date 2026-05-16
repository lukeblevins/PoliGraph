import sys
import tarfile
import tempfile
from pathlib import Path

import requests

RELEASE_URL = (
    "https://github.com/lukeblevins/PoliGraph/releases/download"
    "/extra-data-v1/poligrapher-extra-data.tar.gz"
)

REQUIRED = {"entity_info.json", "named_entity_recognition", "purpose_classification"}


def main():
    import poligrapher

    pkg_dir = Path(poligrapher.__file__).parent
    extra_data = pkg_dir / "extra-data"

    already_present = {p.name for p in extra_data.iterdir()} if extra_data.exists() else set()
    if REQUIRED.issubset(already_present):
        print("Extra data already present, nothing to do.")
        return

    print(f"Downloading extra data from GitHub Release ...")

    with requests.get(RELEASE_URL, stream=True) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))

        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                tmp.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    mb = downloaded // 1024 ** 2
                    total_mb = total // 1024 ** 2
                    print(f"\r  {pct:.1f}%  ({mb} / {total_mb} MB)", end="", flush=True)
            tmp_path = Path(tmp.name)

    print(f"\nExtracting to {extra_data} ...")
    extra_data.mkdir(exist_ok=True)

    with tarfile.open(tmp_path) as tf:
        # Tarball is rooted at extra-data/; strip that prefix when extracting.
        members = tf.getmembers()
        for m in members:
            parts = Path(m.name).parts
            if len(parts) < 2:
                continue
            m.name = str(Path(*parts[1:]))
        tf.extractall(extra_data, members=[m for m in members if m.name])

    tmp_path.unlink()
    print("Done.")


if __name__ == "__main__":
    main()

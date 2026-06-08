"""
Install GMP headers/libs into the Windows GnuCOBOL tree for COMP-3 (PACKED-DECIMAL).

The SuperBOL / GnuCOBOL AIO installer often ships libgmp-10.dll but omits gmp.h and
link libraries. Behavioral COBOL compile then fails with: gmp.h: No such file or directory.

This script downloads mingw-w64-gmp from MSYS2 and copies:
  - include/gmp.h
  - lib/libgmp.a, lib/libgmp.dll.a
into %LOCALAPPDATA%\\GnuCOBOL\\include and \\lib.
"""

from __future__ import annotations

import os
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.gnucobol_gmp_runtime import gnucobol_root, gmp_runtime_ready

GMP_PKG_URL = (
    "https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-gmp-6.3.0-2-any.pkg.tar.zst"
)
FILES_TO_INSTALL = (
    ("mingw64/include/gmp.h", "include/gmp.h"),
    ("mingw64/lib/libgmp.a", "lib/libgmp.a"),
    ("mingw64/lib/libgmp.dll.a", "lib/libgmp.dll.a"),
)


def _decompress_zst(pkg_path: Path) -> bytes:
    try:
        import zstandard as zstd
    except ImportError:
        import subprocess

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "zstandard", "-q"],
            stdout=subprocess.DEVNULL,
        )
        import zstandard as zstd

    with pkg_path.open("rb") as handle:
        decompressor = zstd.ZstdDecompressor()
        with decompressor.stream_reader(handle) as reader:
            return reader.read()


def install_gmp(*, force: bool = False) -> int:
    root = gnucobol_root()
    if root is None:
        print("[ensure-gmp] GnuCOBOL not found at %LOCALAPPDATA%\\GnuCOBOL", file=sys.stderr)
        return 1

    ready, msg = gmp_runtime_ready(root)
    if ready and not force:
        print(f"[ensure-gmp] GMP runtime already present under {root}")
        return 0

    import tempfile
    import urllib.request

    print(f"[ensure-gmp] Downloading {GMP_PKG_URL}")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        pkg_path = tmp_path / "gmp.pkg.tar.zst"
        urllib.request.urlretrieve(GMP_PKG_URL, pkg_path)
        tar_bytes = _decompress_zst(pkg_path)
        tar_path = tmp_path / "gmp.pkg.tar"
        tar_path.write_bytes(tar_bytes)
        with tarfile.open(tar_path, "r") as archive:
            for src, dest_rel in FILES_TO_INSTALL:
                member = archive.getmember(src)
                payload = archive.extractfile(member)
                if payload is None:
                    print(f"[ensure-gmp] missing member {src}", file=sys.stderr)
                    return 1
                dest = root / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(payload.read())
                print(f"[ensure-gmp] installed {dest}")

    ready, msg = gmp_runtime_ready(root)
    if not ready:
        print(f"[ensure-gmp] verify failed: {msg}", file=sys.stderr)
        return 1
    print("[ensure-gmp] GMP headers and link libraries ready for cobc COMP-3")
    return 0


if __name__ == "__main__":
    force = "--force" in sys.argv
    raise SystemExit(install_gmp(force=force))

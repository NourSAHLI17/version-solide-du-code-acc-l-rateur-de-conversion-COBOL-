"""Safe Java file persistence (validate before write)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Union

from app.services.java_pre_write_validator import write_java_file

PathLike = Union[str, Path]


def write_validated_java_files(files: Dict[str, str], base_dir: PathLike) -> None:
    """Write multiple Java files under *base_dir* after validating each."""
    root = Path(base_dir)
    for filename, source in files.items():
        write_java_file(root / filename, source)

#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.admin_api import create_backup, ensure_admin_foundation


def main() -> None:
    ensure_admin_foundation()
    result = create_backup("cli")
    print(f"Backup created: {result['filename']}")
    print(f"Compressed copy: {result['zip_filename']}")
    print(f"Backup folder: {Path(result['path']).parent}")


if __name__ == "__main__":
    main()

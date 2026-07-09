#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.admin_api import BACKUP_DIR, DATABASE_URL, is_postgres_url, sqlite_path


def unpack_if_zip(path: Path) -> Path:
    if path.suffix != ".zip":
        return path
    temp_dir = Path(tempfile.mkdtemp(prefix="irm_restore_"))
    with zipfile.ZipFile(path) as archive:
        archive.extractall(temp_dir)
    files = [p for p in temp_dir.iterdir() if p.is_file()]
    if len(files) != 1:
        raise SystemExit("Backup zip must contain exactly one database backup file.")
    return files[0]


def confirm_twice(target: str) -> None:
    print("Restore is destructive. Stop the app before continuing.")
    first = input(f"Type RESTORE to replace {target}: ")
    second = input("Type RESTORE again to confirm: ")
    if first != "RESTORE" or second != "RESTORE":
        raise SystemExit("Restore cancelled.")


def restore_sqlite(backup: Path) -> None:
    destination = sqlite_path()
    confirm_twice(str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        safety = destination.with_suffix(destination.suffix + ".pre_restore")
        shutil.copy2(destination, safety)
        print(f"Safety copy created: {safety}")
    shutil.copy2(backup, destination)
    print(f"SQLite database restored to {destination}")


def restore_postgres(backup: Path) -> None:
    confirm_twice("PostgreSQL DATABASE_URL")
    if backup.suffix == ".dump":
        cmd = ["pg_restore", "--clean", "--if-exists", "--dbname", DATABASE_URL, str(backup)]
    else:
        cmd = ["psql", DATABASE_URL, "-f", str(backup)]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print("PostgreSQL database restored.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore an IRM database backup with two confirmations.")
    parser.add_argument("backup", help="Backup filename in app/backups or full path")
    args = parser.parse_args()
    backup = Path(args.backup)
    if not backup.exists():
        backup = BACKUP_DIR / args.backup
    if not backup.exists():
        raise SystemExit(f"Backup not found: {args.backup}")
    backup = unpack_if_zip(backup)
    if is_postgres_url():
        restore_postgres(backup)
    else:
        restore_sqlite(backup)


if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable


ARTIFACT_DIR = Path("artifacts/database")
CONFIG_DIR = Path("config/master_data")


def normalize_value(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[\s,.;:]+$", "", text)
    return text.casefold()


def trimmed_value(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def read_mapping(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def approved(value: object) -> bool:
    return str(value or "").strip().casefold() in {"true", "yes", "1", "approved"}

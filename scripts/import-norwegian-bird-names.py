#!/usr/bin/env python3
"""Import BirdLife Norge's NNKF workbook into BirdFrame's local name map.

The workbook is an .xlsx file, but this importer intentionally uses only the
Python standard library so it also works in the small BirdFrame container.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def shared_strings(archive: ZipFile) -> list[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall("m:si", NS)]


def import_workbook(source: Path) -> dict[str, str]:
    with ZipFile(source) as archive:
        strings = shared_strings(archive)
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = sheet.findall(".//m:sheetData/m:row", NS)
        if not rows:
            raise ValueError("Workbook has no rows")

        def value(cell: ET.Element) -> str:
            raw = cell.find("m:v", NS)
            text = raw.text if raw is not None and raw.text else ""
            return strings[int(text)] if cell.get("t") == "s" and text else text

        headers = {cell.get("r", "")[0]: value(cell) for cell in rows[0].findall("m:c", NS)}
        scientific_column = next((column for column, name in headers.items() if name.lower() == "scientific_name"), None)
        norwegian_column = next((column for column, name in headers.items() if name.lower() == "norskavilistv1"), None)
        if not scientific_column or not norwegian_column:
            raise ValueError("Workbook must contain Scientific_name and norskAviListv1 columns")

        result: dict[str, str] = {}
        for row in rows[1:]:
            values = {cell.get("r", "")[0]: value(cell).strip() for cell in row.findall("m:c", NS)}
            scientific, norwegian = values.get(scientific_column, ""), values.get(norwegian_column, "")
            if scientific and norwegian:
                result[" ".join(scientific.split())] = " ".join(norwegian.split())
        return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print("Usage: import-norwegian-bird-names.py NNKF.xlsx [output.json]", file=sys.stderr)
        return 2
    source = Path(sys.argv[1])
    output = Path(sys.argv[2]) if len(sys.argv) == 3 else Path("backend/birdframe/data/no_names.json")
    names = import_workbook(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(names, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Imported {len(names)} Norwegian bird names into {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

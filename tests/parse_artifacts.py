#!/usr/bin/env python3
"""Parse test artifact files and emit a JSON summary.

- Scans a directory (default: tests/_artifacts) or a list of files.
- For each file, finds the last JSON object/array line and returns it.
- Outputs a compact JSON array of {file, data} objects.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _extract_last_json_line(text: str) -> Any | None:
    last = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            val = json.loads(line)
        except Exception:
            continue
        last = val
    return last


def _iter_files(args: list[str]) -> list[Path]:
    if not args:
        base = Path("tests/_artifacts")
        exists = base.exists()
        if not exists:
            return []
        files: list[Path] = []
        for p in sorted(base.iterdir()):
            if p.is_file():
                files.append(p)
        return files
    out: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            for x in sorted(p.iterdir()):
                if x.is_file():
                    out.append(x)
            continue
        if p.exists():
            out.append(p)
    return out


def main(argv: list[str]) -> int:
    files = _iter_files(argv)
    results: list[dict[str, Any]] = []
    for p in files:
        try:
            data = _extract_last_json_line(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            data = None
        results.append({"file": str(p), "data": data})
    print(json.dumps(results, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

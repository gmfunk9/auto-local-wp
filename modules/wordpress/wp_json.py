"""Helpers for extracting clean JSON from noisy WP-CLI output.

Single-responsibility: text processing only. Callers run commands.
"""

from __future__ import annotations

from typing import Optional


def extract_json_blob(s: str) -> Optional[str]:
    """Return the first balanced JSON object/array found in text.

    Scans for the earliest '[' or '{' and returns the substring spanning
    the matching bracket/brace, tolerating strings and escapes.
    Returns None if no balanced JSON is found.
    """
    if not s:
        return None
    lb = s.find("[")
    lb2 = s.find("{")
    if lb == -1 and lb2 == -1:
        return None
    if lb == -1 or (lb2 != -1 and lb2 < lb):
        start, open_c, close_c = lb2, "{", "}"
    else:
        start, open_c, close_c = lb, "[", "]"

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_c:
            depth += 1
        elif ch == close_c:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


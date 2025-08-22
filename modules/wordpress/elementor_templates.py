from __future__ import annotations

from modules.utils import require
from .cli import wp_cmd, wp_cmd_json


def get_elementor_version(domain: str) -> str:
    ok, data = wp_cmd_json(
        domain, ["plugin", "get", "elementor", "--field=version"]
    )
    if not ok:
        return ""
    if not data:
        return ""
    version_string = str(data).strip()
    return version_string


def set_elementor_meta(domain: str, page_id: int, version: str) -> bool:
    updates = [
        ("_elementor_edit_mode", "builder"),
        ("_elementor_version", version),
    ]
    for meta_key, meta_value in updates:
        ok = wp_cmd(
            domain, ["post", "meta", "update", str(page_id), meta_key, meta_value]
        )
        if not require(
            ok, f"Could not set {meta_key} for page {page_id}", "error"
        ):
            return False
    return True

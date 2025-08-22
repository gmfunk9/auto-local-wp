#!/usr/bin/env python3
"""Simple Elementor _elementor_data copy test (raw bytes, no transforms).

- Copies _elementor_data from one page to another on the same site.
- Reads source via WP-CLI, writes destination via eval-file reading a temp file.
- No slashing, no JSON parsing, no normalization. Just copy -> file -> paste.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from modules.utils import init_logging, status_pass, status_fail, log
from modules.wordpress.cli import wp_cmd, wp_cmd_capture
from config import SITE_ROOT_DIR


def _site_arg(domain: str | None, path: str | None) -> str:
    if path:
        return str(path)
    if not domain:
        raise SystemExit("domain or path required")
    return domain


def _site_path(domain: str | None, path: str | None) -> Path:
    if path:
        return Path(path)
    return Path(SITE_ROOT_DIR) / str(domain)


def _read_meta(site: str, post_id: int) -> tuple[bool, str]:
    ok, out, _ = wp_cmd_capture(site, [
        "post", "meta", "get", str(post_id), "_elementor_data",
    ])
    return ok, (out or "")


def _write_meta_raw(site: str, site_path: Path, post_id: int, blob: str) -> bool:
    tmpfile = Path(f"/tmp/_elementor_data-{post_id}.json")
    tmpfile.write_text(blob, encoding="utf-8")
    try:
        ok = wp_cmd(site, [
            "post", "meta", "update",
            str(post_id),
            "_elementor_data",
            blob
        ])
        return ok
    finally:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain")
    parser.add_argument("--path")
    parser.add_argument("--from-page", type=int, required=True)
    parser.add_argument("--to-page", type=int, required=True)
    args = parser.parse_args(argv)

    os.environ.setdefault("AUTOLOCAL_RID", "elemcopy")
    init_logging(None)

    site = _site_arg(args.domain, args.path)
    site_path = _site_path(args.domain, args.path)

    ok_s, src = _read_meta(site, args.from_page)
    if not ok_s or not src:
        status_fail("Could not read source _elementor_data")
        return 1
    log(f"read src len={len(src)} from={args.from_page}")

    ok_w = _write_meta_raw(site, site_path, args.to_page, src)
    if not ok_w:
        status_fail("Write failed (raw file -> update_post_meta)")
        return 1

    ok_d, dst = _read_meta(site, args.to_page)
    if not ok_d:
        status_fail("Could not read destination _elementor_data after write")
        return 1

    print({
        "from": args.from_page,
        "to": args.to_page,
        "src_len": len(src),
        "dst_len": len(dst),
        "equal": src == dst,
    })
    status_pass("elementor_data raw copy completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


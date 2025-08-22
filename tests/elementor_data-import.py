#!/usr/bin/env python3
"""Isolate Elementor _elementor_data writes using two methods.

- Targets a site by --domain (default) or explicit --path
- Selects target page via --page-id or --slug
- Sources payload via exactly one of: --blob-file, --from-page, --from-tpl
- Writes using:
  1) direct: wp post meta update <page> _elementor_data <blob>
  2) file:   wp eval-file (reads blob from file and updates meta)
- After each write, reads back _elementor_data, normalizes JSON, and reports
  equality/length/hash to spot discrepancies.

This does not flush CSS by default; focus is meta fidelity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Tuple

from modules.utils import init_logging, status_pass, status_fail, parse_json_relaxed, log
from modules.wordpress.cli import (
    wp_cmd,
    wp_cmd_capture,
    wp_cmd_json,
    wp_cmd_json_at_path,
)
from config import SITE_ROOT_DIR


DEFAULT_DOMAIN = "autolocalwp-testing-01.local"


def _site_path(domain: str | None, path: str | None) -> Path:
    if path:
        return Path(path)
    if not domain:
        domain = DEFAULT_DOMAIN
    return Path(SITE_ROOT_DIR) / domain


def _canonical(s: str) -> Tuple[str, str, int]:
    """
    Return (md5, normalized_json or original, length). Tries strict JSON, then
    relaxed; falls back to original string if both fail.
    """
    text = s or ""
    norm: str = text
    try:
        obj = json.loads(text)
        norm = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        try:
            obj = parse_json_relaxed(text)
            norm = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            norm = text
    md5 = hashlib.md5(norm.encode("utf-8")).hexdigest()
    return md5, norm, len(norm)


def _resolve_page_id(domain: str | None, path: str | None, slug: str) -> int:
    if path:
        ok, rows = wp_cmd_json_at_path(Path(path), [
            "post",
            "list",
            "--post_type=page",
            f"--name={slug}",
            "--fields=ID",
        ])
    else:
        dom = domain or DEFAULT_DOMAIN
        ok, rows = wp_cmd_json(dom, [
            "post",
            "list",
            "--post_type=page",
            f"--name={slug}",
            "--fields=ID",
        ])
    if not ok:
        return 0
    if not isinstance(rows, list):
        return 0
    if not rows:
        return 0
    try:
        first = rows[0]
        value = None
        if isinstance(first, dict):
            value = first.get("ID")
        if value is None:
            return 0
        number = int(value)
        return number
    except Exception:
        return 0


def _read_meta(domain: str | None, path: str | None, post_id: int) -> Tuple[bool, str]:
    if path:
        ok, out, _ = wp_cmd_capture(str(path), [
            "post",
            "meta",
            "get",
            str(post_id),
            "_elementor_data",
        ])
    else:
        dom = domain or DEFAULT_DOMAIN
        ok, out, _ = wp_cmd_capture(dom, [
            "post",
            "meta",
            "get",
            str(post_id),
            "_elementor_data",
        ])
    return ok, (out or "")


def _write_direct(domain: str | None, path: str | None, post_id: int, blob: str) -> bool:
    if path:
        # Use json wrapper to enforce consistent flags; discard data
        ok, _ = wp_cmd_json_at_path(Path(path), [
            "post",
            "meta",
            "update",
            str(post_id),
            "_elementor_data",
            blob,
        ])
        return ok
    dom = domain or DEFAULT_DOMAIN
    return wp_cmd(dom, [
        "post",
        "meta",
        "update",
        str(post_id),
        "_elementor_data",
        blob,
    ])


def _write_file(domain: str | None, path: str | None, post_id: int, blob: str) -> bool:
    base = _site_path(domain, path) / "wp-content" / "uploads" / "autolocal-tpl"
    base.mkdir(parents=True, exist_ok=True)
    jpath = base / f"_elementor_data-{post_id}.json"
    ppath = base / f"setmeta-{post_id}.php"
    jpath.write_text(blob, encoding="utf-8")
    pcode = (
        "<?php "
        f"$p={int(post_id)}; $k='_elementor_data'; $f='{str(jpath)}'; "
        "$v=file_get_contents($f); update_post_meta($p,$k,$v); echo 'OK';"
    )
    ppath.write_text(pcode, encoding="utf-8")
    try:
        dom_or_path = ""
        if path:
            dom_or_path = str(path)
        else:
            dom_or_path = domain or DEFAULT_DOMAIN
        ok = wp_cmd(dom_or_path, ["eval-file", str(ppath)])
        return ok
    finally:
        try:
            ppath.unlink(missing_ok=True)
            jpath.unlink(missing_ok=True)
        except Exception:
            pass


def _write_file_slash(domain: str | None, path: str | None, post_id: int, blob: str) -> bool:
    base = _site_path(domain, path) / "wp-content" / "uploads" / "autolocal-tpl"
    base.mkdir(parents=True, exist_ok=True)
    jpath = base / f"_elementor_data-{post_id}.json"
    ppath = base / f"setmeta-slash-{post_id}.php"
    jpath.write_text(blob, encoding="utf-8")
    pcode = (
        "<?php "
        f"$p={int(post_id)}; $k='_elementor_data'; $f='{str(jpath)}'; "
        "$v=file_get_contents($f); $v=wp_slash($v); update_post_meta($p,$k,$v); echo 'OK';"
    )
    ppath.write_text(pcode, encoding="utf-8")
    try:
        dom_or_path = ""
        if path:
            dom_or_path = str(path)
        else:
            dom_or_path = domain or DEFAULT_DOMAIN
        ok = wp_cmd(dom_or_path, ["eval-file", str(ppath)])
        return ok
    finally:
        try:
            ppath.unlink(missing_ok=True)
            jpath.unlink(missing_ok=True)
        except Exception:
            pass


def _load_payload(domain: str | None, path: str | None, args) -> str:
    if args.blob_file:
        return Path(args.blob_file).read_text(encoding="utf-8")
    if args.from_page:
        ok, s = _read_meta(domain, path, int(args.from_page))
        if ok:
            return s
        return ""
    if args.from_tpl:
        # Elementor stores data under the template post as well
        ok, s = _read_meta(domain, path, int(args.from_tpl))
        if ok:
            return s
        return ""
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--path")
    parser.add_argument("--page-id", type=int)
    parser.add_argument("--slug")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--blob-file")
    src.add_argument("--from-page", type=int)
    src.add_argument("--from-tpl", type=int)
    args = parser.parse_args(argv)

    os.environ.setdefault("AUTOLOCAL_RID", "elemdata")
    init_logging(None)

    pid = args.page_id or 0
    if pid <= 0 and args.slug:
        pid = _resolve_page_id(args.domain, args.path, args.slug)
    if pid <= 0:
        status_fail("No valid page id (use --page-id or --slug)")
        return 2

    payload = _load_payload(args.domain, args.path, args)
    if not payload:
        status_fail("Could not load payload")
        return 2

    # Baseline canonicalization
    in_md5, in_norm, in_len = _canonical(payload)

    # Method 1: direct
    ok1 = _write_direct(args.domain, args.path, pid, payload)
    ok1r, read1 = _read_meta(args.domain, args.path, pid)
    md5_1, norm_1, len_1 = _canonical(read1)
    same_1 = (in_md5 == md5_1)
    out1 = {
        "method": "direct",
        "ok": bool(ok1 and ok1r),
        "page_id": pid,
        "in_len": in_len,
        "read_len": len_1,
        "in_md5": in_md5,
        "read_md5": md5_1,
        "equal": same_1,
    }
    line1 = json.dumps(out1, ensure_ascii=False, separators=(",", ":"))
    print(line1)
    log(f"elementor_data test: {line1}")

    # # Method 2: file
    # ok2 = _write_file(args.domain, args.path, pid, payload)
    # ok2r, read2 = _read_meta(args.domain, args.path, pid)
    # md5_2, norm_2, len_2 = _canonical(read2)
    # same_2 = (in_md5 == md5_2)
    # out2 = {
    #     "method": "file",
    #     "ok": bool(ok2 and ok2r),
    #     "page_id": pid,
    #     "in_len": in_len,
    #     "read_len": len_2,
    #     "in_md5": in_md5,
    #     "read_md5": md5_2,
    #     "equal": same_2,
    # }
    # line2 = json.dumps(out2, ensure_ascii=False, separators=(",", ":"))
    # print(line2)
    # log(f"elementor_data test: {line2}")

    # # Method 3: file with wp_slash
    # ok3 = _write_file_slash(args.domain, args.path, pid, payload)
    # ok3r, read3 = _read_meta(args.domain, args.path, pid)
    # md5_3, norm_3, len_3 = _canonical(read3)
    # same_3 = (in_md5 == md5_3)
    # out3 = {
    #     "method": "file_slash",
    #     "ok": bool(ok3 and ok3r),
    #     "page_id": pid,
    #     "in_len": in_len,
    #     "read_len": len_3,
    #     "in_md5": in_md5,
    #     "read_md5": md5_3,
    #     "equal": same_3,
    # }
    # line3 = json.dumps(out3, ensure_ascii=False, separators=(",", ":"))
    # print(line3)
    # log(f"elementor_data test: {line3}")

    if out1["ok"]:
        status_pass("elementor_data import test completed")
        return 0
    status_fail("elementor_data import test had failures")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

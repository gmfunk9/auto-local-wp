"""WP-CLI wrappers and process helpers."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Tuple

from config import SITE_ROOT_DIR, WP_CLI_PATH
from modules.utils import _http_uid, _normalize_wp_parts, log

WP_TIMEOUT = int(os.environ.get("WP_TIMEOUT", "600"))  # seconds


def _wp_base_argv(site_path: Path) -> list[str]:
    parts = [WP_CLI_PATH, f"--path={site_path}"]
    http_uid = _http_uid()
    if http_uid > 0 and os.geteuid() != http_uid:
        return ["sudo", "-u", "http"] + parts
    return parts


def wp_cmd(domain: str, command, timeout: int = WP_TIMEOUT) -> bool:
    """Run a WP-CLI command with quiet output, timing, and timeout."""
    site_path = Path(SITE_ROOT_DIR) / domain
    parts = _normalize_wp_parts(command)
    if not parts:
        return False
    if "--quiet" not in parts:
        parts.append("--quiet")
    args = _wp_base_argv(site_path) + parts
    env = os.environ.copy()
    env["WP_CLI_DISABLE_AUTO_CHECK_UPDATE"] = "1"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            args, text=True, capture_output=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        logging.error("wp %s timeout after %.1fs", " ".join(parts), dt)
        return False
    dt = time.monotonic() - t0
    if proc.returncode == 0:
        log(f"PASS: wp {' '.join(parts)} ({dt:.1f}s)")
        return True
    logging.error(
        "wp %s exit=%s\nSTDERR: %s",
        " ".join(parts),
        proc.returncode,
        (proc.stderr or "").strip(),
    )
    return False


def wp_cmd_capture(
    domain: str, command, timeout: int = WP_TIMEOUT
) -> Tuple[bool, str, str]:
    """Run a WP-CLI command and capture output.
    Returns (ok, stdout, stderr).
    """
    site_path = Path(SITE_ROOT_DIR) / domain
    parts = _normalize_wp_parts(command)
    if not parts:
        return False, "", "Invalid command"
    if "--quiet" not in parts:
        parts.append("--quiet")
    args = _wp_base_argv(site_path) + parts
    env = os.environ.copy()
    env["WP_CLI_DISABLE_AUTO_CHECK_UPDATE"] = "1"
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            args, text=True, capture_output=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        msg = f"wp {' '.join(parts)} timeout after {dt:.1f}s"
        logging.error(msg)
        return False, "", msg
    dt = time.monotonic() - t0
    if proc.returncode == 0:
        log(f"PASS: wp {' '.join(parts)} ({dt:.1f}s)")
        return (
            True,
            (proc.stdout or "").strip(),
            (proc.stderr or "").strip(),
        )
    logging.error(
        "wp %s exit=%s\nSTDERR: %s",
        " ".join(parts),
        proc.returncode,
        (proc.stderr or "").strip(),
    )
    return False, (proc.stdout or "").strip(), (proc.stderr or "").strip()


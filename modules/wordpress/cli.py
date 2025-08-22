# cli.py
# Invariants (Phase-1 WP-CLI JSON consistency):
# - All WP-CLI access goes through these wrappers; callers never build flags.
# - Read-ish commands are coerced to JSON at the source by appending:
#     --format=json --quiet --no-color --skip-plugins --skip-themes
# - Parsing strips ANSI and PHP/WP noise and extracts real JSON when present.
# - Public wrappers return structured types; wp_cmd_capture returns a JSON string
#   of that structure; when output is empty, emit an empty JSON (e.g. []).
# - Accept commands with or without leading "wp"/"--path"; sanitize duplicates.
# - Logs: one PASS/FAIL per call; console stays minimal; file logs keep details.
# - Displayed command in logs never shows duplicated binaries; prefer "wp …".

from __future__ import annotations

import json
import logging
import os
import os.path
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Tuple, Union

from config import SITE_ROOT_DIR, WP_CLI_PATH
from modules.utils import _http_uid, _normalize_wp_parts, log, parse_json_relaxed
from .wp_json import extract_json_blob

# Timeouts and PHP noise suppression
WP_TIMEOUT = int(os.environ.get("WP_TIMEOUT", "600"))  # seconds
os.environ.setdefault("WP_CLI_DISABLE_AUTO_CHECK_UPDATE", "1")
os.environ.setdefault("WP_CLI_SILENCE_PHP_ERRORS", "1")
# Also hush PHP startup/display errors for CLI
os.environ.setdefault("WP_CLI_PHP_ARGS", "-d display_errors=0 -d display_startup_errors=0")

# ── Noise filters ───────────────────────────────────────────────────────────────
ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
NOISE_PREFIXES = (
    "PHP Warning:", "PHP Notice:", "PHP Deprecated:", "PHP Fatal error:",
    "Warning:", "Notice:", "Deprecated:", "Fatal error:", "Error:", "PHP:"
)
NOISE_PATTERNS = (
    re.compile(r"^#\d+:"),               # stack frames
    re.compile(r"^'trace'\s*=>"),        # array trace header
    re.compile(r"^\)\]$"),               # closing junk
    re.compile(r"^',?$"),                # dangling quotes/commas
    re.compile(r".*->.*"),               # method arrow in stack lines
)

def _strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)

def _drop_noise_lines(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln:
            continue
        if any(ln.startswith(p) for p in NOISE_PREFIXES):
            continue
        if any(p.search(ln) for p in NOISE_PATTERNS):
            continue
        out.append(ln)
    return out

def _unquote_token(tok: str) -> str:
    if len(tok) < 2:
        return tok
    if tok[0] == '"':
        if tok[-1] == '"':
            return tok[1:-1]
    if tok[0] == "'":
        if tok[-1] == "'":
            return tok[1:-1]
    return tok

def _decode_scalar_maybe_json(one: str) -> Any:
    """
    Try strict JSON; if that yields a string, unwrap nested quotes if present.
    Fallback: return unquoted token.
    """
    try:
        val = json.loads(one)
        if isinstance(val, str):
            # If still wrapped in quotes (double-encoded), strip repeatedly.
            while len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
                val = val[1:-1]
        return val
    except Exception:
        return _unquote_token(one)

def _cast_token(tok: str) -> Any:
    # ints (IDs) stay numeric; everything else stays string
    if tok.isdigit():
        try:
            return int(tok)
        except Exception:
            return tok
    return tok

def _collect_simple_tokens(lines: list[str]) -> list[str]:
    # keep tokens without whitespace (IDs, slugs, urls, quoted strings)
    return [ln for ln in lines if re.match(r"^\S+$", ln) is not None]

# ── Internal helpers ────────────────────────────────────────────────────────────
def _target_to_path(target: Union[str, Path]) -> Path:
    if isinstance(target, Path):
        return target
    return Path(SITE_ROOT_DIR) / str(target)

def _wp_base_argv(site_path: Path) -> list[str]:
    parts = [WP_CLI_PATH, f"--path={site_path}"]
    http_uid = _http_uid()
    if http_uid <= 0:
        return parts
    if os.geteuid() == http_uid:
        return parts
    return ["sudo", "-u", "http"] + parts

def _sanitize_parts(parts: list[str]) -> list[str]:
    # drop any leading 'wp' or explicit binary tokens (repeat to be safe)
    while parts and (parts[0] == "wp" or os.path.basename(parts[0]) == "wp"):
        parts = parts[1:]
    # drop any --path passed by caller (we provide our own)
    cleaned: list[str] = []
    skip_next = False
    for i, p in enumerate(parts):
        if skip_next:
            skip_next = False
            continue
        if p.startswith("--path="):
            continue
        if p == "--path":
            if i + 1 < len(parts):
                nextp = parts[i + 1]
                if not nextp.startswith("-"):
                    skip_next = True
            continue
        cleaned.append(p)
    return cleaned

def _ensure_quiet_flags(parts: list[str]) -> list[str]:
    if "--no-color" not in parts:
        parts.append("--no-color")
    if "--quiet" not in parts:
        parts.append("--quiet")
    return parts

def _fmt_cmd_for_log(args: list[str]) -> str:
    if not args:
        return ""
    # strip sudo -u http prefix for display
    start = 0
    if args[0] == "sudo":
        if len(args) >= 4:
            if args[1] == "-u":
                start = 3
    # replace absolute binary path with 'wp' for readability
    pretty = ["wp"] + args[start+1:]
    return " ".join(pretty)

def _wp_run(target: Union[str, Path], command, timeout: int = WP_TIMEOUT) -> Tuple[bool, str, str, int]:
    site_path = _target_to_path(target)
    parts = _normalize_wp_parts(command)
    if not parts:
        return False, "", "Invalid command", 1
    parts = _sanitize_parts(parts)
    parts = _ensure_quiet_flags(parts)

    args = _wp_base_argv(site_path) + parts
    env = os.environ.copy()

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        dt = time.monotonic() - t0
        logging.error("wp %s timeout after %.1fs", _fmt_cmd_for_log(args), dt)
        return False, "", f"timeout after {dt:.1f}s", 124

    dt = time.monotonic() - t0
    ok = proc.returncode == 0
    if ok:
        log(f"PASS: wp {_fmt_cmd_for_log(args)} ({dt:.1f}s)")
    else:
        clean_err = "\n".join(_drop_noise_lines(proc.stderr or ""))
        logging.error(
            "wp %s exit=%s\nSTDERR: %s",
            _fmt_cmd_for_log(args),
            proc.returncode,
            clean_err.strip(),
        )
    return ok, (proc.stdout or ""), (proc.stderr or ""), proc.returncode


# ── Parsing (strict JSON out with porcelain fallback) ───────────────────────────
def _parse_json_loose(combined: str, readish: bool = False) -> Any | None:
    """
    Best-effort JSON parse with noise scrubbing and porcelain handling.
    Order:
      1) Strip ANSI; drop PHP/WP noise lines.
      2) Extract embedded JSON container if present and parse strictly/relaxed.
      3) If single clean line, try json.loads for primitive; else treat as string (unquoted).
      4) If multi-line, emit array of simple tokens (ints if numeric);
         if none, fall back to first clean line as string.
      5) None if nothing usable.
    """
    cleaned_text = "\n".join(_drop_noise_lines(_strip_ansi(combined))).strip()
    if not cleaned_text:
        return None

    # Embedded containers ({...} or [...])
    blob = extract_json_blob(cleaned_text)
    if blob is not None:
        try:
            return json.loads(blob)
        except Exception:
            try:
                return parse_json_relaxed(blob, default=None)
            except Exception:
                return None

    # Single-line primitive
    lines = cleaned_text.splitlines()
    if len(lines) == 1:
        one = lines[0].strip()
        if not one:
            return None
        return _decode_scalar_maybe_json(one)

    # Multi-line porcelain → collect simple tokens
    toks = _collect_simple_tokens(lines)
    if toks:
        return [_cast_token(_unquote_token(t)) for t in toks]

    # Fallback to first cleaned line as string
    return lines[0].strip() if lines else None

# ── Public API ──────────────────────────────────────────────────────────────────
def _looks_like_read_cmd(parts: list[str]) -> bool:
    s = set(parts)
    if "list" in s:
        return True
    if "get" in s:
        return True
    if "search" in s:
        return True
    return any(p.startswith("--fields=") for p in parts)

def _append_format_json(parts: list[str]) -> list[str]:
    if not any(p.startswith("--format=") for p in parts):
        parts = parts[:] + ["--format=json"]
    # reduce boot/plugin noise for read-ish commands
    if "--skip-plugins" not in parts:
        parts.append("--skip-plugins")
    if "--skip-themes" not in parts:
        parts.append("--skip-themes")
    if "--no-color" not in parts:
        parts.append("--no-color")
    if "--quiet" not in parts:
        parts.append("--quiet")
    return parts

def wp_cmd_json(domain: str, command: Any, timeout: int = WP_TIMEOUT) -> Tuple[bool, Any]:
    parts = _normalize_wp_parts(command)
    parts = _sanitize_parts(parts)

    readish = bool(parts and _looks_like_read_cmd(parts))
    # For read-ish commands, try to coerce JSON at the source.
    if readish:
        has_format = any(p.startswith("--format=") for p in parts)
        if not has_format:
            parts = _append_format_json(parts)
            logging.debug("Augmented command with --format=json etc.")
            ok, out, err, code = _wp_run(domain, parts, timeout=timeout)
        else:
            ok, out, err, code = _wp_run(domain, parts, timeout=timeout)
    else:
        ok, out, err, code = _wp_run(domain, parts, timeout=timeout)

    combined = (out or "") + (("\n" + err) if err else "")
    if err:
        clean_err = _drop_noise_lines(err)
        logging.debug("Stderr (len %d): %s", len(err), clean_err[:3])
    if out:
        logging.debug("Stdout (len %d)", len(out))


    data = _parse_json_loose(combined.strip(), readish=readish)
    if data is None:
        if readish:
            logging.warning("wp_cmd_json: returning empty array because JSON parse failed")
        else:
            logging.debug("wp_cmd_json: no JSON output (non-read command)")
        data = []
    else:
        logging.debug("wp_cmd_json: parsed JSON-like type=%s", type(data).__name__)

        # unfuck case: JSON string that itself looks like JSON
        if isinstance(data, str):
            stripped = data.strip()
            if stripped:
                first = stripped[0]
                if first in "[{":
                    try:
                        inner = json.loads(stripped)
                        data = inner
                        logging.debug(
                            "wp_cmd_json: unwrapped nested JSON string"
                        )
                    except Exception:
                        pass

    return ok, data


def wp_cmd(domain: str, command, timeout: int = WP_TIMEOUT) -> bool:
    """
    Legacy boolean wrapper. Delegates to wp_cmd_json and discards data.
    """
    ok, _ = wp_cmd_json(domain, command, timeout=timeout)
    return ok

def wp_cmd_capture(domain: str, command, timeout: int = WP_TIMEOUT) -> Tuple[bool, str, str]:
    """
    Legacy capture wrapper. Delegates to wp_cmd_json and returns:
      (ok, stdout_string_json, "").
    """
    ok, data = wp_cmd_json(domain, command, timeout=timeout)
    return ok, json.dumps(data, ensure_ascii=False, separators=(",", ":")), ""

def wp_cmd_json_at_path(site_path: Path, command, timeout: int = WP_TIMEOUT) -> Tuple[bool, Any]:
    """
    Same as wp_cmd_json, but with an explicit filesystem path to the site.
    """
    return wp_cmd_json(str(site_path), command, timeout=timeout)

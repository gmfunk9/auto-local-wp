"""Utility helpers kept dependency-free.

- init_logging: configure console + file logging with run-id.
- status_pass/status_fail: concise console status lines (with run-id).
- run_cmd: thin wrapper over subprocess.run with check + text enabled.
- log: debug-level logger for normal status lines (file-oriented).
- db_ident: normalized identifier for DB/user names.
- _http_uid: resolve uid for the "http" user or -1 if missing.
- _normalize_wp_parts: parse WP-CLI command into argv parts.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
import pwd
import shlex
import subprocess
from typing import List, Sequence, Any
import re
import json


_RUN_ID = ""


def _gen_run_id() -> str:
    try:
        import uuid

        return uuid.uuid4().hex[:8]
    except Exception:
        return "00000000"


def init_logging(run_id: str | None = None) -> str:
    """Initialize logging with console + rotating file handlers.

    - Console: minimal, INFO+, intended for terse status only.
    - File: DEBUG+, rich format, written to log/autolocal-<rid>.log
    Returns the run-id used.
    """
    global _RUN_ID
    if _RUN_ID:
        return _RUN_ID

    rid = run_id or os.environ.get("AUTOLOCAL_RID") or _gen_run_id()
    _RUN_ID = rid

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Ensure log directory under project root: parent of 'modules'
    try:
        # Project root = parent of 'modules'
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        log_dir = os.path.join(root_dir, "log")
        os.makedirs(log_dir, exist_ok=True)
        logfile = os.path.join(log_dir, f"autolocal-{rid}.log")
    except Exception:
        logfile = os.path.abspath(f"autolocal-{rid}.log")

    # Quiet any pre-existing console handlers
    for h in list(root.handlers):
        try:
            if isinstance(h, logging.StreamHandler):
                h.setLevel(logging.CRITICAL)
        except Exception:
            continue

    # Add file handler if not present
    has_file = False
    for h in root.handlers:
        try:
            if isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', '').endswith(
                os.path.basename(logfile)
            ):
                has_file = True
                break
        except Exception:
            continue
    if not has_file:
        fh = RotatingFileHandler(logfile, maxBytes=5 * 1024 * 1024, backupCount=3)
        fh.setLevel(logging.DEBUG)
        ffmt = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        fh.setFormatter(ffmt)
        root.addHandler(fh)

    # Add a super-quiet console handler if none exist
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(logging.CRITICAL)
        cfmt = logging.Formatter("%(levelname)s: %(message)s")
        ch.setFormatter(cfmt)
        root.addHandler(ch)

    logging.debug("Logging initialized. run_id=%s file=%s", rid, logfile)
    os.environ["AUTOLOCAL_RID"] = rid
    return rid


def _rid() -> str:
    return _RUN_ID or os.environ.get("AUTOLOCAL_RID", "--------")


def status_pass(msg: str) -> None:
    print(f"PASS: {msg} [{_rid()}]")


def status_fail(msg: str) -> None:
    print(f"FAIL: {msg} [{_rid()}]", flush=True)


def run_cmd(args: List[str]) -> None:
    subprocess.run(args, check=True, text=True)


def log(msg: str) -> None:
    # File-oriented normal progress; stays out of console noise.
    logging.debug(msg)


def db_ident(domain: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in domain)


def _http_uid() -> int:
    try:
        return pwd.getpwnam("http").pw_uid
    except Exception:
        return -1


def _normalize_wp_parts(command: str | Sequence[str]) -> list[str]:
    """Normalize command into argv parts.
    Accepts str (parsed with shlex) or sequence of strings.
    Returns a list; empty list indicates an error already reported.
    """
    if command is None:
        logging.error("wp called with None command")
        return []
    if isinstance(command, str):
        text = command.strip()
        if not text:
            logging.error("wp called with empty command")
            return []
        try:
            return shlex.split(text)
        except Exception as err:
            logging.error("Could not parse command: %s", err)
            return []
    if isinstance(command, (list, tuple)):
        parts = [str(p) for p in command]
        if not parts:
            logging.error("wp called with empty argv list")
            return []
        return parts
    logging.error("Unsupported command type: %s", type(command).__name__)
    return []


def _strip_ansi(text: str) -> str:
    try:
        return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    except Exception:
        return text


def parse_json_relaxed(text: str, default: Any) -> Any:
    """Parse JSON with basic tolerance for noise.

    - Strips BOM and ANSI codes
    - Extracts substring between first '[' and last ']' or first '{' and last '}'
    - Returns default on failure
    """
    if text is None:
        return default
    try:
        s = text.lstrip("\ufeff").strip()
        s = _strip_ansi(s)
        try:
            return json.loads(s)
        except Exception:
            pass
        # Try bracketed array
        lb = s.find("[")
        rb = s.rfind("]")
        if lb != -1 and rb != -1 and rb > lb:
            try:
                return json.loads(s[lb : rb + 1])
            except Exception:
                pass
        # Try object
        lb = s.find("{")
        rb = s.rfind("}")
        if lb != -1 and rb != -1 and rb > lb:
            try:
                return json.loads(s[lb : rb + 1])
            except Exception:
                pass
    except Exception:
        return default
    return default

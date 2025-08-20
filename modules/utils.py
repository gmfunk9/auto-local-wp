"""Utility helpers kept dependency-free.

- run_cmd: thin wrapper over subprocess.run with check + text enabled.
- log: info-level logger for normal status lines.
- db_ident: normalized identifier for DB/user names.
- _http_uid: resolve uid for the "http" user or -1 if missing.
- _normalize_wp_parts: parse WP-CLI command into argv parts.
"""

import logging
import pwd
import shlex
import subprocess
from typing import List, Sequence


def run_cmd(args: List[str]) -> None:
    subprocess.run(args, check=True, text=True)


def log(msg: str) -> None:
    logging.info(msg)


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

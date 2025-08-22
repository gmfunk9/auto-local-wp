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
from pathlib import Path
from urllib.parse import urlsplit


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
    parts: list[str] = []
    for char in domain:
        if char.isalnum():
            parts.append(char)
            continue
        parts.append("_")
    identifier = "".join(parts)
    return identifier


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
        if lb != -1:
            if rb != -1:
                if rb > lb:
                    try:
                        return json.loads(s[lb : rb + 1])
                    except Exception:
                        pass
        # Try object
        lb = s.find("{")
        rb = s.rfind("}")
        if lb != -1:
            if rb != -1:
                if rb > lb:
                    try:
                        return json.loads(s[lb : rb + 1])
                    except Exception:
                        pass
    except Exception:
        return default
    return default


# ---------------------------------------------------------------------------
# Generic helpers moved from modules/wordpress/plugins.py
# ---------------------------------------------------------------------------


def require(condition: bool, message: str, level: str = "info") -> bool:
    if condition:
        return True

    if level == "error":
        logging.error(f"SKIP: {message}")
    elif level == "warning":
        logging.warning(f"SKIP: {message}")
    else:
        log(f"SKIP: {message}")

    return False


def get_temp_dir(domain: str, site_root_dir: str) -> Path:
    upload_dir = (
        Path(site_root_dir) / domain / "wp-content" / "uploads" / "autolocal-tpl"
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def write_temp_file(domain: str, filename: str, content: str, site_root_dir: str) -> Path:
    temp_dir = get_temp_dir(domain, site_root_dir)
    destination = temp_dir / filename
    destination.write_text(content, encoding="utf-8")
    return destination


def run_as_http(command: list[str]) -> bool:
    try:
        subprocess.run(["sudo", "-u", "http"] + command, check=True)
        return True
    except Exception as error:
        command_str = " ".join(command)
        logging.error(f"Command failed: {command_str} - {error}")
        return False
    # INCONSISTENCY: this uses try/except instead of returning a Boolean
    # and letting require() handle logging, which would be more consistent.


def copy_directory_item(item: Path, target: Path, name: str) -> bool:
    command = ["cp", "-rT", str(item), str(target)]
    result = run_as_http(command)
    log_message = f"Installed {name} {item.name}"
    return require(result, log_message, "info")


def copy_directory_tree(source: Path, destination: Path, label: str) -> bool:
    if not source.exists():
        return True

    for item in source.iterdir():
        target_path = destination / item.name
        result = copy_directory_item(item, target_path, label)
        if not result:
            return False

    return True


def cleanup_staged_template(domain: str, path_str: str, site_root_dir: str) -> None:
    try:
        path = Path(path_str)
        if path.exists():
            path.unlink()
            log(f"PASS: Removed staged template {path}")

        temp_dir = get_temp_dir(domain, site_root_dir)
        empty = not any(temp_dir.iterdir())
        if temp_dir.exists() and empty:
            temp_dir.rmdir()
            log(f"PASS: Removed empty temp dir {temp_dir}")
    except Exception as error:
        logging.error(f"Cleanup failed: {error}")
    # INCONSISTENCY: try/except is used here to swallow all errors,
    # but most of the file uses require() for validation + logging.


# Upload/media URL helpers
UPLOAD_PATTERN = r"http[^\"]+uploads[^\"]+\.(?:jpg|jpeg|png|webp)"
SIZE_PATTERN = r"(?:-\d{2,5}x\d{2,5})(\.\w{3,4})(?:$|\?)"
UPLOAD_RE = re.compile(UPLOAD_PATTERN, re.IGNORECASE)
SIZE_RE = re.compile(SIZE_PATTERN, re.IGNORECASE)


def find_upload_urls(blob: str) -> tuple[list[str], str]:
    if not blob:
        return [], ""

    raw_urls = UPLOAD_RE.findall(blob)
    cleaned = []
    seen = set()

    for url in raw_urls:
        normalized_url = url.replace("\\/", "/")
        if normalized_url not in seen:
            seen.add(normalized_url)
            cleaned.append(normalized_url)

    host = ""
    if cleaned:
        first_url = cleaned[0]
        host = urlsplit(first_url).netloc

    return cleaned, host


def normalize_url(url: str) -> str:
    without_slashes = url.replace("\\/", "/")
    no_query = without_slashes.split("?", 1)[0]
    no_fragment = no_query.split("#", 1)[0]
    return no_fragment


def remove_size_suffix(url: str) -> str:
    return SIZE_RE.sub(r"\1", url)


def update_json_ids_from_urls(
    blob: str, mapping: dict[str, str]
) -> tuple[str, int]:
    if not mapping:
        return blob, 0

    fixed_blob = blob.replace("\\/", "/")
    data = json.loads(fixed_blob)
    hits = 0

    def lookup_id(url: str) -> str | None:
        normalized = normalize_url(url)
        unsized = remove_size_suffix(normalized)
        if normalized in mapping:
            return mapping[normalized]
        if unsized in mapping:
            return mapping[unsized]
        return None

    def walk_object(obj):
        nonlocal hits
        if isinstance(obj, dict):
            if "url" in obj:
                url_val = obj.get("url")
                new_id = lookup_id(url_val)
                if new_id is not None:
                    try:
                        obj["id"] = int(new_id)
                    except Exception:
                        obj["id"] = new_id
                    hits += 1
            for val in obj.values():
                walk_object(val)
        elif isinstance(obj, list):
            for item in obj:
                walk_object(item)

    walk_object(data)
    new_blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return new_blob, hits


def apply_placeholders(text: str, mapping: dict[str, str] | None = None) -> str:
    if not mapping:
        return text

    updated = text
    for key, value in mapping.items():
        updated = updated.replace(key, value)

    return updated

#!/usr/bin/env python3
"""Manage autolocal entries in /etc/hosts safely and atomically.

Inputs: domain via CLI, optional --remove flag. On add, uses
LOCALHOST_IP from config. Only lines with "# autolocal" are managed.
Other lines and comments are preserved intact.
"""
import os
import sys
import tempfile
from pathlib import Path
from typing import List, Tuple

from config import HOSTS_FILE, LOCALHOST_IP
from modules.utils import log


def _read_hosts() -> Tuple[List[str], int, int, int]:
    path = Path(HOSTS_FILE)
    if not path.exists():
        uid = os.getuid()
        gid = os.getgid()
        mode = 0o644
        return [], mode, uid, gid
    data = path.read_text()
    st = path.stat()
    lines = data.splitlines(keepends=True)
    return lines, st.st_mode, st.st_uid, st.st_gid


def _write_hosts_atomic(
    lines: List[str], mode: int, uid: int, gid: int
) -> bool:
    path = Path(HOSTS_FILE)
    dir_path = path.parent
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, dir=str(dir_path)
        ) as tmp:
            tmp.writelines(lines)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.chmod(tmp_path, mode)
        os.chown(tmp_path, uid, gid)
        os.replace(tmp_path, str(path))
        return True
    except Exception as err:
        print(
            f"FAIL: Could not write hosts file: {err}",
            file=sys.stderr,
        )
        return False


def add_host(ip: str, domain: str) -> bool:
    lines, mode, uid, gid = _read_hosts()
    tag = "# autolocal"
    desired = f"{ip} {domain} {tag}\n"

    kept = []
    removed = 0
    for line in lines:
        has_tag = tag in line
        has_domain = domain in line
        if has_tag and has_domain:
            removed += 1
            continue
        kept.append(line)

    if removed == 0 and desired in lines:
        return True

    kept.append(desired)
    ok = _write_hosts_atomic(kept, mode, uid, gid)
    if not ok:
        return False
    log(f"PASS: Added {domain} to hosts file")
    return True


def remove_host(domain: str) -> bool:
    lines, mode, uid, gid = _read_hosts()
    tag = "# autolocal"

    kept = []
    removed = 0
    for line in lines:
        has_tag = tag in line
        has_domain = domain in line
        if has_tag and has_domain:
            removed += 1
            continue
        kept.append(line)

    if removed == 0:
        return True

    ok = _write_hosts_atomic(kept, mode, uid, gid)
    if not ok:
        return False
    log(f"PASS: Removed {domain} from hosts file")
    return True


def main() -> int:
    if len(sys.argv) < 2:
        print("FAIL: Missing domain", file=sys.stderr)
        return 1
    domain = sys.argv[1]
    do_remove = "--remove" in sys.argv
    if do_remove:
        ok = remove_host(domain)
        return 0 if ok else 1
    ok = add_host(LOCALHOST_IP, domain)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

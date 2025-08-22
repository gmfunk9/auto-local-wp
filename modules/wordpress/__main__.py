"""Module entry point preserving original CLI behavior."""

from __future__ import annotations

import logging
import sys

from modules.utils import init_logging, status_fail
from .installer import (
    preflight_create,
    install_wordpress,
    setup_wordpress,
    remove_wordpress,
)
from .site import (
    setup_starter_pages_and_menu,
    enable_auto_updates,
)


def _init_logging() -> None:
    # Use shared logging scheme with run-id propagation.
    init_logging(None)


def main() -> int:
    _init_logging()
    argv = sys.argv[1:]
    if not argv:
        status_fail(
            "usage: [--preflight|--create|--remove] <domain> | preflight|core|starter|updates|remove <domain>"
        )
        return 1
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    if flags:
        if len(args) < 1:
            status_fail("missing domain")
            return 1
        domain = args[0]
        preset = None
        for f in flags:
            if f.startswith("--preset="):
                preset = f.split("=", 1)[1]
                break
        if "--remove" in flags:
            ok = remove_wordpress(domain)
            if ok:
                return 0
            return 1
        if "--preflight" in flags:
            ok = preflight_create(domain)
            if ok:
                return 0
            return 1
        if "--create" in flags:
            ok = setup_wordpress(domain, preset=preset)
            if ok:
                return 0
            return 1
        status_fail("unknown flag")
        return 1
    cmd = args[0]
    if len(args) < 2:
        status_fail("missing domain")
        return 1
    domain = args[1]
    if cmd == "preflight":
        ok = preflight_create(domain)
        if ok:
            return 0
        return 1
    if cmd == "core":
        ok = install_wordpress(domain)
        if ok:
            return 0
        return 1
    # marketplace plugin/theme install and preset commands removed (vault-only)
    if cmd == "starter":
        ok = setup_starter_pages_and_menu(domain)
        if ok:
            return 0
        return 1
    if cmd == "updates":
        ok = enable_auto_updates(domain)
        if ok:
            return 0
        return 1
    if cmd == "remove":
        ok = remove_wordpress(domain)
        if ok:
            return 0
        return 1
    status_fail("unknown subcommand")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

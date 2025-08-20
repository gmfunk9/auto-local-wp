"""Module entry point preserving original CLI behavior."""

from __future__ import annotations

import logging
import sys

from .installer import (
    preflight_create,
    install_wordpress,
    setup_wordpress,
    remove_wordpress,
)
from .site import (
    build_preset_config,
    apply_preset_config,
    setup_starter_pages_and_menu,
    enable_auto_updates,
)
from .plugins import install_plugins
from .themes import install_themes


def _init_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s: %(message)s",
        )


def main() -> int:
    _init_logging()
    argv = sys.argv[1:]
    if not argv:
        logging.error(
            "usage: wordpress [--preflight|--create|--remove] <domain> | "
            "preflight|core|plugins|themes|preset|starter|updates|remove <domain>"
        )
        return 1
    flags = [a for a in argv if a.startswith("--")]
    args = [a for a in argv if not a.startswith("--")]
    if flags:
        if len(args) < 1:
            logging.error("Missing domain")
            return 1
        domain = args[0]
        if "--remove" in flags:
            return 0 if remove_wordpress(domain) else 1
        if "--preflight" in flags:
            return 0 if preflight_create(domain) else 1
        if "--create" in flags:
            return 0 if setup_wordpress(domain) else 1
        logging.error("Unknown flag")
        return 1
    cmd = args[0]
    if len(args) < 2:
        logging.error("Missing domain")
        return 1
    domain = args[1]
    if cmd == "preflight":
        return 0 if preflight_create(domain) else 1
    if cmd == "core":
        return 0 if install_wordpress(domain) else 1
    if cmd == "plugins":
        preset = build_preset_config()
        return 0 if install_plugins(domain, preset["plugins"]) else 1
    if cmd == "themes":
        preset = build_preset_config()
        return 0 if install_themes(domain, preset["themes"]) else 1
    if cmd == "preset":
        preset = build_preset_config()
        return 0 if apply_preset_config(domain, preset) else 1
    if cmd == "starter":
        return 0 if setup_starter_pages_and_menu(domain) else 1
    if cmd == "updates":
        return 0 if enable_auto_updates(domain) else 1
    if cmd == "remove":
        return 0 if remove_wordpress(domain) else 1
    logging.error("Unknown subcommand")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

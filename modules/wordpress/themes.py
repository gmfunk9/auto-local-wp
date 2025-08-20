"""Theme management helpers."""

from __future__ import annotations

import logging

from modules.utils import log
from .cli import wp_cmd


def install_themes(domain: str, themes: list[str]) -> bool:
    for theme in themes:
        if not wp_cmd(domain, f"theme install {theme} --force"):
            logging.error("Could not install theme: %s", theme)
            return False
    return True


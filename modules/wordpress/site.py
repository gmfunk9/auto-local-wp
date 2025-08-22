"""Filesystem and site configuration operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from config import SITE_ROOT_DIR
from modules.utils import log
from .cli import wp_cmd, wp_cmd_capture, wp_cmd_json


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


def ensure_site_dir(domain: str) -> bool:
    site_path = Path(SITE_ROOT_DIR) / domain
    try:
        site_path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as err:
        logging.error("Could not create or access %s: %s", site_path, err)
        return False


def get_site_plugins_dir(domain: str) -> Path:
    site_path = Path(SITE_ROOT_DIR) / domain
    return site_path / "wp-content" / "plugins"


def _append_unique(items: list[str], value: str) -> None:
    if value in items:
        return
    items.append(value)


import logging


def _get_post_id_by_slug(domain: str, slug: str) -> int:
    ok, rows = wp_cmd_json(
        domain, [
            "post", "list", "--post_type=page", f"--name={slug}", "--fields=ID",
        ]
    )
    if not ok or not isinstance(rows, list) or not rows:
        return 0
    try:
        first = rows[0]
        val = first.get("ID") if isinstance(first, dict) else None
        return int(val) if val is not None else 0
    except Exception:
        return 0


def _ensure_page(domain: str, title: str, slug: str, content: str) -> int:
    page_id = _get_post_id_by_slug(domain, slug)
    if page_id:
        return page_id
    cmd = [
        "post",
        "create",
        "--post_type=page",
        "--post_status=publish",
        f"--post_title={title}",
        f"--post_name={slug}",
        f"--post_content={content}",
        "--porcelain",
    ]
    ok, out, _ = wp_cmd_capture(domain, cmd)
    if not ok:
        return 0
    try:
        pid = int((out or "0").strip())
        if pid > 0:
            return pid
    except ValueError:
        pass
    # Fallback: re-query by slug in case create printed a message
    # instead of the ID while still creating the post.
    return _get_post_id_by_slug(domain, slug)


def _set_static_front_page(domain: str, page_id: int) -> bool:
    if page_id <= 0:
        return False
    if not wp_cmd(domain, "option update show_on_front page"):
        return False
    if not wp_cmd(domain, f"option update page_on_front {page_id}"):
        return False
    return True


def _menu_exists(domain: str, name: str) -> bool:
    ok, rows = wp_cmd_json(domain, ["menu", "list", "--fields=name"])
    if not ok or not isinstance(rows, list):
        return False
    for item in rows:
        try:
            if (item.get("name") or "").strip() == name:
                return True
        except Exception:
            continue
    return False


def _ensure_menu(domain: str, name: str) -> bool:
    if _menu_exists(domain, name):
        return True
    return wp_cmd(domain, f"menu create '{name}'")


def _menu_item_object_ids(domain: str, name: str) -> set[int]:
    ok, rows = wp_cmd_json(
        domain, ["menu", "item", "list", name, "--fields=object_id"]
    )
    if not ok or not isinstance(rows, list):
        return set()
    ids: set[int] = set()
    for item in rows:
        try:
            raw = item.get("object_id") if isinstance(item, dict) else None
            if raw is None:
                continue
            ids.add(int(str(raw).strip()))
        except Exception:
            continue
    return ids


def _ensure_menu_items(domain: str, name: str, page_ids: list[int]) -> bool:
    existing = _menu_item_object_ids(domain, name)
    for pid in page_ids:
        if pid in existing:
            continue
        if not wp_cmd(domain, f"menu item add-post '{name}' {pid}"):
            return False
    return True


def setup_starter_pages_and_menu(domain: str) -> bool:
    home_id = _ensure_page(
        domain, title="Home", slug="home", content="This is your Home page placeholder."
    )
    if not home_id:
        logging.error("Could not ensure Home page")
        return False
    services_id = _ensure_page(
        domain, title="Services", slug="services", content="List your services here."
    )
    if not services_id:
        logging.error("Could not ensure Services page")
        return False
    contact_id = _ensure_page(
        domain, title="Contact", slug="contact", content="Add your contact details here."
    )
    if not contact_id:
        logging.error("Could not ensure Contact page")
        return False
    if not _set_static_front_page(domain, home_id):
        logging.error("Could not set static front page")
        return False
    if not _ensure_menu(domain, "Main"):
        logging.error("Could not ensure Main menu")
        return False
    if not _ensure_menu_items(domain, "Main", [home_id, services_id, contact_id]):
        logging.error("Could not add pages to Main menu")
        return False
    log("PASS: Starter pages and Main menu ready")
    return True


def enable_auto_updates(domain: str) -> bool:
    if not wp_cmd(domain, "plugin auto-updates enable --all"):
        return False
    if not wp_cmd(domain, "theme auto-updates enable --all"):
        return False
    if not wp_cmd(domain, "plugin auto-updates status --all"):
        return False
    log("PASS: Auto-updates enabled for plugins and themes")
    return True


def site_has_wp_config(domain: str) -> bool:
    site_path = Path(SITE_ROOT_DIR) / domain
    return (site_path / "wp-config.php").exists()

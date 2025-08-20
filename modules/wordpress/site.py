"""Filesystem and site configuration operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from config import SITE_ROOT_DIR
from modules.utils import log
from .cli import wp_cmd, wp_cmd_capture


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


def _load_tsv(filename: str) -> list[tuple[str, str]]:
    path = DATA_DIR / filename
    if not path.exists():
        return []
    items: list[tuple[str, str]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            status = parts[1].strip().lower()
            if status not in ("active", "disabled") or not name:
                continue
            items.append((name, status))
    except Exception as err:
        logging.error("Could not read %s: %s", path, err)
        return []
    return items


def _plugins_from_tsv() -> tuple[list[str], list[str]]:
    items = _load_tsv("plugins.tsv")
    install = [name for name, _ in items]
    active = [name for name, st in items if st == "active"]
    return install, active


def _themes_from_tsv() -> tuple[list[str], list[str]]:
    items = _load_tsv("themes.tsv")
    install = [name for name, _ in items]
    active = [name for name, st in items if st == "active"]
    return install, active


def _read_wp_cli_commands() -> list[str]:
    path = DATA_DIR / "wp_cli_commands.txt"
    if not path.exists():
        return []
    commands: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            commands.append(line)
    except Exception as err:
        logging.error("Could not read %s: %s", path, err)
        return []
    return commands


def _custom_plugins_dir() -> Path:
    return DATA_DIR / "custom-plugins"


def list_custom_plugins() -> list[Path]:
    base = _custom_plugins_dir()
    if not base.exists() or not base.is_dir():
        return []
    try:
        return [p for p in base.iterdir() if p.is_dir()]
    except Exception:
        return []


def get_site_plugins_dir(domain: str) -> Path:
    site_path = Path(SITE_ROOT_DIR) / domain
    return site_path / "wp-content" / "plugins"


def _append_unique(items: list[str], value: str) -> None:
    if value in items:
        return
    items.append(value)


def build_preset_config() -> dict:
    plugins, active_plugins = _plugins_from_tsv()
    if not plugins:
        plugins, active_plugins = ["elementor"], ["elementor"]

    items = _load_tsv("plugins.tsv")
    status = {name: st for name, st in items}
    for p in list_custom_plugins():
        slug = p.name
        if status.get(slug, "active") != "disabled":
            _append_unique(active_plugins, slug)

    themes, active_themes = _themes_from_tsv()
    if not themes:
        themes, active_themes = ["hello-elementor"], ["hello-elementor"]
    active_theme = active_themes[0] if active_themes else "hello-elementor"
    return {
        "plugins": plugins,
        "active_plugins": active_plugins,
        "themes": themes,
        "active_theme": active_theme,
    }


def apply_preset_config(domain: str, preset_config: dict) -> bool:
    commands = _read_wp_cli_commands()
    commands.append(f"theme activate {preset_config['active_theme']}")
    for plugin in preset_config["active_plugins"]:
        commands.append(f"plugin activate {plugin}")
    for cmd in commands:
        if not wp_cmd(domain, cmd):
            logging.error("WordPress configuration failed: %s", cmd)
            return False
    return True


def _get_post_id_by_slug(domain: str, slug: str) -> int:
    ok, out, _ = wp_cmd_capture(
        domain, f"post list --post_type=page --name={slug} --field=ID"
    )
    if not ok:
        return 0
    out = (out or "").strip()
    if not out:
        return 0
    try:
        return int(out.split()[0])
    except ValueError:
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
        return int((out or "0").strip())
    except ValueError:
        return 0


def _set_static_front_page(domain: str, page_id: int) -> bool:
    if page_id <= 0:
        return False
    if not wp_cmd(domain, "option update show_on_front page"):
        return False
    if not wp_cmd(domain, f"option update page_on_front {page_id}"):
        return False
    return True


def _menu_exists(domain: str, name: str) -> bool:
    ok, out, _ = wp_cmd_capture(domain, "menu list --format=csv --fields=name")
    if not ok:
        return False
    lines = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    for ln in lines[1:] if len(lines) > 1 else []:
        if ln.strip() == name:
            return True
    return False


def _ensure_menu(domain: str, name: str) -> bool:
    if _menu_exists(domain, name):
        return True
    return wp_cmd(domain, f"menu create '{name}'")


def _menu_item_object_ids(domain: str, name: str) -> set[int]:
    ok, out, _ = wp_cmd_capture(
        domain, f"menu item list '{name}' --fields=object_id --format=ids"
    )
    if not ok:
        return set()
    txt = (out or "").strip()
    if not txt:
        return set()
    ids: set[int] = set()
    for token in txt.split():
        try:
            ids.add(int(token))
        except ValueError:
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


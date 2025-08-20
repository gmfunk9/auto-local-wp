"""Plugin management and Elementor seeding."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from config import (
    SITE_ROOT_DIR,
    ELEMENTOR_SEED,
    ELEMENTOR_TPL_PATH,
)
from modules.utils import log
from .cli import wp_cmd, wp_cmd_capture
from .site import list_custom_plugins, get_site_plugins_dir

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


def _append_agent_activity_log(line: str) -> None:
    path = ROOT_DIR / "AGENT_ACTIVITY.log"
    try:
        from datetime import datetime

        ts = datetime.utcnow().isoformat() + "Z"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{ts} {line}\n")
    except Exception:
        pass


def install_plugins(domain: str, plugins: list[str]) -> bool:
    custom_slugs = {p.name for p in list_custom_plugins()}
    for plugin in plugins:
        if plugin in custom_slugs:
            continue
        cmd = ["plugin", "install", plugin, "--force"]
        if not wp_cmd(domain, cmd):
            logging.error("Could not install plugin: %s", plugin)
            return False
    return True


def install_custom_plugins(domain: str) -> bool:
    dest_base = get_site_plugins_dir(domain)
    try:
        dest_base.mkdir(parents=True, exist_ok=True)
    except Exception as err:
        logging.error("Could not ensure plugins dir %s: %s", dest_base, err)
        return False
    for src in list_custom_plugins():
        dest = dest_base / src.name
        try:
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            log(f"PASS: Installed custom plugin {src.name}")
        except Exception as err:
            logging.error("Could not install custom plugin %s: %s", src.name, err)
            return False
    return True


def _list_elementor_templates() -> list[Path]:
    base = DATA_DIR / "elementor-page-templates"
    if not base.exists() or not base.is_dir():
        return []
    try:
        return [p for p in base.iterdir() if p.is_file() and p.suffix == ".json"]
    except Exception:
        return []


def _pick_template_for_page(templates: list[Path], key: str) -> Path | None:
    if not templates:
        return None
    key = key.lower()
    matches = [p for p in templates if key in p.name.lower()]
    if not matches:
        return None
    return sorted(matches, key=lambda p: p.name.lower())[0]


def _get_elementor_version(domain: str) -> str:
    ok, ver, _ = wp_cmd_capture(
        domain, ["plugin", "get", "elementor", "--field=version"]
    )
    if not ok:
        return ""
    return (ver or "").strip()


def _uploads_autolocal_dir(domain: str) -> Path:
    site = Path(SITE_ROOT_DIR) / domain
    return site / "wp-content" / "uploads" / "autolocal-tpl"


def stage_elementor_tpl(domain: str, src) -> str:
    try:
        src_path = Path(src)
        if not src_path.exists() or not src_path.is_file():
            logging.error("Template not found: %s", src_path)
            return ""
        dest_dir = _uploads_autolocal_dir(domain)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src_path.name
        if dest.exists():
            try:
                dest.unlink()
            except Exception as err:
                logging.error("Could not remove existing tpl %s: %s", dest, err)
                return ""
        shutil.copy2(src_path, dest)
        log(f"PASS: Staged Elementor template {dest}")
        return str(dest)
    except Exception as err:
        logging.error("Could not stage template: %s", err)
        return ""


def _cleanup_staged_tpl(domain: str, path_str: str) -> None:
    try:
        path = Path(path_str)
        if path.exists():
            try:
                path.unlink()
                log(f"PASS: Removed staged template {path}")
            except Exception as err:
                logging.error("Could not remove staged file %s: %s", path, err)
        temp_dir = _uploads_autolocal_dir(domain)
        try:
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
                log(f"PASS: Removed empty temp dir {temp_dir}")
        except Exception as err:
            logging.error("Could not remove temp dir %s: %s", temp_dir, err)
    except Exception:
        pass


def provision_elementor(domain: str) -> bool:
    if not ELEMENTOR_SEED:
        log("SKIP: Elementor seeding disabled by config")
        return True

    ok, _, _ = wp_cmd_capture(domain, ["plugin", "is-active", "elementor"])
    if not ok:
        log("INFO: Elementor not active, installing + activating")
        if not wp_cmd(domain, ["plugin", "install", "elementor", "--activate"]):
            logging.error("Could not install/activate elementor")
            return False

    templates = _list_elementor_templates()
    if not templates:
        fallback = Path(ELEMENTOR_TPL_PATH)
        if not fallback.exists():
            logging.error("No Elementor templates found")
            return False
        templates = [fallback]

    version = _get_elementor_version(domain)
    if not version:
        logging.error("Could not read Elementor version")
        return False

    pages: list[tuple[str, str]] = [
        ("home", "Home"),
        ("about", "About"),
        ("services", "Services"),
        ("contact", "Contact"),
    ]

    seeded = 0
    for slug, title in pages:
        tpl_path = _pick_template_for_page(templates, slug) or _pick_template_for_page(
            templates, "default"
        )
        if tpl_path is None:
            fp = Path(ELEMENTOR_TPL_PATH)
            tpl_path = fp if fp.exists() else None
        if tpl_path is None:
            logging.error("No template available for %s", slug)
            return False

        staged = stage_elementor_tpl(domain, tpl_path)
        if not staged:
            return False

        ok, out, err = wp_cmd_capture(
            domain,
            [
                "elementor",
                "library",
                "import",
                str(staged),
                "--returnType=ids",
                "--user=1",
            ],
        )
        _cleanup_staged_tpl(domain, staged)
        if not ok or not out.strip():
            logging.error("Elementor template import failed for %s: %s", slug, err)
            return False
        tpl_id = out.splitlines()[-1].strip()
        log(f"PASS: Imported template {tpl_id} for {slug}")

        ok, pid_txt, _ = wp_cmd_capture(
            domain, f"post list --post_type=page --name={slug} --field=ID"
        )
        page_id = 0
        if ok and (pid_txt or "").strip():
            try:
                page_id = int((pid_txt or "0").strip().split()[0])
            except ValueError:
                page_id = 0
        if page_id <= 0:
            ok, created, err = wp_cmd_capture(
                domain,
                [
                    "post",
                    "create",
                    "--post_type=page",
                    f"--post_title={title}",
                    f"--post_name={slug}",
                    "--post_status=publish",
                    "--porcelain",
                ],
            )
            if not ok or not (created or "").strip():
                logging.error("Could not create page %s: %s", slug, err)
                return False
            try:
                page_id = int((created or "0").strip())
            except ValueError:
                page_id = 0
        else:
            log(f"INFO: Found existing page {slug}:{page_id}")
        if page_id <= 0:
            logging.error("Invalid page id for %s", slug)
            return False

        if not wp_cmd(
            domain, ["post", "meta", "update", str(page_id), "_elementor_edit_mode", "builder"]
        ):
            logging.error("Could not set _elementor_edit_mode")
            return False

        if not wp_cmd(
            domain,
            ["post", "meta", "update", str(page_id), "_elementor_version", version],
        ):
            logging.error("Could not set _elementor_version")
            return False

        ok, tpl_data, err = wp_cmd_capture(
            domain, ["post", "meta", "get", tpl_id, "_elementor_data"]
        )
        if not ok:
            logging.error("Could not read tpl _elementor_data for %s: %s", slug, err)
            return False
        if not wp_cmd(
            domain,
            ["post", "meta", "update", str(page_id), "_elementor_data", tpl_data],
        ):
            logging.error("Could not copy _elementor_data to page")
            return False

        seeded += 1
        log(f"PASS: Seeded page {slug}:{page_id} from tpl {tpl_id}")

    if not wp_cmd(domain, ["rewrite", "flush", "--hard"]):
        logging.error("rewrite flush failed")
        return False

    _append_agent_activity_log(f"provision_elementor domain={domain} pages={seeded}")
    log(f"PASS: Elementor seeding complete for {seeded} pages")
    return True


"""Vault-driven plugins/themes management and Elementor seeding.

- Copies plugins and themes from the vault into new sites.
- Activates/deactivates plugins based on the vault's state.
- Activates the vault's active theme.
- Does not install from the marketplace.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
import subprocess

from config import (
    SITE_ROOT_DIR,
    ELEMENTOR_SEED,
    ELEMENTOR_TPL_PATH,
)
from modules.utils import log
from .cli import wp_cmd, wp_cmd_capture
from .site import get_site_plugins_dir

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


# Marketplace install removed. Vault-only policy.


VAULT_SITE = Path("/srv/http/funkpd_plugin_vault.local")
VAULT = VAULT_SITE / "wp-content"

def install_custom_plugins(domain: str) -> bool:
    """
    Copy all plugins and mu-plugins from the vault into the site.
    Run mkdir/cp as http so ownership is http:http.
    """
    import subprocess

    dest_plugins = get_site_plugins_dir(domain)
    dest_mu = dest_plugins.parent / "mu-plugins"

    try:
        # create the parent dirs as http
        subprocess.run(["sudo", "-u", "http", "mkdir", "-p", str(dest_plugins)], check=True)
        subprocess.run(["sudo", "-u", "http", "mkdir", "-p", str(dest_mu)], check=True)
    except Exception as err:
        logging.error("Could not ensure plugin dirs: %s", err)
        return False

    for subdir, dest_base in (("plugins", dest_plugins), ("mu-plugins", dest_mu)):
        src_dir = VAULT / subdir
        if not src_dir.exists():
            continue
        for src in src_dir.iterdir():
            dest = dest_base / src.name
            try:
                subprocess.run(
                    ["sudo", "-u", "http", "cp", "-rT", str(src), str(dest)],
                    check=True,
                )
                log(f"PASS: Installed {subdir[:-1]} {src.name}")
            except Exception as err:
                logging.error("Could not install %s %s: %s", subdir[:-1], src.name, err)
                return False
    return True


def remove_default_plugins(domain: str) -> bool:
    """Remove bundled default plugins (hello, akismet) if present.

    Best-effort: logs outcome and continues even if not present.
    """
    ok = True
    for slug in ("hello", "akismet"):
        if wp_cmd(domain, ["plugin", "delete", slug]):
            log(f"PASS: Removed default plugin {slug}")
        else:
            logging.info("Could not delete or not present: %s", slug)
    return ok


def sync_plugins_state_from_vault(domain: str) -> bool:
    """Activate/deactivate plugins to mirror the vault's state.

    Reads the vault's `wp plugin list --format=json` and ensures the new site
    activates/deactivates accordingly. Skips must-use/dropin statuses.
    """
    try:
        result = subprocess.run(
            [
                "sudo", "-u", "http", "wp",
                f"--path={VAULT_SITE}",
                "plugin", "list",
                "--fields=name,status",
                "--format=json",
                "--quiet",
            ],
            check=True, capture_output=True, text=True
        )
    except Exception as err:
        logging.error("Could not read plugin list from vault: %s", err)
        return False

    try:
        import json

        plugins_info = json.loads(result.stdout or "[]")
    except Exception as err:
        logging.error("Invalid JSON from vault plugin list: %s", err)
        return False

    ok = True
    for item in plugins_info:
        name = (item.get("name") or "").strip()
        status = (item.get("status") or "").strip().lower()
        if not name:
            continue
        if status in ("must-use", "dropin"):
            continue
        if status == "active":
            if not wp_cmd(domain, ["plugin", "activate", name]):
                logging.error("Failed to activate plugin: %s", name)
                ok = False
        else:
            if not wp_cmd(domain, ["plugin", "deactivate", name]):
                logging.error("Failed to deactivate plugin: %s", name)
                ok = False
    return ok


def install_custom_themes(domain: str) -> bool:
    """Copy all themes from the vault into the site as http:http."""
    dest_themes = Path(SITE_ROOT_DIR) / domain / "wp-content" / "themes"
    try:
        subprocess.run(["sudo", "-u", "http", "mkdir", "-p", str(dest_themes)], check=True)
    except Exception as err:
        logging.error("Could not ensure themes dir: %s", err)
        return False
    src_dir = VAULT / "themes"
    if not src_dir.exists():
        return True
    for src in src_dir.iterdir():
        dest = dest_themes / src.name
        try:
            subprocess.run(
                ["sudo", "-u", "http", "cp", "-rT", str(src), str(dest)],
                check=True,
            )
            log(f"PASS: Installed theme {src.name}")
        except Exception as err:
            logging.error("Could not install theme %s: %s", src.name, err)
            return False
    return True


def activate_vault_theme(domain: str) -> bool:
    """Activate the theme marked active in the vault."""
    try:
        result = subprocess.run(
            [
                "sudo", "-u", "http", "wp",
                f"--path={VAULT_SITE}",
                "theme", "list",
                "--fields=name,status",
                "--format=json",
                "--quiet",
            ],
            check=True, capture_output=True, text=True
        )
    except Exception as err:
        logging.error("Could not read theme list from vault: %s", err)
        return False
    try:
        import json

        themes_info = json.loads(result.stdout or "[]")
    except Exception as err:
        logging.error("Invalid JSON from vault theme list: %s", err)
        return False
    active = ""
    for item in themes_info:
        if (item.get("status") or "").strip().lower() == "active":
            active = (item.get("name") or "").strip()
            break
    if not active:
        logging.error("No active theme found in vault")
        return False
    return wp_cmd(domain, ["theme", "activate", active])


def prune_themes_not_in_vault(domain: str) -> bool:
    """Delete all site themes that are not present in the vault.

    Assumes vault themes are already copied and the vault's active theme
    has been activated on the site.
    """
    # Read vault themes
    try:
        result_v = subprocess.run(
            [
                "sudo", "-u", "http", "wp",
                f"--path={VAULT_SITE}",
                "theme", "list",
                "--fields=name",
                "--format=csv",
                "--quiet",
            ],
            check=True, capture_output=True, text=True,
        )
        lines = [ln.strip() for ln in (result_v.stdout or "").splitlines() if ln.strip()]
        vault_names = set(lines[1:]) if lines and lines[0].lower() == "name" else set(lines)
    except Exception as err:
        logging.error("Could not read vault themes: %s", err)
        return False

    # Read site themes (name + status for potential checks)
    try:
        result_s = subprocess.run(
            [
                "sudo", "-u", "http", "wp",
                f"--path={Path(SITE_ROOT_DIR) / domain}",
                "theme", "list",
                "--fields=name,status",
                "--format=json",
                "--quiet",
            ],
            check=True, capture_output=True, text=True,
        )
        import json

        site_info = json.loads(result_s.stdout or "[]")
    except Exception as err:
        logging.error("Could not read site themes: %s", err)
        return False

    ok = True
    for item in site_info:
        name = (item.get("name") or "").strip()
        if not name or name in vault_names:
            continue
        if not wp_cmd(domain, ["theme", "delete", name]):
            logging.error("Failed to delete theme not in vault: %s", name)
            ok = False
        else:
            log(f"PASS: Deleted theme not in vault: {name}")
    return ok




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
        log("SKIP: Elementor not active; skipping seeding (no auto-install)")
        return True

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

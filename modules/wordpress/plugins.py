# plugins.py
"""
Clean, robust replacement for the vault-driven plugins/themes management
and Elementor seeding module. Drop-in replacement for your existing file.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlsplit

from config import (
    SITE_ROOT_DIR,
    ELEMENTOR_SEED,
    ELEMENTOR_TPL_PATH,
)
from modules.utils import log, parse_json_relaxed  # parse_json_relaxed optional fallback
from .cli import wp_cmd, wp_cmd_capture, wp_cmd_json, wp_cmd_json_at_path
from .site import get_site_plugins_dir, _ensure_page as _ensure_page

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"

VAULT_SITE = Path("/srv/http/funkpd_plugin_vault.local")
VAULT_CONTENT = VAULT_SITE / "wp-content"


# -------------------------
# Filesystem helpers
# -------------------------
def _uploads_autolocal_dir(domain: str) -> Path:
    site = Path(SITE_ROOT_DIR) / domain
    return site / "wp-content" / "uploads" / "autolocal-tpl"


def _write_temp_file(domain: str, filename: str, content: str) -> Path:
    dest = _uploads_autolocal_dir(domain)
    dest.mkdir(parents=True, exist_ok=True)
    p = dest / filename
    p.write_text(content, encoding="utf-8")
    return p


# -------------------------
# Plugin / theme helpers
# -------------------------
def install_custom_plugins(domain: str) -> bool:
    dest_plugins = get_site_plugins_dir(domain)
    dest_mu = dest_plugins.parent / "mu-plugins"

    try:
        subprocess.run(["sudo", "-u", "http", "mkdir", "-p", str(dest_plugins)], check=True)
        subprocess.run(["sudo", "-u", "http", "mkdir", "-p", str(dest_mu)], check=True)
    except Exception as err:
        logging.error("Could not ensure plugin dirs: %s", err)
        return False

    for subdir, dest_base in (("plugins", dest_plugins), ("mu-plugins", dest_mu)):
        src_dir = VAULT_CONTENT / subdir
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
    ok = True
    for slug in ("hello", "akismet"):
        if wp_cmd(domain, ["plugin", "delete", slug]):
            log(f"PASS: Removed default plugin {slug}")
        else:
            logging.info("Could not delete or not present: %s", slug)
    return ok


def sync_plugins_state_from_vault(domain: str) -> bool:
    ok, plugins_info = wp_cmd_json_at_path(VAULT_SITE, [
        "plugin", "list", "--fields=name,status",
    ])
    if not ok:
        logging.error("Could not read plugin list from vault")
        return False
    if not isinstance(plugins_info, list):
        logging.error("Invalid JSON from vault plugin list (not list)")
        return False

    ok = True
    for item in plugins_info:
        try:
            name = (item.get("name") or "").strip()
            status = (item.get("status") or "").strip().lower()
        except Exception:
            continue
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
    dest_themes = Path(SITE_ROOT_DIR) / domain / "wp-content" / "themes"
    try:
        subprocess.run(["sudo", "-u", "http", "mkdir", "-p", str(dest_themes)], check=True)
    except Exception as err:
        logging.error("Could not ensure themes dir: %s", err)
        return False
    src_dir = VAULT_CONTENT / "themes"
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
    ok, themes_info = wp_cmd_json_at_path(VAULT_SITE, [
        "theme", "list", "--fields=name,status",
    ])
    if not ok:
        logging.error("Could not read theme list from vault")
        return False
    if not isinstance(themes_info, list):
        logging.error("Invalid JSON from vault theme list (not list)")
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
    ok, vault_list = wp_cmd_json_at_path(VAULT_SITE, [
        "theme", "list", "--fields=name",
    ])
    if not ok:
        logging.error("Could not read vault themes")
        return False
    try:
        vault_names = {str(it.get("name", "")).strip() for it in vault_list if isinstance(it, dict)}
    except Exception:
        vault_names = set()

    ok, site_info = wp_cmd_json(domain, [
        "theme", "list", "--fields=name,status",
    ])
    if not ok or not isinstance(site_info, list):
        logging.error("Could not read site themes")
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


# -------------------------
# Elementor template helpers
# -------------------------
def _list_elementor_templates() -> List[Path]:
    base = DATA_DIR / "elementor-page-templates"
    if not base.exists() or not base.is_dir():
        return []
    try:
        return [p for p in base.iterdir() if p.is_file() and p.suffix == ".json"]
    except Exception:
        return []


def _pick_template_for_page(templates: List[Path], key: str) -> Path | None:
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


# -------------------------
# Media / URL parsing helpers
# -------------------------
def _find_upload_urls(blob: str) -> Tuple[List[str], str]:
    """
    Return list of unique upload URLs and the host of the first URL.
    Works on blobs with escaped slashes.
    """
    if not blob:
        return [], ""
    # simple regex limited to uploads path (kept from original but safe)
    import re
    urls = re.findall(r'http[^\"]+uploads[^\"]+\.(?:jpg|jpeg|png|webp)', blob, re.I)
    cleaned: List[str] = []
    seen = set()
    for u in urls:
        cu = u.replace("\\/", "/")
        if cu in seen:
            continue
        seen.add(cu)
        cleaned.append(cu)
    host = urlsplit(cleaned[0]).netloc if cleaned else ""
    return cleaned, host


# at top of file, with other imports
import os
os.environ.setdefault("WP_CLI_PHP_ARGS", "-d display_errors=0 -d display_startup_errors=0")

# replace the old _import_media_from_vault with this:
def _import_media_from_vault(domain: str, clean_url: str) -> str:
    """
    Import a file from the vault into the site and return the new attachment id.
    Sanitizes WP-CLI output: extracts the last numeric token from stdout.
    """
    if not clean_url:
        return ""
    idx = clean_url.find("/wp-content/")
    if idx == -1:
        return ""
    rel = clean_url[idx:]  # keep '/wp-content/uploads/...'
    src = VAULT_SITE / rel.lstrip("/")

    ok, out, err = wp_cmd_capture(domain, ["media", "import", str(src), "--porcelain"])
    if not ok:
        logging.error("wp media import failed for %s: %s", src, err)
        return ""

    # Prefer stdout, but it may contain PHP warnings. Extract last numeric token.
    text = (out or "") + "\n" + (err or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        logging.error("media import returned empty output for %s", src)
        return ""

    # Look for the last line that ends with an integer, or any numeric-only line.
    import re
    for ln in reversed(lines):
        m = re.search(r"(\d+)\s*$", ln)
        if m:
            return m.group(1)

    # Fallback: find any numeric token anywhere in output
    for ln in lines:
        toks = re.findall(r"\d+", ln)
        if toks:
            return toks[-1]

    logging.warning("media import returned no numeric id for %s; raw out=%s err=%s", src, out, err)
    return ""


# -------------------------
# JSON-based id remap (no regex guessing)
# -------------------------
def _safe_load_json(blob: str):
    """
    Try strict json.loads first, fallback to parse_json_relaxed if available.
    Returns parsed object or raises.
    """
    try:
        return json.loads(blob)
    except Exception:
        try:
            return parse_json_relaxed(blob)
        except Exception:
            # last attempt: replace escaped slashes and retry
            return json.loads(blob.replace("\\/", "/"))


import json, re

_size_suffix_re = re.compile(r"(?:-\d{2,5}x\d{2,5})(\.\w{3,4})(?:$|\?)", re.IGNORECASE)

def _normalize_url(u: str) -> str:
    # de-escape, strip query/fragments, collapse repeated slashes (except scheme)
    u = u.replace("\\/", "/")
    u = u.split("?", 1)[0].split("#", 1)[0]
    return u

def _unsize(u: str) -> str:
    return _size_suffix_re.sub(r"\1", u)

import json, re

_size_suffix_re = re.compile(r"(?:-\d{2,5}x\d{2,5})(\.\w{3,4})(?:$|\?)", re.IGNORECASE)

def _normalize_url(u: str) -> str:
    u = u.replace("\\/", "/")
    u = u.split("?", 1)[0].split("#", 1)[0]
    return u

def _unsize(u: str) -> str:
    return _size_suffix_re.sub(r"\1", u)

def json_update_ids_from_urls(blob: str, mapping: dict) -> tuple[str, int]:
    """
    Walk JSON and set dict['id'] based on dict['url'] using provided URL->ID mapping.
    Prints detailed logs of each step.
    Returns (new_blob_str, hits_count).
    """
    if not mapping:
        print("[JUIFU DEBUG] No mapping provided, returning blob unchanged")
        return blob, 0

    data = json.loads(blob.replace("\\/", "/"))
    hits = 0

    def lookup_id(u: str):
        nu = _normalize_url(u)
        unsized = _unsize(nu)
        nid = mapping.get(nu) or mapping.get(unsized)
        print(f"[JUIFU LOOKUP] url={u} normalized={nu} unsized={unsized} -> id={nid}")
        return nid

    def walk(obj, path="root"):
        nonlocal hits
        if isinstance(obj, dict):
            if "url" in obj:
                u = obj.get("url")
                nid = lookup_id(u)
                if nid is not None:
                    old = obj.get("id")
                    try:
                        obj["id"] = int(nid)
                    except Exception:
                        obj["id"] = nid
                    hits += 1
                    print(f"[JUIFU UPDATE] {path}: id {old} -> {obj['id']} for {u}")
                else:
                    print(f"[JUIFU SKIP] {path}: url {u} not in mapping")
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        # primitives ignored

    print("[JUIFU DEBUG] Starting walk")
    walk(data)
    print(f"[JUIFU DEBUG] Completed walk, hits={hits}")
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False), hits


# -------------------------
# Safe meta setter to avoid "Argument list too long"
# -------------------------
def _update_post_meta_from_file(domain: str, post_id: int, key: str, value: str) -> bool:
    """
    Write 'value' to a temp file inside site's autolocal dir and run wp eval-file
    which reads the file and updates post meta. Returns True on success.
    """
    try:
        tmpjson = _write_temp_file(domain, f"{key}-{post_id}.json", value)
        tmpphp = _write_temp_file(
            domain,
            f"setmeta-{key}-{post_id}.php",
            '<?php '
            f'$p={int(post_id)}; $k="{key}"; $f="{str(tmpjson)}"; '
            '$v=file_get_contents($f); update_post_meta($p,$k,$v); echo "OK";',
        )
        ok = wp_cmd(domain, ["eval-file", str(tmpphp)])
        try:
            tmpphp.unlink(missing_ok=True)
            tmpjson.unlink(missing_ok=True)
        except Exception:
            pass
        return ok
    except Exception as e:
        logging.error("Failed file-based post meta update: %s", e)
        return False


# -------------------------
# High-level provisioning
# -------------------------
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

    pages: List[Tuple[str, str]] = [
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

        ok, rows = wp_cmd_json(
            domain, [
                "post", "list", "--post_type=page", f"--name={slug}", "--fields=ID",
            ]
        )
        page_id = 0
        if ok and isinstance(rows, list) and rows:
            try:
                first = rows[0]
                val = first.get("ID") if isinstance(first, dict) else None
                page_id = int(val) if val is not None else 0
            except Exception:
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

        # Direct copy (no remap). Suitable if templates reference site-relative urls.
        if not _update_post_meta_from_file(domain, page_id, "_elementor_data", tpl_data):
            logging.error("Could not copy _elementor_data to page")
            return False

        seeded += 1
        log(f"PASS: Seeded page {slug}:{page_id} from tpl {tpl_id}")

    if not wp_cmd(domain, ["elementor", "flush_css"]):
        logging.error("Elementor CSS flush failed")
        return False
    if not wp_cmd(domain, ["rewrite", "flush", "--hard"]):
        logging.error("rewrite flush failed")
        return False

    log(f"PASS: Elementor seeding complete for {seeded} pages")
    return True


# -------------------------
# Provision from vault preset (remap URLs -> ids)
# -------------------------
def _vault_page_id_for_slug(slug: str) -> str:
    ok, rows = wp_cmd_json_at_path(VAULT_SITE, [
        "post", "list",
        "--post_type=page",
        f"--name={slug}",
        "--fields=ID",
    ])
    if not ok or not isinstance(rows, list) or not rows:
        return ""
    try:
        first = rows[0]
        val = first.get("ID") if isinstance(first, dict) else None
        return str(val).strip() if val is not None else ""
    except Exception:
        return ""


def _vault_get_meta(post_id: str, key: str) -> str:
    ok, rows = wp_cmd_json_at_path(VAULT_SITE, [
        "post", "meta", "list", post_id,
        f"--keys={key}",
        "--fields=meta_value",
    ])
    if not ok or not isinstance(rows, list) or not rows:
        return ""
    try:
        first = rows[0]
        val = first.get("meta_value") if isinstance(first, dict) else None
        return str(val) if val is not None else ""
    except Exception:
        return ""


def _parse_preset(preset: str) -> Tuple[str, str]:
    if not preset:
        return "", ""
    if "-" not in preset:
        return preset, "1"
    key, ver = preset.rsplit("-", 1)
    return key, ver


def provision_elementor_from_vault_preset(domain: str, preset: str) -> bool:
    key, ver = _parse_preset(preset)
    if not key or not ver:
        logging.error("Invalid preset value: %s", preset)
        return False

    version = _get_elementor_version(domain)
    if not version:
        logging.error("Could not read Elementor version")
        return False

    pages: List[Tuple[str, str]] = [
        ("home", "Home"),
        ("about", "About"),
        ("contact", "Contact"),
    ]

    seeded = 0
    for slug, title in pages:
        vault_slug = f"{key}-{slug}-{ver}"
        vid = _vault_page_id_for_slug(vault_slug)
        if not vid:
            logging.error("Vault page not found: %s", vault_slug)
            return False
        blob = _vault_get_meta(vid, "_elementor_data")
        if not blob:
            logging.error("No _elementor_data for vault page %s", vault_slug)
            return False

        # find upload urls from vault blob
        urls, vault_host = _find_upload_urls(blob)
        url_to_id: Dict[str, str] = {}
        for u in urls:
            nid = _import_media_from_vault(domain, u)
            if not nid:
                logging.error("Media import failed for %s", u)
                continue
            url_to_id[u] = nid

        # normalize slashes and placeholders
        blob2 = blob.replace("\\/", "/")
        blob2 = _apply_placeholders_stub(blob2)

        # swap host first so JSON will contain new-site URLs
        if vault_host:
            blob2 = blob2.replace(vault_host, domain)

        # build mapping for both vault-host and new-host keys so walker hits
        mapping = dict(url_to_id)
        if vault_host:
            mapping.update({u.replace(vault_host, domain): nid for u, nid in url_to_id.items()})

        # JSON-walk update ids (safe, logged)
        blob3, hits = json_update_ids_from_urls(blob2, mapping)
        print(f"[INFO] remap hits={hits}")

        page_id = _ensure_page(domain, title=title, slug=slug, content="")
        if page_id <= 0:
            logging.error("Could not ensure page %s", slug)
            return False

        if not wp_cmd(domain, [
            "post", "meta", "update", str(page_id), "_elementor_edit_mode", "builder",
        ]):
            logging.error("Could not set _elementor_edit_mode")
            return False
        if not wp_cmd(domain, [
            "post", "meta", "update", str(page_id), "_elementor_version", version,
        ]):
            logging.error("Could not set _elementor_version")
            return False

        if not wp_cmd(domain, [
            "post", "meta", "update", str(page_id), "_elementor_data", blob3,
        ]):
            logging.error("Could not set _elementor_data on %s", slug)
            return False

        seeded += 1
        log(f"PASS: Seeded {slug}:{page_id} from vault {vault_slug}")

    if not wp_cmd(domain, ["elementor", "flush_css"]):
        logging.error("Elementor CSS flush failed")
        return False

    log(f"PASS: Vault Elementor seeding complete for {seeded} pages")
    return True



def _apply_placeholders_stub(text: str, mapping: dict[str, str] | None = None) -> str:
    """
    No-op by default. If a mapping is provided, replace keys with values.
    Keeps behaviour deterministic and safe when called without args.
    """
    if not mapping:
        return text
    try:
        for k, v in mapping.items():
            # best-effort replace; ignore failures
            text = text.replace(k, v)
    except Exception:
        # swallow to avoid breaking provisioning pipeline
        pass
    return text


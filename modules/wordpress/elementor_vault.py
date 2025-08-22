from __future__ import annotations

import logging
import re
from pathlib import Path

from modules.utils import (
    log,
    require,
    find_upload_urls,
    update_json_ids_from_urls,
    apply_placeholders,
)
from .cli import wp_cmd, wp_cmd_json, wp_cmd_json_at_path
from .site import _ensure_page
from .elementor_templates import set_elementor_meta, get_elementor_version


VAULT_SITE = Path("/srv/http/funkpd_plugin_vault.local")


def import_media_from_vault(domain: str, clean_url: str) -> str:
    if not clean_url:
        return ""
    if "/wp-content/" not in clean_url:
        return ""

    index = clean_url.find("/wp-content/")
    rel_path = clean_url[index:].lstrip("/")
    src = VAULT_SITE / rel_path

    ok, data = wp_cmd_json(domain, ["media", "import", str(src), "--porcelain"])
    if not require(ok, f"Media import failed for {src}", "error"):
        return ""

    if isinstance(data, (int, float)):
        return str(int(data))

    if isinstance(data, str):
        matches = re.findall(r"\d+", data)
        if matches:
            return matches[-1]
        return ""

    if isinstance(data, list):
        for val in reversed(data):
            try:
                return str(int(str(val).strip()))
            except Exception:
                continue

    logging.warning(f"Media import returned no numeric id for {src}")
    return ""


def get_vault_page_id(slug: str) -> str:
    ok, rows = wp_cmd_json_at_path(
        VAULT_SITE,
        ["post", "list", "--post_type=page", f"--name={slug}", "--fields=ID"],
    )
    valid = ok and isinstance(rows, list) and rows
    if not require(valid, f"Vault page not found: {slug}", "error"):
        return ""
    first_id = str(rows[0].get("ID", "")).strip()
    return first_id


def get_vault_meta(post_id: str, key: str) -> str:
    ok, rows = wp_cmd_json_at_path(
        VAULT_SITE,
        ["post", "meta", "list", post_id, f"--keys={key}", "--fields=meta_value"],
    )
    if not ok:
        require(False, f"No {key} for vault page {post_id}", "error")
        return ""
    if not isinstance(rows, list):
        require(False, f"No {key} for vault page {post_id}", "error")
        return ""
    if not rows:
        require(False, f"No {key} for vault page {post_id}", "error")
        return ""
    value = str(rows[0].get("meta_value", ""))
    return value


def prepare_vault_data(
    blob: str, domain: str, vault_host: str
) -> tuple[str, int]:
    urls, _ = find_upload_urls(blob)
    url_to_id: dict[str, str] = {}

    for url in urls:
        new_id = import_media_from_vault(domain, url)
        if not require(bool(new_id), f"Media import failed for {url}", "error"):
            continue
        url_to_id[url] = new_id

    blob = blob.replace("\\/", "/")
    blob = apply_placeholders(blob)

    if vault_host:
        blob = blob.replace(vault_host, domain)

    mapping = dict(url_to_id)
    if vault_host:
        for url, new_id in url_to_id.items():
            remapped = url.replace(vault_host, domain)
            mapping[remapped] = new_id

    return update_json_ids_from_urls(blob, mapping)


def seed_vault_page(
    domain: str,
    slug: str,
    title: str,
    key: str,
    version: str,
    elementor_version: str,
) -> bool:
    vault_slug = f"{key}-{slug}-{version}"
    vault_id = get_vault_page_id(vault_slug)
    if not require(bool(vault_id), f"Vault page not found: {vault_slug}", "error"):
        return False

    blob = get_vault_meta(vault_id, "_elementor_data")
    if not require(
        bool(blob), f"No _elementor_data for vault page {vault_slug}", "error"
    ):
        return False

    urls, vault_host = find_upload_urls(blob)
    blob, hits = prepare_vault_data(blob, domain, vault_host)
    log(f"INFO: remap hits={hits}")

    page_id = _ensure_page(domain, title=title, slug=slug, content="")
    if not require(page_id > 0, f"Could not ensure page {slug}", "error"):
        return False

    ok = set_elementor_meta(domain, page_id, elementor_version)
    if not require(ok, f"Could not set elementor meta for {slug}", "error"):
        return False

    ok = wp_cmd(
        domain, ["post", "meta", "update", str(page_id), "_elementor_data", blob]
    )
    if not require(ok, f"Could not set _elementor_data on {slug}", "error"):
        return False

    log(f"PASS: Seeded {slug}:{page_id} from vault {vault_slug}")
    return True


def parse_preset(preset: str) -> tuple[str, str]:
    if not preset:
        return preset, "1"
    if "-" not in preset:
        return preset, "1"
    parts = preset.rsplit("-", 1)
    return parts[0], parts[1]


def provision_elementor_from_vault_preset(domain: str, preset: str) -> bool:
    key, version = parse_preset(preset)
    has_key = bool(key)
    if not require(has_key, f"Invalid preset value: {preset}", "error"):
        return False
    has_version = bool(version)
    if not require(has_version, f"Invalid preset value: {preset}", "error"):
        return False

    elementor_version = get_elementor_version(domain)
    if not require(
        bool(elementor_version), "Could not read Elementor version", "error"
    ):
        return False

    pages = [("home", "Home"), ("about", "About"), ("contact", "Contact")]
    seeded = 0

    for slug, title in pages:
        ok = seed_vault_page(
            domain, slug, title, key, version, elementor_version
        )
        if not require(ok, f"Could not seed vault page {slug}", "error"):
            return False
        seeded += 1

    ok = wp_cmd(domain, ["elementor", "flush_css"])
    if not require(ok, "Elementor CSS flush failed", "error"):
        return False

    log(f"PASS: Vault Elementor seeding complete for {seeded} pages")
    return True


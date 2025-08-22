from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from config import SITE_ROOT_DIR, ELEMENTOR_SEED, ELEMENTOR_TPL_PATH
from modules.utils import (
    log,
    require,
    run_as_http,
    get_temp_dir,
    write_temp_file,
    copy_directory_item,
    copy_directory_tree,
    cleanup_staged_template,
    normalize_url,
    remove_size_suffix,
    find_upload_urls,
    update_json_ids_from_urls,
    apply_placeholders,
)
from .cli import wp_cmd, wp_cmd_capture, wp_cmd_json, wp_cmd_json_at_path
from .site import get_site_plugins_dir, _ensure_page

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
VAULT_SITE = Path("/srv/http/funkpd_plugin_vault.local")
VAULT_CONTENT = VAULT_SITE / "wp-content"

 


 


def install_custom_plugins(domain: str) -> bool:
    plugins_dir = get_site_plugins_dir(domain)
    mu_dir = plugins_dir.parent / "mu-plugins"

    made_plugins = run_as_http(["mkdir", "-p", str(plugins_dir)])
    made_mu = run_as_http(["mkdir", "-p", str(mu_dir)])
    created_dirs = made_plugins and made_mu

    if not require(created_dirs, "Could not create plugin directories", "error"):
        return False

    copied_plugins = copy_directory_tree(VAULT_CONTENT / "plugins", plugins_dir, "plugin")
    copied_mu = copy_directory_tree(VAULT_CONTENT / "mu-plugins", mu_dir, "mu-plugin")
    return copied_plugins and copied_mu


def remove_single_plugin(domain: str, slug: str) -> bool:
    deleted = wp_cmd(domain, ["plugin", "delete", slug])
    return require(deleted, f"Removed default plugin {slug}", "info")


def remove_default_plugins(domain: str) -> bool:
    plugin_slugs = ["hello", "akismet"]

    for slug in plugin_slugs:
        success = remove_single_plugin(domain, slug)
        if not success:
            return False

    return True


def sync_plugins_state_from_vault(domain: str) -> bool:
    ok, plugin_rows = wp_cmd_json_at_path(VAULT_SITE, ["plugin", "list", "--fields=name,status"])
    valid_list = ok and isinstance(plugin_rows, list)
    if not require(valid_list, "Could not read plugin list from vault", "error"):
        return False

    all_successful = True
    for plugin in plugin_rows:
        plugin_name = str(plugin.get("name", "")).strip()
        plugin_status = str(plugin.get("status", "")).strip().lower()

        if not plugin_name:
            continue
        if plugin_status == "must-use":
            continue
        if plugin_status == "dropin":
            continue

        if plugin_status == "active":
            action = "activate"
        else:
            action = "deactivate"

        executed = wp_cmd(domain, ["plugin", action, plugin_name])
        result = require(executed, f"Failed to {action} plugin: {plugin_name}", "error")
        if not result:
            all_successful = False

    return all_successful


def install_custom_themes(domain: str) -> bool:
    themes_dir = Path(SITE_ROOT_DIR) / domain / "wp-content" / "themes"

    made_dir = run_as_http(["mkdir", "-p", str(themes_dir)])
    if not require(made_dir, "Could not create themes directory", "error"):
        return False

    copied = copy_directory_tree(VAULT_CONTENT / "themes", themes_dir, "theme")
    return copied


def activate_vault_theme(domain: str) -> bool:
    ok, theme_rows = wp_cmd_json_at_path(VAULT_SITE, ["theme", "list", "--fields=name,status"])
    valid_list = ok and isinstance(theme_rows, list)
    if not require(valid_list, "Could not read theme list from vault", "error"):
        return False

    active_theme = ""
    for theme in theme_rows:
        status = str(theme.get("status", "")).strip().lower()
        if status == "active":
            active_theme = str(theme.get("name", "")).strip()
            break

    has_theme = bool(active_theme)
    if not require(has_theme, "No active theme found in vault", "error"):
        return False

    activated = wp_cmd(domain, ["theme", "activate", active_theme])
    return activated


def prune_themes_not_in_vault(domain: str) -> bool:
    ok, vault_rows = wp_cmd_json_at_path(VAULT_SITE, ["theme", "list", "--fields=name"])
    if not ok:
        return False

    vault_names = set()
    for theme in vault_rows:
        theme_name = str(theme.get("name", "")).strip()
        vault_names.add(theme_name)

    ok, site_rows = wp_cmd_json(domain, ["theme", "list", "--fields=name,status"])
    valid_list = ok and isinstance(site_rows, list)
    if not require(valid_list, "Could not read theme list from site", "error"):
        return False

    all_successful = True
    for theme in site_rows:
        theme_name = str(theme.get("name", "")).strip()
        in_vault = theme_name in vault_names

        if not theme_name:
            continue
        if in_vault:
            continue
        deleted = wp_cmd(domain, ["theme", "delete", theme_name])
        result = require(
            deleted, f"Deleted theme not in vault: {theme_name}", "warning"
        )
        if not result:
            all_successful = False

    return all_successful


def list_elementor_templates() -> list[Path]:
    base = DATA_DIR / "elementor-page-templates"
    exists = base.exists()
    is_dir = base.is_dir()
    if not exists:
        return []
    if not is_dir:
        return []

    templates = []
    for path in base.iterdir():
        if path.suffix == ".json":
            templates.append(path)

    return templates


def pick_template_for_page(templates: list[Path], key: str) -> Path | None:
    if not templates:
        return None

    lower_key = key.lower()
    matches = []
    for path in templates:
        if lower_key in path.name.lower():
            matches.append(path)

    if not matches:
        return None

    # NOTE: originally used min() inline. Rewritten explicitly.
    chosen = matches[0]
    for path in matches:
        if path.name.lower() < chosen.name.lower():
            chosen = path

    return chosen


def get_elementor_version(domain: str) -> str:
    ok, data = wp_cmd_json(domain, ["plugin", "get", "elementor", "--field=version"])
    if not ok:
        return ""

    if not data:
        return ""

    version_string = str(data).strip()
    return version_string


def stage_elementor_template(domain: str, src_path: Path) -> str:
    exists = src_path.exists()
    if not require(exists, f"Template not found: {src_path}", "error"):
        return ""

    dest = get_temp_dir(domain, SITE_ROOT_DIR) / src_path.name
    if dest.exists():
        dest.unlink()

    shutil.copy2(src_path, dest)
    log(f"PASS: Staged Elementor template {dest}")
    return str(dest)


 


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


 


def update_post_meta_from_file(domain: str, post_id: int, key: str, value: str) -> bool:
    temp_dir = get_temp_dir(domain, SITE_ROOT_DIR)
    json_path = temp_dir / f"{key}-{post_id}.json"
    php_path = temp_dir / f"setmeta-{key}-{post_id}.php"

    php_code = (
        f'<?php $p={post_id}; $k="{key}"; '
        f'$f="{json_path}"; '
        '$v=file_get_contents($f); update_post_meta($p,$k,$v); echo "OK";'
    )

    try:
        json_file = write_temp_file(domain, f"{key}-{post_id}.json", value, SITE_ROOT_DIR)
        php_file = write_temp_file(
            domain, f"setmeta-{key}-{post_id}.php", php_code, SITE_ROOT_DIR
        )

        success = wp_cmd(domain, ["eval-file", str(php_file)])

        json_file.unlink(missing_ok=True)
        php_file.unlink(missing_ok=True)

        return success
    except Exception as error:
        logging.error(f"Failed file-based post meta update: {error}")
        return False
    # INCONSISTENCY: uses try/except for logging, but could apply require()
    # on intermediate results for consistency.


def parse_preset(preset: str) -> tuple[str, str]:
    if not preset:
        return preset, "1"

    if "-" not in preset:
        return preset, "1"

    parts = preset.rsplit("-", 1)
    return parts[0], parts[1]


 


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


def get_or_create_page(domain: str, slug: str, title: str) -> int:
    ok, rows = wp_cmd_json(
        domain,
        ["post", "list", "--post_type=page", f"--name={slug}", "--fields=ID"],
    )
    if ok:
        if isinstance(rows, list):
            if rows:
                return int(rows[0].get("ID", 0))

    ok, created, _ = wp_cmd_capture(
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
    valid = ok and created.strip()
    if not require(valid, f"Could not create page {slug}", "error"):
        return 0
    return int(created.strip())


def set_elementor_meta(domain: str, page_id: int, version: str) -> bool:
    updates = [
        ("_elementor_edit_mode", "builder"),
        ("_elementor_version", version),
    ]

    for meta_key, meta_value in updates:
        ok = wp_cmd(
            domain, ["post", "meta", "update", str(page_id), meta_key, meta_value]
        )
        if not require(ok, f"Could not set {meta_key} for page {page_id}", "error"):
            return False

    return True


def import_elementor_template(domain: str, template_path: str) -> str:
    staged_path = stage_elementor_template(domain, Path(template_path))
    if not staged_path:
        return ""

    ok, data = wp_cmd_json(
        domain,
        [
            "elementor",
            "library",
            "import",
            staged_path,
            "--returnType=ids",
            "--user=1",
        ],
    )
    cleanup_staged_template(domain, staged_path, SITE_ROOT_DIR)

    if not require(ok, f"Elementor template import failed for {template_path}", "error"):
        return ""

    if isinstance(data, list):
        if data:
            return str(data[-1]).strip()

    if isinstance(data, (int, float, str)):
        return str(data).strip()

    return ""


def copy_template_data(domain: str, template_id: str, page_id: int) -> bool:
    ok, template_data, _ = wp_cmd_capture(
        domain, ["post", "meta", "get", template_id, "_elementor_data"]
    )
    if not require(ok, f"Could not read _elementor_data for template {template_id}", "error"):
        return False

    return update_post_meta_from_file(domain, page_id, "_elementor_data", template_data)


def get_template_for_page(templates: list[Path], slug: str) -> Path | None:
    template = pick_template_for_page(templates, slug)
    if template:
        return template

    template = pick_template_for_page(templates, "default")
    if template:
        return template

    fallback = Path(ELEMENTOR_TPL_PATH)
    exists = fallback.exists()
    if exists:
        return fallback
    return None


def seed_elementor_page(domain: str, slug: str, title: str, templates: list[Path], version: str) -> bool:
    template = get_template_for_page(templates, slug)
    has_template = bool(template)
    if not require(has_template, f"No template available for {slug}", "error"):
        return False

    template_id = import_elementor_template(domain, str(template))
    has_id = bool(template_id)
    if not require(has_id, f"Elementor template import failed for {slug}", "error"):
        return False

    log(f"PASS: Imported template {template_id} for {slug}")

    page_id = get_or_create_page(domain, slug, title)
    valid_page = page_id > 0
    if not require(valid_page, f"Could not create page {slug}", "error"):
        return False

    ok = set_elementor_meta(domain, page_id, version)
    if not require(ok, f"Could not set elementor meta for {slug}", "error"):
        return False

    ok = copy_template_data(domain, template_id, page_id)
    if not require(ok, "Could not copy _elementor_data to page", "error"):
        return False

    log(f"PASS: Seeded page {slug}:{page_id} from template {template_id}")
    return True


def flush_elementor(domain: str) -> bool:
    commands = [["elementor", "flush_css"], ["rewrite", "flush", "--hard"]]

    for command in commands:
        ok = wp_cmd(domain, command)
        if not require(ok, f"Command failed: {' '.join(command)}", "error"):
            return False

    return True


def prepare_vault_data(blob: str, domain: str, vault_host: str) -> tuple[str, int]:
    urls, _ = find_upload_urls(blob)
    url_to_id = {}

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


def seed_vault_page(domain: str, slug: str, title: str, key: str, version: str, elementor_version: str) -> bool:
    vault_slug = f"{key}-{slug}-{version}"
    vault_id = get_vault_page_id(vault_slug)
    if not require(bool(vault_id), f"Vault page not found: {vault_slug}", "error"):
        return False

    blob = get_vault_meta(vault_id, "_elementor_data")
    if not require(bool(blob), f"No _elementor_data for vault page {vault_slug}", "error"):
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

    ok = wp_cmd(domain, ["post", "meta", "update", str(page_id), "_elementor_data", blob])
    if not require(ok, f"Could not set _elementor_data on {slug}", "error"):
        return False

    log(f"PASS: Seeded {slug}:{page_id} from vault {vault_slug}")
    return True


def provision_elementor(domain: str) -> bool:
    if not require(ELEMENTOR_SEED, "Elementor seeding disabled by config", "info"):
        return True

    ok = wp_cmd(domain, ["plugin", "is-active", "elementor"])
    if not require(ok, "Elementor not active; skipping seeding", "info"):
        return True

    templates = list_elementor_templates()
    if not templates:
        fallback = Path(ELEMENTOR_TPL_PATH)
        if not require(fallback.exists(), "No Elementor templates found", "error"):
            return False
        templates = [fallback]

    version = get_elementor_version(domain)
    if not require(bool(version), "Could not read Elementor version", "error"):
        return False

    pages = [("home", "Home"), ("about", "About"), ("services", "Services"), ("contact", "Contact")]
    seeded = 0

    for slug, title in pages:
        ok = seed_elementor_page(domain, slug, title, templates, version)
        if not require(ok, f"Could not seed page {slug}", "error"):
            return False
        seeded += 1

    ok = flush_elementor(domain)
    if not require(ok, "Could not flush Elementor CSS/rewrite", "error"):
        return False

    log(f"PASS: Elementor seeding complete for {seeded} pages")
    return True


def provision_elementor_from_vault_preset(domain: str, preset: str) -> bool:
    key, version = parse_preset(preset)
    has_key = bool(key)
    if not require(has_key, f"Invalid preset value: {preset}", "error"):
        return False
    has_version = bool(version)
    if not require(has_version, f"Invalid preset value: {preset}", "error"):
        return False

    elementor_version = get_elementor_version(domain)
    if not require(bool(elementor_version), "Could not read Elementor version", "error"):
        return False

    pages = [("home", "Home"), ("about", "About"), ("contact", "Contact")]
    seeded = 0

    for slug, title in pages:
        ok = seed_vault_page(domain, slug, title, key, version, elementor_version)
        if not require(ok, f"Could not seed vault page {slug}", "error"):
            return False
        seeded += 1

    ok = wp_cmd(domain, ["elementor", "flush_css"])
    if not require(ok, "Elementor CSS flush failed", "error"):
        return False

    log(f"PASS: Vault Elementor seeding complete for {seeded} pages")
    return True

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from config import SITE_ROOT_DIR, ELEMENTOR_SEED, ELEMENTOR_TPL_PATH
from modules.utils import (
    log,
    require,
    get_temp_dir,
    write_temp_file,
    cleanup_staged_template,
)
from .cli import wp_cmd, wp_cmd_capture, wp_cmd_json


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


def list_elementor_templates() -> list[Path]:
    base = DATA_DIR / "elementor-page-templates"
    exists = base.exists()
    is_dir = base.is_dir()
    if not exists:
        return []
    if not is_dir:
        return []

    templates: list[Path] = []
    for path in base.iterdir():
        if path.suffix == ".json":
            templates.append(path)

    return templates


def pick_template_for_page(
    templates: list[Path], key: str
) -> Path | None:
    if not templates:
        return None

    lower_key = key.lower()
    matches: list[Path] = []
    for path in templates:
        if lower_key in path.name.lower():
            matches.append(path)

    if not matches:
        return None

    chosen = matches[0]
    for path in matches:
        if path.name.lower() < chosen.name.lower():
            chosen = path

    return chosen


def get_elementor_version(domain: str) -> str:
    ok, data = wp_cmd_json(
        domain, ["plugin", "get", "elementor", "--field=version"]
    )
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


def update_post_meta_from_file(
    domain: str, post_id: int, key: str, value: str
) -> bool:
    temp_dir = get_temp_dir(domain, SITE_ROOT_DIR)
    json_path = temp_dir / f"{key}-{post_id}.json"
    php_path = temp_dir / f"setmeta-{key}-{post_id}.php"

    php_code = (
        f'<?php $p={post_id}; $k="{key}"; '
        f'$f="{json_path}"; '
        '$v=file_get_contents($f); update_post_meta($p,$k,$v); echo "OK";'
    )

    try:
        json_file = write_temp_file(
            domain, f"{key}-{post_id}.json", value, SITE_ROOT_DIR
        )
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
        if not require(
            ok, f"Could not set {meta_key} for page {page_id}", "error"
        ):
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

    if not require(
        ok, f"Elementor template import failed for {template_path}", "error"
    ):
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
    if not require(
        ok, f"Could not read _elementor_data for template {template_id}", "error"
    ):
        return False

    return update_post_meta_from_file(
        domain, page_id, "_elementor_data", template_data
    )


def get_template_for_page(
    templates: list[Path], slug: str
) -> Path | None:
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


def seed_elementor_page(
    domain: str,
    slug: str,
    title: str,
    templates: list[Path],
    version: str,
) -> bool:
    template = get_template_for_page(templates, slug)
    has_template = bool(template)
    if not require(has_template, f"No template available for {slug}", "error"):
        return False

    template_id = import_elementor_template(domain, str(template))
    has_id = bool(template_id)
    if not require(
        has_id, f"Elementor template import failed for {slug}", "error"
    ):
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

    log(
        f"PASS: Seeded page {slug}:{page_id} from template {template_id}"
    )
    return True


def flush_elementor(domain: str) -> bool:
    commands = [["elementor", "flush_css"], ["rewrite", "flush", "--hard"]]

    for command in commands:
        ok = wp_cmd(domain, command)
        if not require(ok, f"Command failed: {' '.join(command)}", "error"):
            return False

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
        if not require(
            fallback.exists(), "No Elementor templates found", "error"
        ):
            return False
        templates = [fallback]

    version = get_elementor_version(domain)
    if not require(bool(version), "Could not read Elementor version", "error"):
        return False

    pages = [
        ("home", "Home"),
        ("about", "About"),
        ("services", "Services"),
        ("contact", "Contact"),
    ]
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


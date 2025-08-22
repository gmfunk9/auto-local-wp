from __future__ import annotations

from pathlib import Path

from config import SITE_ROOT_DIR
from modules.utils import (
    log,
    require,
    run_as_http,
    copy_directory_tree,
)
from .cli import wp_cmd, wp_cmd_json, wp_cmd_json_at_path
from .site import get_site_plugins_dir


# Vault paths
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

    copied_plugins = copy_directory_tree(
        VAULT_CONTENT / "plugins", plugins_dir, "plugin"
    )
    copied_mu = copy_directory_tree(
        VAULT_CONTENT / "mu-plugins", mu_dir, "mu-plugin"
    )
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
    ok, plugin_rows = wp_cmd_json_at_path(
        VAULT_SITE, ["plugin", "list", "--fields=name,status"]
    )
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
        result = require(
            executed, f"Failed to {action} plugin: {plugin_name}", "error"
        )
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
    ok, theme_rows = wp_cmd_json_at_path(
        VAULT_SITE, ["theme", "list", "--fields=name,status"]
    )
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
    ok, vault_rows = wp_cmd_json_at_path(
        VAULT_SITE, ["theme", "list", "--fields=name"]
    )
    if not ok:
        return False

    vault_names = set()
    for theme in vault_rows:
        theme_name = str(theme.get("name", "")).strip()
        vault_names.add(theme_name)

    ok, site_rows = wp_cmd_json(
        domain, ["theme", "list", "--fields=name,status"]
    )
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


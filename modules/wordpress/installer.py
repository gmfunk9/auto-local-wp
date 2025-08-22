"""Install/remove core WordPress and orchestrate setup."""

from __future__ import annotations

import logging
from pathlib import Path

from config import (
    SITE_ROOT_DIR,
    NGINX_VHOST_DIR,
    DEFAULT_WP_USER,
    DEFAULT_WP_PASS,
    DEFAULT_WP_EMAIL,
    DB_PASS,
)
from modules.utils import db_ident, log
from .cli import wp_cmd
from .db import ensure_db_and_user, _db_exists, _db_user_exists
from .site import (
    ensure_site_dir,
    setup_starter_pages_and_menu,
    enable_auto_updates,
    site_has_wp_config,
)
from .plugins_themes import (
    install_custom_plugins,
    install_custom_themes,
    sync_plugins_state_from_vault,
    activate_vault_theme,
    prune_themes_not_in_vault,
    remove_default_plugins,
)
from .elementor_templates import provision_elementor
from .elementor_vault import provision_elementor_from_vault_preset
from .cli import wp_cmd


def install_wordpress(domain: str) -> bool:
    if not ensure_site_dir(domain):
        return False
    if not ensure_db_and_user(domain):
        return False
    ident = db_ident(domain)
    dbname = ident
    dbuser = ident
    commands = [
        "core download --force",
        (
            "config create "
            f"--dbname={dbname} --dbuser={dbuser} --dbpass={DB_PASS} "
            "--skip-check"
        ),
        (
            "core install "
            f"--url={domain} --title='{domain}' "
            f"--admin_user={DEFAULT_WP_USER} "
            f"--admin_password={DEFAULT_WP_PASS} "
            f"--admin_email={DEFAULT_WP_EMAIL} --skip-email"
        ),
    ]
    for cmd in commands:
        if not wp_cmd(domain, cmd):
            return False
    return True


def remove_wordpress(domain: str) -> bool:
    ident = db_ident(domain)
    dbname = ident
    dbuser = ident
    from .db import run_mysql

    ok1 = run_mysql(f"DROP DATABASE IF EXISTS `{dbname}`;")
    ok2 = run_mysql(f"DROP USER IF EXISTS '{dbuser}'@'localhost';")
    return ok1 and ok2


def preflight_create(domain: str) -> bool:
    logging.info("PREFLIGHT START")
    site_path = Path(SITE_ROOT_DIR) / domain
    if site_has_wp_config(domain):
        logging.error(
            "Site directory exists with wp-config.php; refusing to overwrite"
        )
        return False
    ident = db_ident(domain)
    dbname = ident
    dbuser = ident
    if _db_exists(dbname):
        logging.error("Database already exists: %s", dbname)
        return False
    if _db_user_exists(dbuser):
        logging.error("Database user already exists: %s@localhost", dbuser)
        return False
    vhost = Path(NGINX_VHOST_DIR) / f"{domain}.conf"
    if vhost.exists():
        logging.error("Nginx vhost already exists: %s", vhost)
        return False
    log("PASS: Preflight checks passed")
    return True


def setup_wordpress(domain: str, preset: str | None = None) -> bool:
    if not install_wordpress(domain):
        return False
    # Remove default bundled plugins before installing vault plugins
    remove_default_plugins(domain)
    if not install_custom_plugins(domain):
        return False
    if not install_custom_themes(domain):
        return False
    if not sync_plugins_state_from_vault(domain):
        return False
    if not activate_vault_theme(domain):
        return False
    # Remove any non-vault themes after activating the vault theme
    prune_themes_not_in_vault(domain)
    # Run custom WP-CLI commands from data/wp_cli_commands.txt
    if not _run_wp_cli_commands_file(domain):
        return False
    if preset:
        if not provision_elementor_from_vault_preset(domain, preset):
            return False
    else:
        if not provision_elementor(domain):
            return False
    if not setup_starter_pages_and_menu(domain):
        return False
    if not enable_auto_updates(domain):
        return False
    log(f"PASS: WordPress setup complete for {domain}")
    return True


# ─── Custom Commands File ───────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


def _read_wp_cli_commands() -> list[str]:
    path = DATA_DIR / "wp_cli_commands.txt"
    if not path.exists():
        return []
    commands: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = (raw or "").strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            commands.append(line)
    except Exception as err:
        logging.error("Could not read %s: %s", path, err)
        return []
    return commands


def _run_wp_cli_commands_file(domain: str) -> bool:
    commands = _read_wp_cli_commands()
    if not commands:
        return True
    for cmd in commands:
        if not wp_cmd(domain, cmd):
            logging.error("Custom WP-CLI command failed: %s", cmd)
            return False
    return True

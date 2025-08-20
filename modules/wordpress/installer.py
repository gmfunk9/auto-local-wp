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
    build_preset_config,
    apply_preset_config,
    setup_starter_pages_and_menu,
    enable_auto_updates,
    site_has_wp_config,
)
from .plugins import install_plugins, install_custom_plugins, provision_elementor
from .themes import install_themes


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
    failed = False
    site_path = Path(SITE_ROOT_DIR) / domain
    if site_has_wp_config(domain):
        logging.error(
            "Site directory exists with wp-config.php; refusing to overwrite"
        )
        failed = True
    ident = db_ident(domain)
    dbname = ident
    dbuser = ident
    if _db_exists(dbname):
        logging.error("Database already exists: %s", dbname)
        failed = True
    if _db_user_exists(dbuser):
        logging.error("Database user already exists: %s@localhost", dbuser)
        failed = True
    vhost = Path(NGINX_VHOST_DIR) / f"{domain}.conf"
    if vhost.exists():
        logging.error("Nginx vhost already exists: %s", vhost)
        failed = True
    if failed:
        return False
    log("PASS: Preflight checks passed")
    return True


def setup_wordpress(domain: str) -> bool:
    if not install_wordpress(domain):
        return False
    preset = build_preset_config()
    if not install_plugins(domain, preset["plugins"]):
        return False
    if not install_custom_plugins(domain):
        return False
    if not install_themes(domain, preset["themes"]):
        return False
    if not apply_preset_config(domain, preset):
        return False
    if not provision_elementor(domain):
        return False
    if not setup_starter_pages_and_menu(domain):
        return False
    if not enable_auto_updates(domain):
        return False
    log(f"PASS: WordPress setup complete for {domain}")
    return True


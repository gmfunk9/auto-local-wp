"""Shared configuration constants for auto-local.

Centralizes paths and credentials used by modules.
"""

SITE_ROOT_DIR = "/srv/http"
NGINX_VHOST_DIR = "/etc/nginx/vhosts"
HOSTS_FILE = "/etc/hosts"
LOCALHOST_IP = "127.0.0.1"
WP_CLI_PATH = "/usr/bin/wp"
PHP_FPM_SOCKET = "unix:/run/php-fpm/php-fpm.sock"
USER = "http"
GROUP = "http"
USER_GROUP = f"{USER}:{GROUP}"
DIR_PERMS = 0o755
FILE_PERMS = 0o644
DEFAULT_WP_USER = "admin"
DEFAULT_WP_PASS = "password"
DEFAULT_WP_EMAIL = "admin@localhost.local"
DB_USER = "funkad"
DB_PASS = ""

# Elementor: seeding handled via vault presets only

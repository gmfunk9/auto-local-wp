# autolocal.py
#!/usr/bin/env python3
import sys
import subprocess
import os
from pathlib import Path

# ─── CONFIG ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.absolute()
SITE_ROOT_DIR = "/srv/http"
NGINX_VHOST_DIR = "/etc/nginx/vhosts"
HOSTS_FILE = "/etc/hosts"
LOCALHOST_IP = "127.0.0.1"
WP_CLI_PATH = "/usr/bin/wp"
PHP_FPM_SOCKET = "unix:/run/php-fpm/php-fpm.sock"
USER = "efunk"
GROUP = "http"
USER_GROUP = f"{USER}:{GROUP}"
DIR_PERMS = 0o755
FILE_PERMS = 0o644
DEFAULT_WP_USER = "admin"
DEFAULT_WP_PASS = "password"
DEFAULT_WP_EMAIL = "admin@localhost.local"
DB_USER = "funkad"
DB_PASS = ""
PRESETS = {
    "wp-min": {
        "plugins": [],
        "themes": ["hello-elementor"],
        "active_theme": "hello-elementor",
        "active_plugins": []
    },
    "wp-mid": {
        "plugins": ["elementor", "litespeed-cache"],
        "themes": ["hello-elementor"],
        "active_theme": "hello-elementor",
        "active_plugins": ["elementor"]
    },
    "wp-max": {
        "plugins": ["elementor", "litespeed-cache", "wp-mail-smtp"],
        "themes": ["astra", "hello-elementor"],
        "active_theme": "astra",
        "active_plugins": ["elementor", "wp-mail-smtp"]
    }
}
# ─── CLI ──────────────────────────────────────────────────────────────
def run_script(script_name, args):
    cmd = [sys.executable, str(SCRIPT_DIR / script_name)] + args
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end='')
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\nFAIL: {script_name} failed (exit code {e.returncode})", file=sys.stderr)
        print(f"COMMAND: {' '.join(cmd)}", file=sys.stderr)
        if e.stdout:
            print("--- stdout ---", file=sys.stderr)
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print("--- stderr ---", file=sys.stderr)
            print(e.stderr, file=sys.stderr)
        print(f"END OF {script_name} FAILURE REPORT\n", file=sys.stderr)
        return False

def create_site(domain, preset):
    if preset not in PRESETS:
        print(f"FAIL: Invalid preset '{preset}'", file=sys.stderr)
        return False
    scripts = [
        ("nginx_setup.py", [domain]),
        ("wp_setup.py", [domain, "--preset", preset]),
        ("dns_local.py", [domain])
    ]
    for script_name, script_args in scripts:
        if not run_script(script_name, script_args):
            return False
    print(f"PASS: Site {domain} created successfully")
    return True

def remove_site(domain):
    scripts = [
        ("nginx_setup.py", [domain, "--remove"]),
        ("dns_local.py", [domain, "--remove"])
    ]
    for script_name, script_args in scripts:
        if not run_script(script_name, script_args):
            return False
    site_dir = Path(SITE_ROOT_DIR) / domain
    if site_dir.exists():
        try:
            subprocess.run(["sudo", "rm", "-rf", str(site_dir)], check=True)
            print(f"PASS: Removed site directory {site_dir}")
        except subprocess.CalledProcessError:
            print(f"FAIL: Could not remove site directory {site_dir}", file=sys.stderr)
            return False
    print(f"PASS: Site {domain} removed successfully")
    return True

def main():
    if len(sys.argv) < 3:
        print("Usage: autolocal.py --create DOMAIN [--preset wp-min|wp-mid|wp-max] | --remove DOMAIN", file=sys.stderr)
        sys.exit(1)
    if sys.argv[1] == "--create":
        domain = sys.argv[2]
        preset = "wp-mid"
        if "--preset" in sys.argv:
            idx = sys.argv.index("--preset")
            preset = sys.argv[idx + 1]
        ok = create_site(domain, preset)
        sys.exit(0 if ok else 1)
    elif sys.argv[1] == "--remove":
        domain = sys.argv[2]
        ok = remove_site(domain)
        sys.exit(0 if ok else 1)
    else:
        print("Must specify --create or --remove", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

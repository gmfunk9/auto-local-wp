#!/usr/bin/env python3
"""CLI to provision or remove local WordPress sites.

Inputs: domain via CLI flags.
Side effects: creates Nginx vhost, site directory, runs wp-cli, updates
/etc/hosts, and reloads Nginx. Removal deletes vhost and site directory
and cleans hosts entry.
"""
import os
import sys
import subprocess
from pathlib import Path
from config import SITE_ROOT_DIR
from modules.utils import run_cmd, log, init_logging, status_pass, status_fail

# ─── CONFIG ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.absolute()
MOD_NGINX = "modules.nginx"
MOD_DNS = "modules.dns"
MOD_WP = "modules.wordpress"
FLAG_CREATE = "--create"
FLAG_REMOVE = "--remove"
FLAG_PREFLIGHT = "--preflight"
FLAG_PRESET = "--preset"
# ─── CLI ──────────────────────────────────────────────────────────────
def run_script(script_name: str, args: list[str]) -> bool:
    cmd = [sys.executable, "-m", script_name] + args
    try:
        run_cmd(cmd)
        return True
    except subprocess.CalledProcessError as err:
        status_fail(f"{script_name} exit={err.returncode}; see log")
        return False


# ─── Orchestration Steps ───────────────────────────────────────────────
def step_wp_preflight(domain: str) -> bool:
    return run_script(MOD_WP, [FLAG_PREFLIGHT, domain])


def step_nginx_write(domain: str) -> bool:
    return run_script(MOD_NGINX, ["write", domain])


def step_nginx_test() -> bool:
    return run_script(MOD_NGINX, ["test"])


def step_nginx_reload() -> bool:
    return run_script(MOD_NGINX, ["reload"])


def step_dns_add(domain: str) -> bool:
    return run_script(MOD_DNS, [domain])


def step_dns_remove(domain: str) -> bool:
    return run_script(MOD_DNS, [domain, FLAG_REMOVE])


def step_wp_create(domain: str, preset: str | None = None) -> bool:
    # Keep combined create for now; internals are already decomposed.
    args = [FLAG_CREATE, domain]
    if preset:
        args.append(f"{FLAG_PRESET}={preset}")
    return run_script(MOD_WP, args)


def step_wp_remove(domain: str) -> bool:
    return run_script(MOD_WP, [FLAG_REMOVE, domain])


def _is_safe_site_dir(path: Path, domain: str) -> bool:
    try:
        resolved = path.resolve()
        root = Path(SITE_ROOT_DIR).resolve()
        return resolved.is_relative_to(root) and resolved.name == domain
    except Exception:
        return False


def remove_site_dir(domain: str) -> bool:
    site_dir = Path(SITE_ROOT_DIR) / domain
    if not site_dir.exists():
        return True
    if not _is_safe_site_dir(site_dir, domain):
        status_fail(f"unsafe remove path {site_dir}")
        return False
    try:
        run_cmd(["sudo", "rm", "-rf", str(site_dir)])
        log(f"PASS: Removed site directory {site_dir}")
        return True
    except subprocess.CalledProcessError:
        status_fail(f"could not remove site dir {site_dir}")
        return False

def provision_site(domain: str, preset: str | None = None) -> bool:
    if not step_wp_preflight(domain):
        return False
    status_pass("wp preflight")
    if not step_nginx_write(domain):
        return False
    status_pass("nginx write")
    if not step_nginx_test():
        return False
    status_pass("nginx test")
    if not step_nginx_reload():
        return False
    status_pass("nginx reload")
    if not step_dns_add(domain):
        return False
    status_pass("dns add")
    if not step_wp_create(domain, preset=preset):
        return False
    status_pass(f"site {domain} created successfully")
    return True

def remove_site(domain: str) -> bool:
    if not run_script(MOD_NGINX, ["remove", domain]):
        return False
    status_pass("nginx remove")
    if not step_nginx_test():
        return False
    status_pass("nginx test")
    if not step_nginx_reload():
        return False
    status_pass("nginx reload")
    if not step_dns_remove(domain):
        return False
    status_pass("dns remove")
    if not remove_site_dir(domain):
        return False
    status_pass("site dir remove")
    if not step_wp_remove(domain):
        return False
    status_pass(f"site {domain} removed successfully")
    return True

def main(argv: list[str]) -> int:
    # Initialize logging and run-id
    rid = init_logging(None)
    if len(argv) < 2:
        status_fail("usage: --create DOMAIN | --remove DOMAIN")
        return 1
    action, domain = argv[0], argv[1]
    # Optional --preset=KEY-V passthrough
    preset = None
    for a in argv[2:]:
        if a.startswith(f"{FLAG_PRESET}="):
            preset = a.split("=", 1)[1]
            break
    if action == FLAG_CREATE:
        # Ensure subprocs inherit run-id
        os.environ["AUTOLOCAL_RID"] = rid
        ok = provision_site(domain, preset=preset)
        if not ok:
            return 1
        # When provisioning succeeds, run seeding with preset via WP module
        # by invoking create with preset inside step_wp_create.
        # The WP module handles the flag.
        # Already executed step_wp_create inside provision_site; nothing else here.
        return 0
    if action == FLAG_REMOVE:
        os.environ["AUTOLOCAL_RID"] = rid
        return 0 if remove_site(domain) else 1
    status_fail("must specify --create or --remove")
    return 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

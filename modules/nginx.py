#!/usr/bin/env python3
"""Create/remove nginx vhost configs.

SRP: This module only manages nginx config files and nginx service ops.
Host file management lives in modules.dns.
"""
import sys
from pathlib import Path
from config import NGINX_VHOST_DIR, SITE_ROOT_DIR, PHP_FPM_SOCKET
from modules.utils import run_cmd, log

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEMPLATE_FILE = DATA_DIR / "nginx_server_block.txt"
CONF_DIR = Path(NGINX_VHOST_DIR)


def render_config(server_name: str, root_dir: Path) -> str:
    template = TEMPLATE_FILE.read_text()
    return template.format(
        server_name=server_name, root_dir=str(root_dir), php_fpm_sock=PHP_FPM_SOCKET
    )


def write_vhost(server_name: str, root_dir: Path) -> Path:
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    conf_path = CONF_DIR / f"{server_name}.conf"
    conf_path.write_text(render_config(server_name, root_dir))
    log(f"PASS: Created nginx config for {server_name}")
    return conf_path


def remove_vhost(server_name: str) -> None:
    conf_path = CONF_DIR / f"{server_name}.conf"
    if not conf_path.exists():
        log(f"INFO: conf not found (skip): {conf_path}")
        return
    conf_path.unlink()
    log(f"PASS: Removed nginx config for {server_name}")


def test_config() -> None:
    run_cmd(["sudo", "nginx", "-t"])


def reload_nginx() -> None:
    run_cmd(["sudo", "systemctl", "reload", "nginx"])


def create_nginx_config(server_name: str, root_dir: Path | None = None) -> None:
    if not server_name or "." not in server_name:
        raise ValueError("server_name must be FQDN like 'example.local'")
    site_dir = root_dir or (Path(SITE_ROOT_DIR) / server_name)
    write_vhost(server_name, site_dir)
    test_config()
    reload_nginx()


def remove_nginx_config(server_name: str) -> None:
    remove_vhost(server_name)
    test_config()
    reload_nginx()


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        print(
            "usage: nginx.py write <server> [--root PATH] | remove <server> | test | reload",
            file=sys.stderr,
        )
        raise SystemExit(2)
    cmd = argv[0]
    if cmd == "write":
        if len(argv) < 2:
            print("FAIL: Missing server name", file=sys.stderr)
            raise SystemExit(2)
        server = argv[1]
        root = None
        if len(argv) >= 4 and argv[2] == "--root":
            root = Path(argv[3])
        create_nginx_config(server, root)
        raise SystemExit(0)
    if cmd == "remove":
        if len(argv) < 2:
            print("FAIL: Missing server name", file=sys.stderr)
            raise SystemExit(2)
        remove_nginx_config(argv[1])
        raise SystemExit(0)
    if cmd == "test":
        test_config()
        raise SystemExit(0)
    if cmd == "reload":
        reload_nginx()
        raise SystemExit(0)
    print(
        "usage: nginx.py write <server> [--root PATH] | remove <server> | test | reload",
        file=sys.stderr,
    )
    raise SystemExit(2)

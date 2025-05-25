# nginx_setup.py
#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path
import os

from autolocal import NGINX_VHOST_DIR, SITE_ROOT_DIR, PHP_FPM_SOCKET, USER_GROUP, DIR_PERMS, FILE_PERMS

def create_vhost_config(domain):
    config = f"""server {{
  listen 80;
  server_name {domain};
  root {SITE_ROOT_DIR}/{domain};
  index index.php index.html index.htm;
  access_log syslog:server=unix:/dev/log;
  error_log syslog:server=unix:/dev/log;
  location / {{
      try_files $uri $uri/ /index.php?$args;
  }}
  location ~ \\.php$ {{
      include fastcgi_params;
      fastcgi_pass {PHP_FPM_SOCKET};
      fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
  }}
  location ~ /\\.ht {{
      deny all;
  }}
}}"""
    return config

def setup_site_directory(domain):
    site_dir = Path(SITE_ROOT_DIR) / domain
    try:
        site_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["sudo", "chown", USER_GROUP, str(site_dir)], check=True)
        subprocess.run(["sudo", "chmod", oct(DIR_PERMS)[2:], str(site_dir)], check=True)
        return True
    except Exception as e:
        print(f"FAIL: Could not setup site directory: {e}", file=sys.stderr)
        return False

def create_nginx_config(domain):
    vhost_file = Path(NGINX_VHOST_DIR) / f"{domain}.conf"
    config_content = create_vhost_config(domain)
    try:
        Path(NGINX_VHOST_DIR).mkdir(parents=True, exist_ok=True)
        with open(vhost_file, 'w') as f:
            f.write(config_content)
        subprocess.run(["sudo", "chown", "root:root", str(vhost_file)], check=True)
        subprocess.run(["sudo", "chmod", oct(FILE_PERMS)[2:], str(vhost_file)], check=True)
        if not setup_site_directory(domain):
            return False
        subprocess.run(["sudo", "nginx", "-t"], check=True, capture_output=True)
        subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)
        print(f"PASS: Created nginx config for {domain}")
        return True
    except Exception as e:
        print(f"FAIL: Could not create nginx config: {e}", file=sys.stderr)
        return False

def remove_nginx_config(domain):
    vhost_file = Path(NGINX_VHOST_DIR) / f"{domain}.conf"
    try:
        if vhost_file.exists():
            vhost_file.unlink()
            subprocess.run(["sudo", "nginx", "-t"], check=True, capture_output=True)
            subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)
            print(f"PASS: Removed nginx config for {domain}")
        else:
            print(f"PASS: Config {vhost_file} does not exist")
        return True
    except Exception as e:
        print(f"FAIL: Could not remove nginx config: {e}", file=sys.stderr)
        return False

def main():
    domain = sys.argv[1]
    remove = "--remove" in sys.argv
    if remove:
        ok = remove_nginx_config(domain)
    else:
        ok = create_nginx_config(domain)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

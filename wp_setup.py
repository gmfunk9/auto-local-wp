# wp_setup.py
#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path
import os
from autolocal import SITE_ROOT_DIR, WP_CLI_PATH, USER, GROUP, DEFAULT_WP_USER, DEFAULT_WP_PASS, DEFAULT_WP_EMAIL, DB_USER, DB_PASS, PRESETS

def wp_cmd(domain, command):
    site_path = Path(SITE_ROOT_DIR) / domain
    cmd = command.split()
    try:
        result = subprocess.run([WP_CLI_PATH, "--allow-root"] + cmd, cwd=site_path, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end='')
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"FAIL: {command}", file=sys.stderr)
        if e.stdout:
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        return False

def install_wordpress(domain):
    site_path = Path(SITE_ROOT_DIR) / domain
    try:
        site_path.mkdir(parents=True, exist_ok=True)
        os.chdir(site_path)
    except Exception as e:
        print(f"FAIL: Could not create or access {site_path}\n{e}", file=sys.stderr)
        return False
    dbname = domain.replace(".", "_")
    commands = [
        "core download",
        f"config create --dbname={dbname} --dbuser={DB_USER} --dbpass={DB_PASS} --skip-check",
        "db create",
        f"core install --url={domain} --title='{domain}' --admin_user={DEFAULT_WP_USER} --admin_password={DEFAULT_WP_PASS} --admin_email={DEFAULT_WP_EMAIL} --skip-email"
    ]
    for cmd in commands:
        try:
            result = subprocess.run([WP_CLI_PATH, "--allow-root"] + cmd.split(), cwd=site_path, check=True, capture_output=True, text=True)
            if result.stdout:
                print(result.stdout, end='')
            if result.stderr:
                print(result.stderr, file=sys.stderr)
        except subprocess.CalledProcessError as e:
            print(f"FAIL: {cmd}", file=sys.stderr)
            if e.stdout:
                print(e.stdout, file=sys.stderr)
            if e.stderr:
                print(e.stderr, file=sys.stderr)
            return False
    set_permissions(site_path)
    return True

def set_permissions(path):
    subprocess.run(["sudo", "chown", "-R", f"{USER}:{GROUP}", str(path)], check=True)
    for root, dirs, files in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
        for f in files:
            os.chmod(os.path.join(root, f), 0o644)

def install_plugins(domain, plugins):
    for plugin in plugins:
        if not wp_cmd(domain, f"plugin install {plugin}"):
            print(f"FAIL: Could not install plugin: {plugin}", file=sys.stderr)
            return False
    return True

def install_themes(domain, themes):
    for theme in themes:
        if not wp_cmd(domain, f"theme install {theme}"):
            print(f"FAIL: Could not install theme: {theme}", file=sys.stderr)
            return False
    return True

def configure_wordpress(domain, preset_config):
    commands = [
        "option update blog_public 0",
        "option update permalink_structure '/%postname%/'",
        "rewrite flush --hard",
        "post delete 1 --force",
        "post delete 2 --force",
        "theme delete twentytwentyone twentytwentytwo twentytwentythree twentytwentyfour"
    ]
    commands.append(f"theme activate {preset_config['active_theme']}")
    for plugin in preset_config['active_plugins']:
        commands.append(f"plugin activate {plugin}")
    for cmd in commands:
        if not wp_cmd(domain, cmd):
            print(f"FAIL: WordPress configuration failed: {cmd}", file=sys.stderr)
            return False
    return True

def setup_wordpress(domain, preset):
    if preset == "no-wp":
        print(f"SKIP: WordPress setup skipped for preset '{preset}'")
        return True
    preset_config = PRESETS[preset]
    if not install_wordpress(domain):
        return False
    if not install_plugins(domain, preset_config["plugins"]):
        return False
    if not install_themes(domain, preset_config["themes"]):
        return False
    if not configure_wordpress(domain, preset_config):
        return False
    print(f"PASS: WordPress setup complete for {domain}")
    return True

def main():
    domain = sys.argv[1]
    preset = "wp"
    if "--preset" in sys.argv:
        idx = sys.argv.index("--preset")
        preset = sys.argv[idx + 1]
    ok = setup_wordpress(domain, preset)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()

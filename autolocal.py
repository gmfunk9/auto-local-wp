import os
import re
import subprocess
from pathlib import Path


def find_highest_version(plugin):
    try:
        plugin_dir = Path("/home/dfunk/Projects/AUTOLOCALWP/") / plugin
        highest_version = "0"
        highest_version_file = ""
        for file in plugin_dir.glob("*.zip"):
            if subprocess.run(["unzip", "-l", str(file), "*.php"], capture_output=True, text=True).stdout:
                version_info = subprocess.run(["unzip", "-p", str(file), "*.php"], capture_output=True, text=True).stdout
                version_info = re.search(r"Version:\s*([\d.]+)", version_info)
                if version_info:
                    version = version_info.group(1)
                    if version > highest_version:
                        highest_version = version
                        highest_version_file = file
        if highest_version_file:
            return highest_version_file
        else:
            raise FileNotFoundError(f"No valid plugin zip files found in {plugin_dir}")
    except Exception as e:
        print(f"Error in find_highest_version: {e}")


def setup_nginx(domain):
    with open("nginx_config_template.txt", "r") as template_file:
        nginx_config = template_file.read().format(domain=domain)
    with open(f"/etc/nginx/sites-available/{domain}", "w") as f:
        f.write(nginx_config)
    run_command(
        "Creating symlink for Nginx configuration",
        ["ln", "-s", f"/etc/nginx/sites-available/{domain}", f"/etc/nginx/sites-enabled/{domain}"]
    )
    run_command(
        "Restarting Nginx",
        ["systemctl", "restart", "nginx"],
    )
    with open("/etc/hosts", "a") as f:
        f.write(f"127.0.0.1 {domain}.local\n")


def run_command( desc, command ):
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        error = re.sub(r'\\n', ' ', result.stdout)
        print(f"\033[92mSUCCE\033[0m '{desc}'")
    except subprocess.CalledProcessError as e:
        error = re.sub(r'\\n', ' ', e.stderr)
        print(f"\033[91mERROR\033[0m '{desc}'")


def setup_wordpress(domain):
    sudo_cmd = ["sudo", "-u", "dfunk", "-i", "--"]
    wp_cmd = ["wp", f"--path=/var/www/{domain}"]
    swp_cmd = sudo_cmd + wp_cmd
    plugins = {
        'uninstall': ["akismet", "hello"],
        'install': ["elementor", "litespeed-cache"],
        'activate': ["elementor"],
        'install_paid': ["updraftplus", "elementor-pro"]
    }
    themes = {
        'install': ["hello-elementor"]
    }
    setup_commands = [
        ("Creating directory for WordPress installation", ["mkdir",  "-p", f"/var/www/{domain}"]),
        ("Downloading WordPress core",                    ["core",   "download"]),
        ("Creating WordPress configuration",              ["config", "create", "--dbname=" + domain, "--dbuser=funkad", "--dbpass="]),
        ("Creating WordPress database",                   ["db",     "create"]),
        ("Installing WordPress core",                     ["core",   "install", "--url=" + domain + ".local", "--title=" + domain, "--admin_user=FunkAd", "--admin_password=pass", "--admin_email=wordpress@" + domain + ".local"]),
        ("Disabling search engine visibility",            ["option", "update", "blog_public", "0"]),
        ("Creating home page",                            ["post",   "create", "--post_type=page", "--post_title=Home", "--post_status=publish"]),
        ("Setting front page to static page",             ["option", "update", "show_on_front", "page"])
    ]
    for description, command in setup_commands:
        run_command(description, swp_cmd + command)
    os.chdir(f"/var/www/{domain}")
    for action, plugin_list in plugins.items():
        for plugin in plugin_list:
            if action == 'install_paid':
                highest_version_file = find_highest_version(plugin)
                if highest_version_file:
                    run_command(f"Installing plugin {plugin}", swp_cmd + ["plugin", "install", f"file://{highest_version_file}", "--activate"])
            else:
                run_command(f"{action.capitalize()}ing plugin {plugin}", swp_cmd + ["plugin", action, plugin])
    for action, theme_list in themes.items():
        for theme in theme_list:
            run_command(f"{action.capitalize()}ing theme {theme}", swp_cmd + ["theme", action, theme])
            if action == 'install':
                run_command(f"Activating theme {theme}", swp_cmd + ["theme", "activate", theme])


if __name__ == "__main__":
    import sys
    domain = sys.argv[1]
    setup_nginx(domain)
    setup_wordpress(domain)

# /home/ffunk/PROJECTS/auto-local-wp/dothing.py
from pathlib import Path
from modules.wordpress.cli import wp_cmd_json_at_path, wp_cmd

# adjust this to your real test site path
VAULT = Path("/srv/http/funkpd_plugin_vault.local")
SITE  = "/srv/http/test-site-import-ele-images-t1.local"

SOURCE_PAGE = "27"  # vault homepage
TARGET_PAGE = "24"  # test homepage

def main():
    # 1. fetch _elementor_data from vault
    ok, rows = wp_cmd_json_at_path(
        VAULT,
        ["post","meta","list", SOURCE_PAGE,
         "--keys=_elementor_data","--fields=meta_value"]
    )
    if not ok:
        raise SystemExit("failed to fetch _elementor_data from vault page 27")
    if not rows:
        raise SystemExit("failed to fetch _elementor_data from vault page 27")
    blob = rows[0]["meta_value"]

    # 2. update target homepage
    wp_cmd(SITE, ["post","meta","update", TARGET_PAGE, "_elementor_data", blob])
    print(f"homepage {TARGET_PAGE} updated with vault {SOURCE_PAGE}")

    # 3. flush css
    wp_cmd(SITE, ["elementor","flush_css"])
    print("elementor css flushed")

    # 4. verify size
    ok, rows = wp_cmd_json_at_path(
        SITE,
        ["post","meta","list", TARGET_PAGE,
         "--keys=_elementor_data","--fields=meta_value"]
    )
    if not ok:
        print("verification failed")
        return
    if not rows:
        print("verification failed")
        return
    size = len(rows[0]["meta_value"])
    print(f"verification: homepage {TARGET_PAGE} _elementor_data length = {size} bytes")

if __name__ == "__main__":
    main()

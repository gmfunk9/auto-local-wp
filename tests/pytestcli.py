from modules.wordpress import cli

site = "/srv/http/funkpd_plugin_vault.local"

# 1. Basic plugin list (read-ish, should yield list of dicts)
ok, data = cli.wp_cmd_json(site, "plugin list")
print("plugin list ok:", ok)
print("plugin list type:", type(data), "count:", len(data))

# 2. Scalar option get (read-ish, should yield string not [])
ok, data = cli.wp_cmd_json(site, "option get home")
print("home url ok:", ok, "value:", data)

# 3. Post IDs (porcelain field, should yield list of ints)
ok, data = cli.wp_cmd_json(site, "post list --post_type=page --field=ID")
print("page IDs:", data)

# 4. Write command (non-read, should yield [])
ok, data = cli.wp_cmd_json(site, "theme is-installed hello-elementor")
print("theme is-installed ok:", ok, "data:", data)

# 5. Capture variant (returns JSON string)
ok, out, err = cli.wp_cmd_capture(site, "option get blogdescription")
print("capture blogdescription:", out)

# 6. Legacy boolean wrapper (pass/fail only)
ok = cli.wp_cmd(site, "theme activate hello-elementor")
print("theme activate ok:", ok)

from pathlib import Path
from modules.wordpress import cli

# using domain (string)
ok, data1 = cli.wp_cmd_json("/srv/http/funkpd_plugin_vault.local",
    "post meta list 27 --keys=_elementor_data --fields=meta_value --format=json --skip-plugins --skip-themes --no-color --quiet")

# using explicit path
ok, data2 = cli.wp_cmd_json_at_path(Path("/srv/http/funkpd_plugin_vault.local"),
    "post meta list 27 --keys=_elementor_data --fields=meta_value --format=json --skip-plugins --skip-themes --no-color --quiet")

print("same?", data1 == data2)

site = Path("/srv/http/funkpd_plugin_vault.local")
cmd = "post meta list 27 --keys=_elementor_data --fields=meta_value --format=json --skip-plugins --skip-themes --no-color --quiet"

ok, data = cli.wp_cmd_json_at_path(site, cmd)

print("ok:", ok)
if data and isinstance(data, list) and "meta_value" in data[0]:
    val = data[0]["meta_value"]
    print("len:", len(val))
    print("head:", val[:50])
    print("tail:", val[-50:])
else:
    print("unexpected data:", type(data), data)

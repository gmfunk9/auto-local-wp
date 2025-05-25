# auto-local

Provision local WordPress sites with Nginx, MariaDB, and `/etc/hosts`.

## Usage

./autolocal.py DOMAIN [--preset wp-min|wp-mid|wp-max]

## Structure

autolocal.py       # entrypoint, config, CLI
nginx_setup.py     # vhost + site dir
wp_setup.py        # wp-cli + theme/plugin config
dns_local.py       # /etc/hosts patch

## Presets

* `wp-min`: bare
* `wp-mid`: Elementor + cache
* `wp-max`: full suite (Elementor, SMTP, cache)


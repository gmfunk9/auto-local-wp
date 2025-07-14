# auto-local

Provision local WordPress or static sites with Nginx, MariaDB, and `/etc/hosts`.

## Usage

~~~bash
./autolocal.py --create DOMAIN [--preset wp|no-wp]
~~~

Default: `wp` (WordPress).  
Use `no-wp` for plain Nginx + DNS, no WordPress.

~~~bash
./autolocal.py --remove DOMAIN
~~~

## Structure

autolocal.py       # entrypoint, config, CLI  
nginx_setup.py     # vhost + site dir  
wp_setup.py        # wp-cli + theme/plugin config  
dns_local.py       # /etc/hosts patch  

## Presets

* `wp`: WordPress with plugins/themes (default)
* `no-wp`: no WordPress, just nginx + DNS

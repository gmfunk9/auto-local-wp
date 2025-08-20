"""WordPress orchestration package (refactored from monolith).

Submodules:
- db: MariaDB helpers
- cli: WP-CLI wrappers
- site: filesystem and site configuration
- plugins: plugin management and Elementor seeding
- themes: theme management
- installer: install/remove and high-level orchestration
"""

# Intentionally minimal; logic lives in submodules and __main__.


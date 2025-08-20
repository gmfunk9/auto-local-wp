<?php
/**
 * Plugin Name: Plugin Example
 * Description: Shows a simple "Hello World" notice in WP Admin.
 * Version: 0.1.0
 * Author: Codex CLI
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit; // Exit if accessed directly
}

add_action( 'admin_notices', function () {
    echo '<div class="notice notice-success is-dismissible"><p><strong>Hello, World!</strong> from Plugin Example.</p></div>';
} );


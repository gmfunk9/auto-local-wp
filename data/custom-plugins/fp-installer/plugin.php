<?php
/**
 * Plugin Name: Elementor Importer Helper
 * Description: Quick utility to import an Elementor JSON and apply it to a page.
 */

add_action('init', function () {
    if (!is_admin()) return;

    // Run only when explicitly called, e.g. ?elementor_import=1
    if (!isset($_GET['elementor_import'])) return;

    $json_file = '/home/ffunk/codex/web_projects/auto-local-wp/data/elementor-page-templates/fp_fullpage-about-landscaping.json';
    $page_title = 'About Landscaping';

    $plugin = \Elementor\Plugin::instance();

    // Import template to library
    $result = $plugin->templates_manager->import_template([
        'fileData' => base64_encode(file_get_contents($json_file)),
        'fileName' => basename($json_file),
    ]);

    if (empty($result[0]['template_id'])) {
        wp_die('Template import failed.');
    }
    $tpl_id = $result[0]['template_id'];

    // Create page
    $page_id = wp_insert_post([
        'post_type'   => 'page',
        'post_title'  => $page_title,
        'post_status' => 'publish',
    ]);

    // Inject template content
    $tpl = $plugin->templates_manager->get_source('local')->get_data($tpl_id);
    if (!empty($tpl['content'])) {
        update_post_meta($page_id, '_elementor_edit_mode', 'builder');
        update_post_meta($page_id, '_elementor_version', ELEMENTOR_VERSION);
        update_post_meta($page_id, '_elementor_data', wp_slash(wp_json_encode($tpl['content'])));
        echo "SUCCESS: Inserted template $tpl_id into page $page_id";
        exit;
    } else {
        wp_die('FAIL: Template has no content.');
    }
});


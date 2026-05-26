<?php
/**
 * Plugin Name: PetalRank pSEO Helper
 * Description: Automates registration of Custom Post Types, ACF Fields, and Authentication filters for the PetalRank pSEO Pipeline.
 * Version: 1.0.0
 * Author: Antigravity AI
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit; // Exit if accessed directly
}

/**
 * 1. Register Custom Post Types (CPTs)
 */
function petalrank_register_cpts() {
    $cpts = array(
        'compare' => array(
            'singular'  => 'Comparison',
            'plural'    => 'Comparisons',
            'menu_icon' => 'dashicons-leftright',
            'slug'      => 'compare',
        ),
        'industry' => array(
            'singular'  => 'Industry',
            'plural'    => 'Industries',
            'menu_icon' => 'dashicons-networking',
            'slug'      => 'industry',
        ),
        'problem' => array(
            'singular'  => 'Problem',
            'plural'    => 'Problems',
            'menu_icon' => 'dashicons-welcome-comments',
            'slug'      => 'problem',
        ),
        'use_case' => array(
            'singular'  => 'Use Case',
            'plural'    => 'Use Cases',
            'menu_icon' => 'dashicons-layout',
            'slug'      => 'use-case',
        ),
        'guide' => array(
            'singular'  => 'Guide',
            'plural'    => 'Guides',
            'menu_icon' => 'dashicons-welcome-learn-more',
            'slug'      => 'guides',
        ),
    );

    foreach ( $cpts as $post_type => $data ) {
        $labels = array(
            'name'               => $data['plural'],
            'singular_name'      => $data['singular'],
            'menu_name'          => $data['plural'],
            'name_admin_bar'     => $data['singular'],
            'all_items'          => 'All ' . $data['plural'],
            'add_new_item'       => 'Add New ' . $data['singular'],
            'new_item'           => 'New ' . $data['singular'],
            'edit_item'          => 'Edit ' . $data['singular'],
            'view_item'          => 'View ' . $data['singular'],
            'search_items'       => 'Search ' . $data['plural'],
            'not_found'          => 'No ' . strtolower($data['plural']) . ' found.',
        );

        $args = array(
            'labels'             => $labels,
            'public'             => true,
            'publicly_queryable' => true,
            'show_ui'            => true,
            'show_in_menu'       => true,
            'query_var'          => true,
            'rewrite'            => array( 'slug' => $data['slug'], 'with_front' => true ),
            'capability_type'    => 'post',
            'has_archive'        => true,
            'hierarchical'       => false,
            'menu_position'      => 5,
            'menu_icon'          => $data['menu_icon'],
            'show_in_rest'       => true, // Required for REST API access
            'supports'           => array( 'title', 'editor', 'thumbnail', 'revisions', 'custom-fields' ),
            'taxonomies'         => array( 'category' ),
        );

        register_post_type( $post_type, $args );
    }
}
add_action( 'init', 'petalrank_register_cpts' );

/**
 * 2. Register ACF Local Field Groups
 */
function petalrank_register_acf_fields() {
    if ( ! function_exists( 'acf_add_local_field_group' ) ) {
        return;
    }

    // COMPARE CPT fields
    acf_add_local_field_group( array(
        'key' => 'group_compare_fields',
        'title' => 'Comparison Page Fields',
        'fields' => array(
            array( 'key' => 'field_competitor_name', 'label' => 'Competitor Name', 'name' => 'competitor_name', 'type' => 'text', 'required' => 1 ),
            array( 'key' => 'field_competitor_strength', 'label' => 'Competitor Strength', 'name' => 'competitor_strength', 'type' => 'textarea' ),
            array( 'key' => 'field_competitor_weakness', 'label' => 'Competitor Weakness', 'name' => 'competitor_weakness', 'type' => 'textarea' ),
            array( 'key' => 'field_ideal_user', 'label' => 'Ideal User', 'name' => 'ideal_user', 'type' => 'text' ),
            array( 'key' => 'field_comparison_summary', 'label' => 'Comparison Summary', 'name' => 'comparison_summary', 'type' => 'textarea' ),
            array( 'key' => 'field_compare_cta', 'label' => 'CTA', 'name' => 'CTA', 'type' => 'text' ),
        ),
        'location' => array( array( array( 'param' => 'post_type', 'operator' => '==', 'value' => 'compare' ) ) ),
        'position' => 'normal',
    ) );

    // INDUSTRY CPT fields
    acf_add_local_field_group( array(
        'key' => 'group_industry_fields',
        'title' => 'Industry Page Fields',
        'fields' => array(
            array( 'key' => 'field_industry_name', 'label' => 'Industry Name', 'name' => 'industry_name', 'type' => 'text', 'required' => 1 ),
            array( 'key' => 'field_seo_challenge', 'label' => 'SEO Challenge', 'name' => 'SEO_challenge', 'type' => 'textarea' ),
            array( 'key' => 'field_outreach_problem', 'label' => 'Outreach Problem', 'name' => 'outreach_problem', 'type' => 'textarea' ),
            array( 'key' => 'field_relevant_feature', 'label' => 'Relevant Feature', 'name' => 'relevant_feature', 'type' => 'text' ),
            array( 'key' => 'field_success_metric', 'label' => 'Success Metric', 'name' => 'success_metric', 'type' => 'text' ),
        ),
        'location' => array( array( array( 'param' => 'post_type', 'operator' => '==', 'value' => 'industry' ) ) ),
        'position' => 'normal',
    ) );

    // PROBLEM CPT fields
    acf_add_local_field_group( array(
        'key' => 'group_problem_fields',
        'title' => 'Problem Page Fields',
        'fields' => array(
            array( 'key' => 'field_problem_issue', 'label' => 'Issue', 'name' => 'issue', 'type' => 'text', 'required' => 1 ),
            array( 'key' => 'field_why_it_happens', 'label' => 'Why It Happens', 'name' => 'why_it_happens', 'type' => 'textarea' ),
            array( 'key' => 'field_business_impact', 'label' => 'Business Impact', 'name' => 'business_impact', 'type' => 'textarea' ),
            array( 'key' => 'field_problem_fix', 'label' => 'Fix', 'name' => 'fix', 'type' => 'textarea' ),
            array( 'key' => 'field_petalrank_solution', 'label' => 'PetalRank Solution', 'name' => 'PetalRank_solution', 'type' => 'textarea' ),
        ),
        'location' => array( array( array( 'param' => 'post_type', 'operator' => '==', 'value' => 'problem' ) ) ),
        'position' => 'normal',
    ) );

    // USE_CASE CPT fields
    acf_add_local_field_group( array(
        'key' => 'group_use_case_fields',
        'title' => 'Use Case Page Fields',
        'fields' => array(
            array( 'key' => 'field_use_case_name', 'label' => 'Use Case Name', 'name' => 'use_case_name', 'type' => 'text', 'required' => 1 ),
            array( 'key' => 'field_why_it_matters', 'label' => 'Why It Matters', 'name' => 'why_it_matters', 'type' => 'textarea' ),
            array( 'key' => 'field_target_audience', 'label' => 'Target Audience', 'name' => 'target_audience', 'type' => 'text' ),
            array( 'key' => 'field_key_workflow', 'label' => 'Key Workflow', 'name' => 'key_workflow', 'type' => 'textarea' ),
            array( 'key' => 'field_benefits', 'label' => 'Benefits', 'name' => 'benefits', 'type' => 'textarea' ),
        ),
        'location' => array( array( array( 'param' => 'post_type', 'operator' => '==', 'value' => 'use_case' ) ) ),
        'position' => 'normal',
    ) );

    // GUIDE CPT fields
    acf_add_local_field_group( array(
        'key' => 'group_guide_fields',
        'title' => 'Guide Page Fields',
        'fields' => array(
            array( 'key' => 'field_guide_title', 'label' => 'Guide Title', 'name' => 'guide_title', 'type' => 'text', 'required' => 1 ),
            array( 'key' => 'field_difficulty_level', 'label' => 'Difficulty Level', 'name' => 'difficulty_level', 'type' => 'text' ),
            array( 'key' => 'field_time_required', 'label' => 'Time Required', 'name' => 'time_required', 'type' => 'text' ),
            array( 'key' => 'field_key_takeaways', 'label' => 'Key Takeaways', 'name' => 'key_takeaways', 'type' => 'textarea' ),
            array( 'key' => 'field_steps', 'label' => 'Steps', 'name' => 'steps', 'type' => 'textarea' ),
        ),
        'location' => array( array( array( 'param' => 'post_type', 'operator' => '==', 'value' => 'guide' ) ) ),
        'position' => 'normal',
    ) );
}
add_action( 'acf/init', 'petalrank_register_acf_fields' );

/**
 * 3. HTTP Authorization Header Bypass Filter for Nginx/Apache CGI
 */
add_filter( 'determine_current_user', function( $user_id ) {
    if ( $user_id ) {
        return $user_id;
    }
    if ( isset( $_SERVER['HTTP_X_HTTP_AUTHORIZATION'] ) ) {
        $_SERVER['HTTP_AUTHORIZATION'] = $_SERVER['HTTP_X_HTTP_AUTHORIZATION'];
    }
    return $user_id;
}, 10 );

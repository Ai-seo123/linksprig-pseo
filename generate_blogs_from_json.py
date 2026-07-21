import os
import json
import pandas as pd
import time
import db_helper
from internal_linker import InternalLinker
from formatter import format_blog_html
from generate_blogs_from_excel import (
    clean_slug, normalize_category, generate_blog_post, 
    push_post_to_wordpress, EXPORT_MODE, WP_POST_STATUS
)

def main():
    json_path = os.getenv("UPLOADED_FILE_PATH")
    if not json_path or not os.path.exists(json_path):
        print(f"[ERROR] JSON file not found at: {json_path}")
        return

    csv_output_path = os.path.join("output", "excel_blogs_export.csv")

    print(f"[INFO] Reading topics from {json_path}...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to open json file: {e}")
        return

    all_pages = []
    for item in items:
        topic = item.get("topic", "").strip()
        keyword = item.get("keyword", "").strip()
        category = item.get("category", "").strip()
        if not topic or not keyword:
            continue
        slug = "/" + clean_slug(topic) + "/"
        all_pages.append({
            "sheet": "JSON_Import",
            "category": category,
            "keyword": keyword,
            "title": topic,
            "slug": slug
        })

    print(f"[INFO] Parsed {len(all_pages)} total pages from JSON.")
    if not all_pages:
        print("[WARNING] No topics parsed. Exiting.")
        return

    # Map categories to internal linker types
    POST_TYPE_MAP = {
        "Category A — LinkedIn Outreach Strategy": "strategy",
        "Category B — AI Personalization & Technology": "technology",
        "Category C — Role-Specific Outreach Guides": "guide",
        "Category D — Message Templates & Copywriting": "copywriting",
        "Category E — Lead Generation & Pipeline Building": "lead_gen"
    }

    # Register pages in the InternalLinker
    registered_pages = []
    for p in all_pages:
        norm_cat = normalize_category(p["category"])
        p_type = POST_TYPE_MAP.get(norm_cat, "guide")
        registered_pages.append({
            "post_type": p_type,
            "slug": p["slug"],
            "title": p["title"],
            "entity": p["keyword"]
        })

    linker = InternalLinker(registered_pages)
    print(f"[INFO] Initialized InternalLinker with {len(registered_pages)} registered pages.")

    # Load registry from db_helper
    try:
        generated_slugs = db_helper.get_all_registered_slugs()
    except Exception as e:
        print(f"[WARNING] Failed to load registry: {e}")
        generated_slugs = set()

    rows_for_csv = []
    uploaded_count = 0

    WP_URL = os.getenv("WP_URL", "")
    WP_USER = os.getenv("WP_USER", "")
    WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for idx, page in enumerate(all_pages):
        topic = page["title"]
        keyword = page["keyword"]
        slug = page["slug"]
        leaf_slug = slug.strip("/").split("/")[-1]

        # Check if already exists on WordPress API by slug if credentials configured
        already_on_wp = False
        if WP_URL and WP_USER and WP_APP_PASSWORD:
            try:
                check_endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
                check_resp = requests.get(
                    check_endpoint,
                    params={"slug": leaf_slug, "status": "any"},
                    auth=(WP_USER, WP_APP_PASSWORD),
                    headers=headers,
                    timeout=10
                )
                if check_resp.status_code == 200 and isinstance(check_resp.json(), list) and len(check_resp.json()) > 0:
                    print(f"[{idx+1}/{len(all_pages)}] Slug already exists on WordPress: {leaf_slug}")
                    db_helper.register_slug(slug)
                    db_helper.register_slug(leaf_slug)
                    already_on_wp = True
            except Exception as e:
                print(f" - [Warning] Error checking WP slug '{leaf_slug}': {e}")

        if already_on_wp:
            continue

        page_data = generate_blog_post(topic, keyword)
        if not page_data:
            print(f" - [FAILED] Skipping '{topic}' due to AI writing error.")
            continue
        elif "error" in page_data:
            print(f"[FATAL] Halting pipeline due to AI API error on topic '{topic}'.")
            exit(1)

        # Overwrite page parameters with values from JSON
        page_data["category"] = normalize_category(page["category"]) or page_data.get("category", "")
        page_data["slug"] = slug # Keep the prefix slug for internal linking resolution

        # Inject context-aware internal links
        norm_cat = normalize_category(page["category"])
        p_type = POST_TYPE_MAP.get(norm_cat, "guide")
        injected_sections, links_count = linker.inject_links(p_type, page_data["body_sections"])
        page_data["body_sections"] = injected_sections
        print(f" - [Internal Links] Injected {links_count} links.")

        # Flatten content HTML for CSV export with Table of Contents layout
        content_html = format_blog_html(
            title=page_data["title"],
            intro_html=page_data["intro"],
            body_sections=page_data["body_sections"],
            faqs_list=page_data["faqs"]
        )

        csv_row = {
            "post_title": page_data["title"],
            "post_slug": page_data["slug"],
            "post_content": content_html,
            "post_status": "draft",
            "post_type": "post",
            "category": page_data.get("category", ""),
            "focus_keyword": keyword,
            "meta_title": page_data["meta_title"],
            "meta_description": page_data["meta_description"]
        }
        rows_for_csv.append(csv_row)

        # Upload directly to WordPress
        if EXPORT_MODE in ["wp_api", "both"]:
            success = push_post_to_wordpress(page_data, keyword)
            if success:
                uploaded_count += 1
                generated_slugs.add(slug)
                generated_slugs.add(leaf_slug)
        else:
            # If CSV only, immediately register incrementally
            db_helper.register_slug(page_data["slug"])
            generated_slugs.add(slug)
            generated_slugs.add(leaf_slug)

        # Add a delay between API calls to prevent rate limits
        time.sleep(1)

    # Save output to CSV
    if rows_for_csv:
        out_df = pd.DataFrame(rows_for_csv)
        # Ensure output directory exists
        os.makedirs(os.path.dirname(csv_output_path), exist_ok=True)
        # Append if file exists, else create new
        if os.path.exists(csv_output_path):
            out_df.to_csv(csv_output_path, mode='a', header=False, index=False, encoding="utf-8")
        else:
            out_df.to_csv(csv_output_path, index=False, encoding="utf-8")
        print(f"[SUCCESS] CSV Export appended at: {csv_output_path}")

    if EXPORT_MODE in ["wp_api", "both"] and uploaded_count == 0 and len(rows_for_csv) > 0:
        raise RuntimeError(f"Failed to upload any generated posts from JSON to WordPress ({uploaded_count}/{len(rows_for_csv)} uploaded)")

    print("\n[INFO] Successful uploads registered incrementally.")
    print("\n[SUCCESS] Pipeline execution finished.")

if __name__ == "__main__":
    main()

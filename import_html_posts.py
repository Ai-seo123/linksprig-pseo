import os
import re
import copy
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from formatter import format_imported_blog_html
import requests
import json
import base64
import time

# Load environment
load_dotenv()

import db_helper

WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()
EXPORT_MODE = os.getenv("EXPORT_MODE", "csv").lower()

# HTML file path
html_path = os.getenv("UPLOADED_FILE_PATH", r"C:\Users\ARNAV\Downloads\linksprig_50_blogs.html")
output_dir = "output"
os.makedirs(output_dir, exist_ok=True)
csv_output_path = os.path.join(output_dir, "imported_blogs_export.csv")

def clean_slug(text):
    # Convert title to a clean slug
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

CATEGORY_MAP = {
    "linkedin outreach strategy": "Category A — LinkedIn Outreach Strategy",
    "ai personalization & technology": "Category B — AI Personalization & Technology",
    "ai personalization and technology": "Category B — AI Personalization & Technology",
    "role-specific outreach guides": "Category C — Role-Specific Outreach Guides",
    "message templates & copywriting": "Category D — Message Templates & Copywriting",
    "message templates and copywriting": "Category D — Message Templates & Copywriting",
    "lead generation & pipeline building": "Category E — Lead Generation & Pipeline Building",
    "lead generation and pipeline building": "Category E — Lead Generation & Pipeline Building"
}

def normalize_category(name):
    if not name:
        return None
    name_lower = name.lower().strip()
    for key, canonical in CATEGORY_MAP.items():
        if key in name_lower or name_lower in key:
            return canonical
    if "category a" in name_lower or "outreach strategy" in name_lower:
        return "Category A — LinkedIn Outreach Strategy"
    if "category b" in name_lower or "ai personalization" in name_lower or "technology" in name_lower:
        return "Category B — AI Personalization & Technology"
    if "category c" in name_lower or "role-specific" in name_lower or "role specific" in name_lower:
        return "Category C — Role-Specific Outreach Guides"
    if "category d" in name_lower or "message templates" in name_lower or "copywriting" in name_lower:
        return "Category D — Message Templates & Copywriting"
    if "category e" in name_lower or "lead generation" in name_lower or "pipeline" in name_lower:
        return "Category E — Lead Generation & Pipeline Building"
    return name

_wp_category_cache = {}

def get_wp_category_id(category_name, wp_url, auth_user, auth_password):
    canonical_name = normalize_category(category_name)
    if not canonical_name:
        return None
        
    if canonical_name in _wp_category_cache:
        return _wp_category_cache[canonical_name]
        
    try:
        import base64
        import requests
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        auth_str = f"{auth_user}:{auth_password}"
        b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
        
        endpoint = f"{wp_url.rstrip('/')}/wp-json/wp/v2/categories"
        response = requests.get(endpoint, params={"per_page": 100}, headers=headers, auth=(auth_user, auth_password), timeout=10)
        
        if response.status_code == 200:
            cats = response.json()
            for cat in cats:
                _wp_category_cache[cat["name"]] = cat["id"]
                _wp_category_cache[cat["slug"]] = cat["id"]
                
            if canonical_name in _wp_category_cache:
                return _wp_category_cache[canonical_name]
            
            for cat in cats:
                if cat["name"].lower().strip() == canonical_name.lower().strip():
                    _wp_category_cache[canonical_name] = cat["id"]
                    return cat["id"]
                    
        # Try creating category if not found
        payload = {
            "name": canonical_name,
            "slug": clean_slug(canonical_name)
        }
        response = requests.post(endpoint, json=payload, headers=headers, auth=(auth_user, auth_password), timeout=10)
        if response.status_code == 201:
            cat = response.json()
            _wp_category_cache[canonical_name] = cat["id"]
            print(f" - [Category] Created category '{canonical_name}' (ID: {cat['id']})")
            return cat["id"]
        elif response.status_code == 400: # Could be term already exists
            search_resp = requests.get(endpoint, params={"search": canonical_name}, headers=headers, auth=(auth_user, auth_password), timeout=10)
            if search_resp.status_code == 200:
                search_cats = search_resp.json()
                for cat in search_cats:
                    if cat["name"].lower().strip() == canonical_name.lower().strip():
                        _wp_category_cache[canonical_name] = cat["id"]
                        return cat["id"]
        print(f" - [Warning] Failed to get or create category '{canonical_name}': {response.status_code} - {response.text}")
    except Exception as e:
        print(f" - [Warning] Error in get_wp_category_id: {e}")
        
    return None

def push_posts_to_wordpress(rows):
    print(f"[INFO] Pushing {len(rows)} posts directly to WordPress REST API at {WP_URL}")
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    
    # Load registry from db_helper
    try:
        generated_slugs = db_helper.get_all_registered_slugs()
    except Exception as e:
        print(f"[WARNING] Failed to load registry: {e}")
        generated_slugs = set()
        
    successful_count = 0
    
    for idx, row in enumerate(rows):
        post_slug = row.get("post_slug")
        if post_slug in generated_slugs:
            print(f"\n[Skipping {idx+1}/{len(rows)}] Slug already in registry: {post_slug}")
            continue
            
        # Check if post already exists on WordPress API by slug
        if post_slug:
            try:
                check_endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
                check_resp = requests.get(
                    check_endpoint,
                    params={"slug": post_slug, "status": "any"},
                    auth=(WP_USER, WP_APP_PASSWORD),
                    headers=headers,
                    timeout=10
                )
                if check_resp.status_code == 200 and isinstance(check_resp.json(), list) and len(check_resp.json()) > 0:
                    print(f"\n[Skipping {idx+1}/{len(rows)}] Slug already exists on WordPress: {post_slug}")
                    db_helper.register_slug(post_slug)
                    continue
            except Exception as e:
                print(f" - [Warning] Error checking if slug '{post_slug}' exists on WP: {e}")
                # Resilient WP API Check: Safely skip this post instead of uploading duplicate
                print(f" - [Skipping {idx+1}/{len(rows)}] Skipping '{post_slug}' due to WP check error to prevent duplication.")
                continue
        cat_name = row.get("category", "")
        cat_id = get_wp_category_id(cat_name, WP_URL, WP_USER, WP_APP_PASSWORD) if cat_name else None
        
        payload = {
            "title": row["post_title"],
            "slug": row["post_slug"],
            "content": row["post_content"],
            "status": WP_POST_STATUS,
            "type": "post",
            "meta": {
                "_rank_math_title": row["meta_title"],
                "_rank_math_description": row["meta_description"],
                "_rank_math_focus_keyword": row["focus_keyword"]
            }
        }
        if cat_id:
            payload["categories"] = [cat_id]
        
        print(f"\n[Pushing {idx+1}/{len(rows)}] Title: {row['post_title']}")
        
        max_retries = 3
        backoff_factor = 2
        success = False
        
        for attempt in range(max_retries):
            try:
                endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
                response = requests.post(
                    endpoint,
                    json=payload,
                    auth=(WP_USER, WP_APP_PASSWORD),
                    headers=headers,
                    timeout=15
                )
                
                if response.status_code == 201:
                    print(f" - [Success] Post draft created: '{row['post_title']}'")
                    # Incrementally save successful slug
                    db_helper.register_slug(post_slug)
                    successful_count += 1
                    success = True
                    break
                elif response.status_code == 401:
                    print(f" - [Error] 401 Unauthorized. Check your credentials.")
                    break
                else:
                    print(f" - [Error] Failed to create: {response.status_code} - {response.text}")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f" - [Attempt {attempt+1}/{max_retries}] Connection/Timeout error: {e}")
            except Exception as e:
                print(f" - [Error] Unexpected exception: {e}")
                break
                
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                print(f"   Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
                
        if not success:
            print(f" - [FAILED] Could not push '{row['post_title']}' to WordPress.")
            
    print(f"\n[SUCCESS] Push complete. Successfully uploaded {successful_count}/{len(rows)} posts.")

def main():
    if not os.path.exists(html_path):
        print(f"[ERROR] HTML file not found at: {html_path}")
        return

    print(f"[INFO] Reading HTML file from {html_path}...")
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    articles = soup.find_all("article", class_="blog-post")
    print(f"[INFO] Found {len(articles)} blog posts to parse.")

    rows = []
    for idx, art in enumerate(articles):
        # 1. Extract meta info
        meta = art.find("div", class_="post-meta")
        
        category = ""
        focus_keyword = ""
        
        if meta:
            cat_span = meta.find("span", class_="post-cat")
            if cat_span:
                cat_text = cat_span.text.strip()
                # Clean up "Category A · LinkedIn Outreach Strategy" -> "LinkedIn Outreach Strategy"
                if "·" in cat_text:
                    category = cat_text.split("·")[-1].strip()
                else:
                    category = cat_text
                    
            kw_div = meta.find("div", class_="post-kw")
            if kw_div:
                focus_keyword = kw_div.text.replace("Focus keyword:", "").replace("Focus Keyword:", "").strip()

        # 2. Extract Title
        title_el = art.find("h1", class_="post-title")
        if title_el:
            title = title_el.text.strip()
        else:
            title = f"Imported Blog Post {idx+1}"

        # 3. Extract Meta Description (from intro-box)
        intro_box = art.find("div", class_="intro-box")
        meta_description = ""
        if intro_box:
            # Strip tags and normalize spaces for description
            meta_description = re.sub(r'\s+', ' ', intro_box.text).strip()
            if len(meta_description) > 160:
                meta_description = meta_description[:157] + "..."

        # 4. Clean and Extract Content HTML
        # Create a deep copy of the article to manipulate without breaking the main tree
        art_copy = copy.copy(art)
        
        # Decompose elements we don't want in the WordPress body editor
        for el in art_copy.find_all(class_=["post-meta", "word-count"]):
            el.decompose()
        
        # Decompose the title since WP titles are handled in the post_title field separately
        for el in art_copy.find_all("h1", class_="post-title"):
            el.decompose()

        # Decode contents to get inner HTML
        raw_body_html = art_copy.decode_contents().strip()
        
        # Format content HTML with Table of Contents layout
        content_html = format_imported_blog_html(title, raw_body_html)

        # 5. Build Slug
        slug = clean_slug(title)

        row = {
            "post_title": title,
            "post_slug": slug,
            "post_content": content_html,
            "post_status": "draft",
            "post_type": "post",
            "category": category,
            "focus_keyword": focus_keyword,
            "meta_title": title,
            "meta_description": meta_description
        }
        rows.append(row)

    # Convert to DataFrame and Export to CSV
    df = pd.DataFrame(rows)
    df.to_csv(csv_output_path, index=False, encoding="utf-8")
    print(f"[SUCCESS] CSV Export complete. Generated {len(rows)} rows at: {csv_output_path}")

    # Push directly to WordPress if configured
    if EXPORT_MODE in ["wp_api", "both"] and WP_URL and WP_USER and WP_APP_PASSWORD:
        push_posts_to_wordpress(rows)
    else:
        # If CSV only, register incrementally immediately
        for row in rows:
            db_helper.register_slug(row["post_slug"])
        print("\n[INFO] Successful uploads registered incrementally in database/registry.")

if __name__ == "__main__":
    main()

import os
import csv
import json
import base64
import requests
import time
from dotenv import load_dotenv

# Load environment
load_dotenv()

import db_helper
import re

WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()

def clean_slug(text):
    text = str(text).lower()
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

def upload_media_to_wp(image_path, wp_url, auth_user, auth_password):
    """Uploads a local image file or a remote image URL to WordPress Media Library and returns its ID."""
    is_url = str(image_path).startswith("http://") or str(image_path).startswith("https://")
    
    if not is_url and not os.path.exists(image_path):
        return None
    
    # Get filename and extension
    if is_url:
        from urllib.parse import urlparse
        parsed = urlparse(image_path)
        filename = os.path.basename(parsed.path)
        if not filename or "." not in filename:
            filename = "featured-image.jpg"
    else:
        filename = os.path.basename(image_path)
        
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = ".jpg"
    
    # Determine Content-Type
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif"
    }
    content_type = content_types.get(ext, "application/octet-stream")
    
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    auth_str = f"{auth_user}:{auth_password}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    
    endpoint = f"{wp_url.rstrip('/')}/wp-json/wp/v2/media"
    
    try:
        if is_url:
            print(f" - [Media] Downloading remote featured image: {image_path}")
            download_resp = requests.get(image_path, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            if download_resp.status_code == 200:
                media_data = download_resp.content
            else:
                print(f" - [Warning] Failed to download remote image: {download_resp.status_code}")
                return None
        else:
            with open(image_path, "rb") as img_file:
                media_data = img_file.read()
        
        response = requests.post(
            endpoint,
            data=media_data,
            headers=headers,
            auth=(auth_user, auth_password),
            timeout=30
        )
        if response.status_code == 201:
            media_id = response.json().get("id")
            print(f" - [Media] Successfully uploaded featured image '{filename}' (ID: {media_id})")
            return media_id
        else:
            print(f" - [Warning] Media upload failed for '{filename}': {response.status_code} - {response.text}")
    except Exception as e:
        print(f" - [Warning] Error uploading media: {e}")
        
    return None

def push_csv_to_wp():
    csv_path = os.getenv("UPLOADED_FILE_PATH", os.path.join("output", "pseo_export_batch.csv"))
    registry_path = os.path.join("output", "generated_registry.json")
    
    if not os.path.exists(csv_path):
        print(f"[ERROR] CSV file not found at: {csv_path}")
        return
        
    if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
        print("[ERROR] WordPress credentials in .env are not complete. Cannot push.")
        return
        
    print(f"[INFO] Pushing drafts from {csv_path} directly to WordPress REST API at {WP_URL}")
    
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
        print(f"[WARNING] Failed to load registry from database: {e}")
        generated_slugs = set()
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        csv_headers = reader.fieldnames
        rows = list(reader)
        
    print(f"[INFO] Found {len(rows)} entries in CSV.")
    
    # Validate required headers
    required_headers = ["post_title", "post_slug", "post_content"]
    if csv_headers is not None:
        missing_headers = [h for h in required_headers if h not in csv_headers]
        if missing_headers:
            print(f"[ERROR] CSV file is missing required columns: {', '.join(missing_headers)}")
            print(f"[INFO] Found columns: {', '.join(csv_headers)}")
            exit(1)
    
    # Define CPT field mappings
    cpt_fields = {
        "compare": ["competitor_name", "competitor_strength", "competitor_weakness", "ideal_user", "comparison_summary", "CTA"],
        "industry": ["industry_name", "SEO_challenge", "outreach_problem", "relevant_feature", "success_metric"],
        "problem": ["issue", "why_it_happens", "business_impact", "fix", "LinkSprig_solution"],
        "use_case": ["use_case_name", "why_it_matters", "target_audience", "key_workflow", "benefits"],
        "guide": ["guide_title", "difficulty_level", "time_required", "key_takeaways", "steps"]
    }
    
    successful_count = 0
    
    for idx, row in enumerate(rows):
        post_title = row.get("post_title")
        post_slug = row.get("post_slug")
        
        if not post_slug:
            continue
            
        wp_slug = post_slug.strip("/").split("/")[-1] if "/" in post_slug else post_slug
        
        post_content = row.get("post_content")
        post_type = row.get("post_type") or "post"
        meta_title = row.get("meta_title")
        meta_description = row.get("meta_description")
        schema_json_str = row.get("schema_json", "{}")
        category = row.get("category", "")
        focus_keyword = row.get("focus_keyword") or row.get("keyword") or ""
        
        # Map CPTs or 'post' to correct endpoint slug
        wp_endpoint = "posts" if post_type == "post" else post_type
        
        # Check if post already exists on WordPress API by slug
        try:
            check_endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}"
            check_resp = requests.get(
                check_endpoint,
                params={"slug": wp_slug, "status": "any"},
                auth=(WP_USER, WP_APP_PASSWORD),
                headers=headers,
                timeout=10
            )
            if check_resp.status_code == 200 and isinstance(check_resp.json(), list) and len(check_resp.json()) > 0:
                print(f"\n[Skipping {idx+1}/{len(rows)}] Slug already exists on WordPress: {wp_slug}")
                # Register incrementally in db since it exists in WP
                db_helper.register_slug(post_slug)
                db_helper.register_slug(wp_slug)
                continue
        except Exception as e:
            print(f" - [Warning] Error checking if slug '{wp_slug}' exists on WP: {e}")
            # Resilient WP API Check: Safely skip this post instead of uploading duplicate
            print(f" - [Skipping {idx+1}/{len(rows)}] Skipping '{post_slug}' due to WP check error to prevent duplication.")
            continue
        
        # Build ACF fields dynamic dictionary based on post_type
        acf_fields = {}
        fields_list = cpt_fields.get(post_type, [])
        for field in fields_list:
            val = row.get(field, "")
            # Only add if it's not empty
            if val:
                acf_fields[field] = val
                
        cat_id = get_wp_category_id(category, WP_URL, WP_USER, WP_APP_PASSWORD) if category else None
        
        # Check for featured image: either from a CSV column or matching the slug in folders
        featured_media_id = None
        csv_img = row.get("featured_image") or row.get("image_path") or row.get("image")
        
        # Check CSV column path first if present (local file or remote URL)
        if csv_img:
            is_remote = str(csv_img).startswith("http://") or str(csv_img).startswith("https://")
            if is_remote or os.path.exists(csv_img):
                featured_media_id = upload_media_to_wp(csv_img, WP_URL, WP_USER, WP_APP_PASSWORD)
        
        # Fallback to checking folders named after the slug
        if not featured_media_id:
            search_dirs = [
                os.path.join("output", "images"),
                "output",
                "images",
                "assets"
            ]
            for sdir in search_dirs:
                if not os.path.exists(sdir):
                    continue
                for ext in [".jpg", ".jpeg", ".png", ".webp"]:
                    candidate_path = os.path.join(sdir, f"{wp_slug}{ext}")
                    if os.path.exists(candidate_path):
                        featured_media_id = upload_media_to_wp(candidate_path, WP_URL, WP_USER, WP_APP_PASSWORD)
                        break
                if featured_media_id:
                    break
 
        payload = {
            "title": post_title,
            "slug": wp_slug,
            "content": post_content,
            "status": WP_POST_STATUS,
            "type": post_type,
            "meta": {
                "_rank_math_title": meta_title,
                "_rank_math_description": meta_description,
                "_rank_math_focus_keyword": focus_keyword,
                "_yoast_wpseo_title": meta_title,
                "_yoast_wpseo_metadesc": meta_description,
                "_yoast_wpseo_focuskw": focus_keyword,
                "schema_json_ld": schema_json_str,
                **acf_fields
            }
        }
        if cat_id:
            payload["categories"] = [cat_id]
        if featured_media_id:
            payload["featured_media"] = featured_media_id
            
        print(f"\n[Pushing {idx+1}/{len(rows)}] Type: {post_type.upper()} | Title: {post_title}")
        
        max_retries = 3
        backoff_factor = 2
        success = False
        
        for attempt in range(max_retries):
            try:
                endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}"
                response = requests.post(
                    endpoint,
                    json=payload,
                    auth=(WP_USER, WP_APP_PASSWORD),
                    headers=headers,
                    timeout=15
                )
                
                if response.status_code == 201:
                    print(f" - [Success] Draft created: '{post_title}'")
                    # Incrementally save successful slug
                    db_helper.register_slug(post_slug)
                    db_helper.register_slug(wp_slug)
                    successful_count += 1
                    success = True
                    break
                elif response.status_code == 404:
                    print(f" - [Error] Failed to create '{post_title}': 404 - Post type '{post_type}' is not registered.")
                    break
                elif response.status_code == 401:
                    print(f" - [Error] Failed to create '{post_title}': 401 - Unauthorized. Please ensure WP_USER and WP_APP_PASSWORD are correct.")
                    break
                else:
                    print(f" - [Error] Failed to create '{post_title}': {response.status_code} - {response.text}")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f" - [Attempt {attempt+1}/{max_retries}] Connection/Timeout error for '{post_title}': {e}")
            except Exception as e:
                print(f" - [Error] Unexpected exception: {e}")
                break
                
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                print(f"   Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
                
        if not success:
            print(f" - [FAILED] Could not push '{post_title}' to WordPress.")
            
    print(f"\n[INFO] Successfully uploaded {successful_count}/{len(rows)} posts.")
    if successful_count == 0 and len(rows) > 0:
        raise RuntimeError(f"Failed to upload any CSV posts to WordPress ({successful_count}/{len(rows)} uploaded)")
            
    print("\n[SUCCESS] Push operation finished.")

if __name__ == "__main__":
    push_csv_to_wp()

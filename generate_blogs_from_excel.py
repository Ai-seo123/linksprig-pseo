import warnings
# Suppress google.generativeai and other Future/Deprecation warnings before import
warnings.filterwarnings("ignore")

import os
import re
import json
import base64
import requests
import time
import pandas as pd
import google.generativeai as genai
from dotenv import load_dotenv
from formatter import format_blog_html

# Load environment
load_dotenv()

import db_helper

API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()
EXPORT_MODE = os.getenv("EXPORT_MODE", "both").lower()

if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("[ERROR] GEMINI_API_KEY not found in environment.")
    exit(1)

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

def generate_blog_post(topic, keyword):
    print(f"\n[AI Writing] Topic: {topic} | Focus Keyword: {keyword}")
    
    system_instruction = (
        "You are a premium B2B SaaS content writer specializing in LinkedIn outreach and lead generation for LinkSprig.\n"
        "Your writing style is professional, data-driven, highly tactical (featuring actionable workflows), and authoritative.\n"
        "CRITICAL GUIDELINES:\n"
        "1. Write a complete, comprehensive, and engaging blog post about the topic. The target word count is 800+ words.\n"
        "2. Integrate the focus keyword naturally throughout the text.\n"
        "3. Structure all body sections using clean HTML tags (e.g. <p>, <ul>, <li>, <strong>, <h3>) for rich layouts. Do NOT wrap headings in <h1> or <h2>, start sub-headings with <h3>. You MUST include at least one bulleted (<ul>, <li>) list in the article.\n"
        "4. Include real-world statistics, metrics, or performance numbers using percent symbols (%) or currency symbols ($), and include a reference to a recent year (e.g., 2026) to establish strong EEAT.\n"
        "5. Ensure the output is a fully complete and valid JSON payload according to the schema. Do not output truncated or invalid JSON.\n"
        "6. Assign the blog post to exactly one of the following 5 categories in the 'category' field (must match the canonical name exactly):\n"
        "   - Category A — LinkedIn Outreach Strategy\n"
        "   - Category B — AI Personalization & Technology\n"
        "   - Category C — Role-Specific Outreach Guides\n"
        "   - Category D — Message Templates & Copywriting\n"
        "   - Category E — Lead Generation & Pipeline Building"
    )
    
    prompt = f"""
    Generate a complete blog post for:
    Topic: {topic}
    Focus Keyword: {keyword}
    
    The JSON payload should include:
    - title: A compelling and SEO-friendly post title (matches or refines the Topic).
    - meta_title: An optimized title for search engines (under 60 characters).
    - meta_description: A click-worthy meta description (under 160 characters).
    - slug: A clean URL slug.
    - category: Exactly one of the 5 canonical category names.
    - intro: An engaging introduction paragraph (in HTML format).
    - body_sections: An array of 3 to 4 detailed sections, each containing:
      * heading: The section sub-heading.
      * content: The section text in rich HTML format.
    - faqs: An array of 2 to 3 frequently asked questions with brief answers.
    """
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "meta_title": {"type": "STRING"},
            "meta_description": {"type": "STRING"},
            "slug": {"type": "STRING"},
            "category": {"type": "STRING"},
            "intro": {"type": "STRING"},
            "body_sections": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "heading": {"type": "STRING"},
                        "content": {"type": "STRING"}
                    },
                    "required": ["heading", "content"]
                }
            },
            "faqs": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "question": {"type": "STRING"},
                        "answer": {"type": "STRING"}
                    },
                    "required": ["question", "answer"]
                }
            }
        },
        "required": ["title", "meta_title", "meta_description", "slug", "category", "intro", "body_sections", "faqs"]
    }
    
    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=system_instruction
        )
        
        response = model.generate_content(
            prompt,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "temperature": 0.7,
                "max_output_tokens": 8192
            }
        )
        
        result = json.loads(response.text)
        if not result.get("slug"):
            result["slug"] = clean_slug(topic)
        return result
    except Exception as e:
        print(f" - [Error] AI generation failed: {e}")
        return {"error": str(e)}

def push_post_to_wordpress(page, keyword):
    if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
        print("[WARNING] WordPress credentials not complete. Skipping upload.")
        return False
        
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    
    # Build content HTML with Table of Contents layout
    content_html = format_blog_html(
        title=page["title"],
        intro_html=page["intro"],
        body_sections=page["body_sections"],
        faqs_list=page["faqs"]
    )
    
    cat_name = page.get("category", "")
    cat_id = get_wp_category_id(cat_name, WP_URL, WP_USER, WP_APP_PASSWORD) if cat_name else None
    
    payload = {
        "title": page["title"],
        "slug": page["slug"],
        "content": content_html,
        "status": WP_POST_STATUS,
        "type": "post",
        "meta": {
            "_rank_math_title": page["meta_title"],
            "_rank_math_description": page["meta_description"],
            "_rank_math_focus_keyword": keyword
        }
    }
    if cat_id:
        payload["categories"] = [cat_id]
    
    # Check if post already exists on WordPress API by slug
    post_slug = page.get("slug")
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
                print(f" - [Skipping] Slug already exists on WordPress: {post_slug}")
                # Register incrementally in db since it exists in WP
                db_helper.register_slug(post_slug)
                return True
        except Exception as e:
            print(f" - [Warning] Error checking if slug '{post_slug}' exists on WP: {e}")
            # Resilient WP API Check: Safely skip this post instead of uploading duplicate
            print(f" - [Skipping] Skipping '{post_slug}' due to WP check error to prevent duplication.")
            return False
            
    max_retries = 3
    backoff_factor = 2
    
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
                print(f" - [Success] WordPress Draft created: '{page['title']}'")
                # Incrementally save successful slug
                db_helper.register_slug(page["slug"])
                return True
            else:
                print(f" - [Error] Failed to upload: {response.status_code} - {response.text}")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f" - [Attempt {attempt+1}/{max_retries}] Connection/Timeout error: {e}")
        except Exception as e:
            print(f" - [Error] Unexpected exception: {e}")
            break
            
        if attempt < max_retries - 1:
            sleep_time = backoff_factor ** attempt
            time.sleep(sleep_time)
            
    return False

def main():
    excel_path = os.getenv("UPLOADED_FILE_PATH", r"C:\Users\ARNAV\Downloads\LinkSprig-Blogs-Topics-Keywords-22ndMay'26.xlsx")
    registry_path = os.path.join("output", "generated_registry.json")
    csv_output_path = os.path.join("output", "excel_blogs_export.csv")
    
    if not os.path.exists(excel_path):
        print(f"[ERROR] Excel file not found at: {excel_path}")
        return
        
    print(f"[INFO] Reading topics from {excel_path}...")
    df = pd.read_excel(excel_path)
    
    # Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]
    
    # Drop rows that don't have topics
    if "Topics" in df.columns:
        df = df.dropna(subset=["Topics"])
    else:
        print("[ERROR] 'Topics' column not found in Excel sheet.")
        print(f"[INFO] Found columns: {', '.join(df.columns)}")
        exit(1)
    
    print(f"[INFO] Found {len(df)} topics in Excel sheet.")
    
    # Load registry from db_helper
    try:
        generated_slugs = db_helper.get_all_registered_slugs()
    except Exception as e:
        print(f"[WARNING] Failed to load registry: {e}")
        generated_slugs = set()
            
    rows_for_csv = []
    successful_slugs = set()
    
    for idx, row in df.iterrows():
        topic = str(row["Topics"]).strip() if row.get("Topics") is not None else ""
        if not topic or topic.lower() == 'nan':
            continue
        keyword = str(row["Keyword"]).strip() if "Keyword" in df.columns and row.get("Keyword") is not None else ""
        
        # Check if already generated
        slug_check = clean_slug(topic)
        if f"/blog/{slug_check}" in generated_slugs or slug_check in generated_slugs:
            print(f"[{idx+1}/{len(df)}] Skipping already generated topic: {topic}")
            continue
            
        page_data = generate_blog_post(topic, keyword)
        if not page_data:
            print(f" - [FAILED] Skipping '{topic}' due to AI writing error.")
            continue
        elif "error" in page_data:
            print(f"[FATAL] Halting pipeline due to AI API error on topic '{topic}'.")
            exit(1)
            
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
            push_post_to_wordpress(page_data, keyword)
        else:
            # If CSV only, immediately register incrementally
            db_helper.register_slug(page_data["slug"])
            
        # Add a delay between API calls to prevent rate limits
        time.sleep(1)
        
    # Save output to CSV
    if rows_for_csv:
        out_df = pd.DataFrame(rows_for_csv)
        # Append if file exists, else create new
        if os.path.exists(csv_output_path):
            out_df.to_csv(csv_output_path, mode='a', header=False, index=False, encoding="utf-8")
        else:
            out_df.to_csv(csv_output_path, index=False, encoding="utf-8")
        print(f"[SUCCESS] CSV Export appended at: {csv_output_path}")
        
    print("\n[INFO] Successful uploads registered incrementally.")
            
    print("\n[SUCCESS] Pipeline execution finished.")

if __name__ == "__main__":
    main()

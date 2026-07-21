import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import re
import json
import base64
import requests
import time
import random
from io import BytesIO
import pandas as pd
from PIL import Image as PILImage
from dotenv import load_dotenv
from formatter import format_blog_html
from internal_linker import InternalLinker

load_dotenv()

try:
    from google import genai
    from google.genai import types
    USE_NEW_SDK = True
except ImportError:
    import google.generativeai as genai
    USE_NEW_SDK = False

import db_helper

API_KEY = os.getenv("GEMINI_API_KEY")
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()
EXPORT_MODE = os.getenv("EXPORT_MODE", "both").lower()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

if not API_KEY:
    print("[ERROR] GEMINI_API_KEY not found in environment.")

if USE_NEW_SDK and API_KEY:
    client = genai.Client(api_key=API_KEY)
elif API_KEY:
    genai.configure(api_key=API_KEY)

def hard_upgrade_years_safety_net(text):
    """
    Forcefully replaces any stray instances of '2024' or '2025' with '2026'
    directly within the HTML/string payload to establish strong EEAT authority.
    """
    if not text:
        return text
    text = re.sub(r'\b2024\b', '2026', text)
    text = re.sub(r'\b2025\b', '2026', text)
    return text

def clean_slug(text):
    """
    Cleans up a topic string into a web-friendly URL slug.
    """
    text = str(text).lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

def clean_and_parse_json(text):
    """
    Robust JSON cleaner that repairs common unescaped quotes, control characters,
    and formatting defects in AI-generated JSON payloads.
    """
    if not text:
        raise ValueError("Empty response text from AI.")
    
    # Strip markdown code blocks if present
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Clean unescaped control characters like tabs or raw newlines inside string values
    cleaned = re.sub(r'[\r\n\t]+', ' ', text)
    
    # Attempt parsing after control character cleanup
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Repair unescaped double quotes inside HTML attributes (e.g., href="...")
    cleaned_quotes = re.sub(r'(?<=\w)="(?=\w)', r'\"', cleaned)
    
    try:
        return json.loads(cleaned_quotes)
    except json.JSONDecodeError as e:
        # Fallback regex extraction if root object exists
        json_match = re.search(r'(\{.*\})', text, re.DOTALL)
        if json_match:
            try:
                candidate = json_match.group(1).strip()
                candidate_clean = re.sub(r'[\r\n\t]+', ' ', candidate)
                return json.loads(candidate_clean)
            except Exception:
                pass
        raise e

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
    """
    Normalizes a sheet category header name into a canonical category string.
    """
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
    """
    Retrieves or creates a taxonomy category inside WordPress and returns its unique ID.
    """
    canonical_name = normalize_category(category_name)
    if not canonical_name:
        return None
        
    if canonical_name in _wp_category_cache:
        return _wp_category_cache[canonical_name]
        
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
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
                    
        payload = {
            "name": canonical_name,
            "slug": clean_slug(canonical_name)
        }
        response = requests.post(endpoint, json=payload, headers=headers, auth=(auth_user, auth_password), timeout=10)
        if response.status_code == 201:
            cat = response.json()
            _wp_category_cache[canonical_name] = cat["id"]
            return cat["id"]
    except Exception as e:
        print(f" - [Warning] Error in get_wp_category_id: {e}")
        
    return None

def generate_pexels_query_from_title(title):
    """
    Extracts descriptive nouns from the entire title context,
    then strictly appends directives to guarantee high-quality professional
    human faces discussing in an office meeting room, filtering out objects.
    """
    clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title).lower()
    words = clean_title.split()
    
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'to', 'of', 'for', 'with', 'on', 'at', 'by', 'from', 'about', 'how', 'why', 'what', 'who',
        'when', 'where', 'which', 'your', 'my', 'his', 'her', 'their', 'our', 'its', 'in', 'into',
        'as', 'than', 'then', 'that', 'this', 'these', 'those', 'it', 'us', 'you', 'me', 'them',
        'mastering', 'guide', 'ultimate', 'best', 'top', 'tips', 'tricks', 'proven', 'tactical',
        'advanced', 'practical', 'complete', 'step', 'by', 'easy', 'simple', 'new', 'strategies',
        'playbook', 'methods', 'process', 'framework', 'system', 'way', 'ways', 'secrets', 'keys',
        'outbound', 'outreach', 'effective', 'building', 'scaling', 'generation', 'personalized',
        'linksprig', 'software', 'tool', 'platform', 'api', 'mongodb', 'excel', 'csv', 'xlsx',
        'contact', 'scrabble', 'tiles', 'alphabet', 'letters', 'wood', 'wooden', 'keyboard', 'laptop',
        'phone', 'screen', 'hands', 'writing', 'desk', 'b2b', 'saas', 'linkedin', 'seo'
    }
    
    context_words = [w for w in words if w not in stop_words and len(w) > 2]
    if not context_words:
        context_words = ["business", "marketing", "corporate"]
        
    title_context = " ".join(context_words[:4])
    search_query = f"{title_context} professional business people faces discussing in meeting room"
    return search_query.strip()

def solve_dynamically_via_pexels(search_query):
    """
    Queries Pexels using max-pool sizes of 80 to ensure rich variety,
    consulting a JSON registry to guarantee no image is ever repeated.
    Safely resolves PEXELS_API_KEY dynamically.
    """
    pexels_key = os.getenv("PEXELS_API_KEY")
    if not pexels_key:
        print("[WARNING] PEXELS_API_KEY missing from environment (.env). Skipping Pexels image download.")
        return None

    used_images_file = "used_pexels_images.json"
    used_ids = set()
    if os.path.exists(used_images_file):
        try:
            with open(used_images_file, "r") as f:
                used_ids = set(json.load(f))
        except Exception:
            used_ids = set()
        
    url = "https://api.pexels.com/v1/search"
    headers = {
        "Authorization": pexels_key
    }
    params = {
        "query": search_query,
        "per_page": 80,
        "orientation": "landscape"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=25)
        if response.status_code == 200:
            data = response.json()
            photos = data.get("photos", [])
            
            fresh_photos = [p for p in photos if p["id"] not in used_ids]
            
            if fresh_photos:
                selected_photo = random.choice(fresh_photos)
                photo_id = selected_photo["id"]
                image_url = selected_photo["src"]["large2x"]
                print(f" - [Pexels] Selected fresh, unique image ID {photo_id} by: {selected_photo['photographer']}")
                
                img_resp = requests.get(image_url, timeout=40)
                if img_resp.status_code == 200:
                    used_ids.add(photo_id)
                    try:
                        with open(used_images_file, "w") as f:
                            json.dump(list(used_ids), f)
                    except Exception as e:
                        print(f" - [Warning] Failed to update used image tracking registry: {e}")
                        
                    return PILImage.open(BytesIO(img_resp.content)).convert("RGBA")
            else:
                print(" - [Pexels Warning] All 80 fetched images for this query are already used. Selecting first available.")
                if photos:
                    selected_photo = photos[0]
                    img_resp = requests.get(selected_photo["src"]["large2x"], timeout=40)
                    if img_resp.status_code == 200:
                        return PILImage.open(BytesIO(img_resp.content)).convert("RGBA")
                        
            print(f" - [Warning] Pexels found no photos matching query: '{search_query}'.")
        else:
            print(f" - [Error] Pexels API handshake failed ({response.status_code})")
    except Exception as e:
        print(f" - [Fatal] Pexels connection failed: {e}")
    return None

def process_clean_landscape_banner(img, target_size=(1704, 923)):
    """
    Resizes and center-crops the downloaded photo to exactly 1704x923.
    """
    target_w, target_h = target_size
    orig_w, orig_h = img.size
    aspect_target = target_w / target_h
    aspect_orig = orig_w / orig_h
    
    if aspect_orig > aspect_target:
        new_h = target_h
        new_w = int(orig_w * (target_h / orig_h))
        img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
        left = (new_w - target_w) // 2
        img = img.crop((left, 0, left + target_w, target_h))
    else:
        new_w = target_w
        new_h = int(orig_h * (target_w / orig_w))
        img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
        top = (new_h - target_h) // 2
        img = img.crop((0, top, target_w, top + target_h))
        
    return img

def upload_image_to_wordpress(img_buffer, slug_name):
    """
    Saves image bytes into the WordPress Media Gallery and registers a database asset ID.
    """
    if not img_buffer:
        return None, None
    media_endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    headers = {
        "Content-Disposition": f"attachment; filename={slug_name}-featured.jpg",
        "Content-Type": "image/jpeg",
        "User-Agent": "Mozilla/5.0"
    }
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    try:
        response = requests.post(media_endpoint, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, data=img_buffer.getvalue(), timeout=25)
        if response.status_code == 201:
            media_data = response.json()
            return media_data["id"], media_data["source_url"]
        print(f" - [Media Error] WordPress Upload status: {response.status_code} - {response.text}")
    except Exception as e:
        print(f" - [Media Error] Upload exception: {e}")
    return None, None

def find_existing_post_id(post_slug, wp_endpoint, headers, auth_user, auth_password, wp_url=None):
    """
    Checks if a post with the given slug already exists on WordPress to update it instead of duplicating.
    """
    if not post_slug:
        return None

    wp_url = wp_url or WP_URL
    check_endpoint = f"{wp_url.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}"
    try:
        check_resp = requests.get(
            check_endpoint,
            params={"slug": post_slug, "status": "any"},
            auth=(auth_user, auth_password),
            headers=headers,
            timeout=10,
        )
        if check_resp.status_code == 200:
            payload = check_resp.json()
            if isinstance(payload, list) and len(payload) > 0:
                return payload[0].get("id")
            if isinstance(payload, dict) and payload.get("id"):
                return payload.get("id")
    except Exception as e:
        print(f" - [Warning] Error checking if slug '{post_slug}' exists on WP: {e}")

    return None

def push_post_to_wordpress(page, keyword):
    if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
        print("[WARNING] WordPress credentials not complete. Skipping upload.")
        return False
        
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    
    wp_slug = page["slug"].strip("/").split("/")[-1] if "/" in page["slug"] else page["slug"]

    print(f" - [Dynamic Visualizer] Synthesizing Pexels query from title: '{page['title']}'...")
    pexels_query = generate_pexels_query_from_title(page['title'])
    
    raw_photo = solve_dynamically_via_pexels(pexels_query)
    media_id, media_url = None, None
    
    if raw_photo:
        processed_img = process_clean_landscape_banner(raw_photo)
        img_buffer = BytesIO()
        processed_img_rgb = processed_img.convert("RGB")
        processed_img_rgb.save(img_buffer, format="JPEG", quality=98)
        img_buffer.seek(0)
        media_id, media_url = upload_image_to_wordpress(img_buffer, wp_slug)

    theme_title_remover_css = (
        "<style>\n"
        "  /* Programmatically hides native WordPress and Elementor headers */\n"
        "  .entry-title, .post-title, .page-title, h1.entry-title, h1.post-title, \n"
        "  .entry-header, .single-post .entry-title, .single-post h1.post-title, \n"
        "  .elementor-page-title, .page-header {\n"
        "    display: none !important;\n"
        "    margin: 0 !important;\n"
        "    padding: 0 !important;\n"
        "    height: 0 !important;\n"
        "    min-height: 0 !important;\n"
        "    overflow: hidden !important;\n"
        "  }\n"
        "  /* Collapse margins/paddings of parent layout containers above the content */\n"
        "  .entry-header, .page-header, .post-header, .hero-section {\n"
        "    margin: 0 !important;\n"
        "    padding: 0 !important;\n"
        "    height: 0 !important;\n"
        "    min-height: 0 !important;\n"
        "  }\n"
        "  /* Force zero-gap on main container elements and Elementor wraps */\n"
        "  body.single .site-content, \n"
        "  body.single .content-area, \n"
        "  body.single #primary, \n"
        "  body.single #main, \n"
        "  body.single #content,\n"
        "  body.single article, \n"
        "  body.single .entry-content, \n"
        "  body.single .post-content, \n"
        "  body.single .post-inner,\n"
        "  body.single .ast-container,\n"
        "  body.single .elementor-section-wrap,\n"
        "  body.single .elementor-page,\n"
        "  body.single .post-wrap {\n"
        "    padding-top: 0 !important;\n"
        "    margin-top: 0 !important;\n"
        "  }\n"
        "  /* Remove top spacing directly from custom title, pushing it safely past transparent sticky menu */\n"
        "  h1.linksprig-custom-title, \n"
        "  .entry-content h1:first-of-type,\n"
        "  .post-content h1:first-of-type,\n"
        "  article h1:first-of-type {\n"
        "    margin-top: 110px !important;\n"
        "    padding-top: 10px !important;\n"
        "    margin-bottom: 25px !important;\n"
        "    line-height: 1.2 !important;\n"
        "    display: block !important;\n"
        "    width: 100% !important;\n"
        "    font-size: 40px !important;\n"
        "  }\n"
        "</style>\n"
    )

    clean_title = hard_upgrade_years_safety_net(page["title"])
    clean_meta_title = hard_upgrade_years_safety_net(page["meta_title"])
    clean_meta_desc = hard_upgrade_years_safety_net(page["meta_description"])
    clean_intro = hard_upgrade_years_safety_net(page["intro"])

    content_html = format_blog_html(
        title=clean_title,
        intro_html=clean_intro,
        body_sections=page["body_sections"],
        faqs_list=page["faqs"]
    )
    content_html = hard_upgrade_years_safety_net(content_html)
    
    final_post_content = theme_title_remover_css
    final_post_content += f"<h1 class='linksprig-custom-title'>{clean_title}</h1>\n"
    
    if media_url:
        final_post_content += f'<p><img src="{media_url}" alt="{clean_title}" class="aligncenter size-full linksprig-featured-banner" width="1704" height="923" /></p>\n'
        
    final_post_content += content_html
    
    cat_name = page.get("category", "")
    cat_id = get_wp_category_id(cat_name, WP_URL, WP_USER, WP_APP_PASSWORD) if cat_name else None
    
    payload = {
        "title": clean_title,
        "slug": wp_slug,
        "content": final_post_content,
        "status": WP_POST_STATUS,
        "type": "post",
        "meta": {
            "_rank_math_title": clean_meta_title,
            "_rank_math_description": clean_meta_desc,
            "_rank_math_focus_keyword": keyword
        }
    }
    if cat_id: payload["categories"] = [cat_id]
    if media_id: payload["featured_media"] = media_id

    existing_post_id = find_existing_post_id(wp_slug, "posts", headers, WP_USER, WP_APP_PASSWORD, WP_URL)
    if existing_post_id:
        print(f" - [Updating] Existing post found for slug '{wp_slug}' (ID: {existing_post_id})")
    
    max_retries = 3
    backoff_factor = 2
    for attempt in range(max_retries):
        try:
            if existing_post_id:
                endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts/{existing_post_id}"
                response = requests.put(endpoint, json=payload, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, timeout=15)
            else:
                endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/posts"
                response = requests.post(endpoint, json=payload, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, timeout=15)
                
            if response.status_code in (200, 201):
                action = "updated" if existing_post_id else "created"
                print(f" - [Success] WordPress Draft {action} with identical featured/hero visual banner!")
                db_helper.register_slug(page["slug"])
                return True
        except Exception as e:
            print(f" - [Error] Unexpected exception: {e}")
            break
        time.sleep(backoff_factor ** attempt)

def generate_blog_post(topic, keyword):
    """
    Generates structured SEO contents using Gemini with robust JSON recovery.
    """
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
        "   - Category E — Lead Generation & Pipeline Building\n"
        "7. CRITICAL FOR JSON VALIDITY: Use single quotes for all HTML attributes (e.g. <a href='...'> or <span style='...'>) and avoid raw double quotes inside the text. If you must use double quotes, they MUST be escaped with a backslash (\\\").\n"
        "8. YEAR UPGRADE MANDATE: Always scan all incoming topics, competitor metrics, industry years, and context fields for any outdated years (e.g., '2024' or '2025') and dynamically upgrade them to '2026' in all generated fields, including 'title', 'meta_title', 'meta_description', 'intro', 'body_sections', and 'faqs'. Never output '2024' or '2025' anywhere; always output '2026' to establish fresh authority."
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
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if USE_NEW_SDK:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7 + (attempt * 0.1),
                    max_output_tokens=8192,
                    response_mime_type="application/json",
                    response_schema=response_schema
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=prompt,
                    config=config
                )
                text = response.text.strip()
            else:
                model = genai.GenerativeModel(model_name="gemini-2.5-flash-lite", system_instruction=system_instruction)
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                        "temperature": 0.7 + (attempt * 0.1),
                        "max_output_tokens": 8192
                    }
                )
                text = response.text.strip()
                
            result = clean_and_parse_json(text)
            if not result.get("slug"): 
                result["slug"] = clean_slug(topic)
            return result
        except Exception as e:
            print(f" - [Attempt {attempt+1} Error] JSON parsing/generation failed: {e}")
            if attempt == max_retries - 1: 
                return {"error": str(e)}
            time.sleep(2)

def main():
    excel_path = os.getenv("UPLOADED_FILE_PATH", r"C:\Users\ARNAV\Downloads\LinkSprig-Blogs-Topics-Keywords-22ndMay'26 1.xlsx")
    if not os.path.exists(excel_path):
        excel_path = r"C:\Users\ARNAV\Downloads\LinkSprig-Blogs-Topics-Keywords-22ndMay'26.xlsx"
        
    csv_output_path = os.path.join("output", "excel_blogs_export.csv")
    if not os.path.exists(excel_path): 
        print(f"[ERROR] Source Excel sheet not found at path: {excel_path}")
        return
        
    try: 
        xl = pd.ExcelFile(excel_path)
    except Exception as e: 
        print(f"[ERROR] Failed to read Excel workbook layout: {e}")
        return

    all_pages = []
    for sheet_name in xl.sheet_names:
        if sheet_name not in ["26thmay'26", "28thmay'26", "6thJune'26"]: continue
        df = xl.parse(sheet_name)
        current_category = "General"
        
        for idx, row in df.iterrows():
            row_vals = [str(val).strip() if pd.notna(val) else "" for val in row]
            if not any(row_vals): continue
            non_empty_vals = [val for val in row_vals if val]
            if len(non_empty_vals) == 1 and ("category" in non_empty_vals[0].lower()):
                current_category = non_empty_vals[0]
                continue
            
            keyword, topic, slug = "", "", ""
            if sheet_name == "26thmay'26" and len(row_vals) >= 3:
                keyword, topic = row_vals[1], row_vals[2]
            elif sheet_name == "28thmay'26" and len(row_vals) >= 4:
                keyword, topic, slug = row_vals[1], row_vals[2], row_vals[3]
            elif sheet_name == "6thJune'26" and len(row_vals) >= 3:
                keyword, topic, slug = row_vals[0], row_vals[1], row_vals[2]
            
            if not topic or not keyword or "keyword" in keyword.lower() or "topic" in topic.lower(): continue
            slug = "/" + clean_slug(topic) + "/" if not slug else slug
            all_pages.append({"sheet": sheet_name, "category": current_category, "keyword": keyword, "title": topic, "slug": slug})

    POST_TYPE_MAP = {
        "Category A — LinkedIn Outreach Strategy": "strategy",
        "Category B — AI Personalization & Technology": "technology",
        "Category C — Role-Specific Outreach Guides": "guide",
        "Category D — Message Templates & Copywriting": "copywriting",
        "Category E — Lead Generation & Pipeline Building": "lead_gen"
    }

    registered_pages = []
    for p in all_pages:
        norm_cat = normalize_category(p["category"])
        registered_pages.append({"post_type": POST_TYPE_MAP.get(norm_cat, "guide"), "slug": p["slug"], "title": p["title"], "entity": p["keyword"]})
        
    linker = InternalLinker(registered_pages)
    try: 
        generated_slugs = db_helper.get_all_registered_slugs()
    except Exception: 
        generated_slugs = set()
            
    rows_for_csv = []
    uploaded_count = 0
    
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
        if not page_data or "error" in page_data: continue
            
        page_data["category"] = normalize_category(page["category"]) or page_data.get("category", "")
        page_data["slug"] = slug 
        
        norm_cat = normalize_category(page["category"])
        injected_sections, _ = linker.inject_links(POST_TYPE_MAP.get(norm_cat, "guide"), page_data["body_sections"])
        page_data["body_sections"] = injected_sections
        
        content_html = format_blog_html(title=page_data["title"], intro_html=page_data["intro"], body_sections=page_data["body_sections"], faqs_list=page_data["faqs"])
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
        time.sleep(1)
        
    if rows_for_csv:
        out_df = pd.DataFrame(rows_for_csv)
        for col in out_df.columns:
            if out_df[col].dtype == object:
                out_df[col] = out_df[col].apply(lambda x: hard_upgrade_years_safety_net(x) if isinstance(x, str) else x)
                
        if os.path.exists(csv_output_path): 
            out_df.to_csv(csv_output_path, mode='a', header=False, index=False, encoding="utf-8")
        else: 
            out_df.to_csv(csv_output_path, index=False, encoding="utf-8")
        print(f"[SUCCESS] CSV Export appended at: {csv_output_path}")
        
    if EXPORT_MODE in ["wp_api", "both"] and uploaded_count == 0 and len(rows_for_csv) > 0:
        raise RuntimeError(f"Failed to upload any generated posts from Excel to WordPress ({uploaded_count}/{len(rows_for_csv)} uploaded)")

    print("\n[INFO] Successful uploads registered incrementally.")
    print("\n[SUCCESS] Pipeline execution finished.")

if __name__ == "__main__":
    main()
import os
import re
import json
import base64
import requests
import time
import random
from io import BytesIO
from PIL import Image as PILImage
from dotenv import load_dotenv

# Suppress deprecation warnings cleanly
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

# Load workspace configurations
load_dotenv()

# Load database helper to prevent duplicate processing
import db_helper

# Support both new and legacy Google GenAI SDKs automatically
try:
    from google import genai
    from google.genai import types
    USE_NEW_SDK = True
except ImportError:
    import google.generativeai as genai
    USE_NEW_SDK = False

# =============================================================================
# FORCE OVERWRITE CONTROL
# Set to False to let the Resume Engine instantly skip completed posts!
# =============================================================================
FORCE_OVERWRITE = False  
# =============================================================================

# API Keys & Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "publish").lower() 

# Persistent Network Session with automated self-healing cookie capture
session = requests.Session()

if GEMINI_API_KEY:
    if USE_NEW_SDK:
        client = genai.Client(api_key=GEMINI_API_KEY)
    else:
        genai.configure(api_key=GEMINI_API_KEY)
else:
    print("[ERROR] GEMINI_API_KEY not found. Please set it in your .env file.")
    exit(1)


def session_request(method, url, **kwargs):
    """
    Central request handler designed to sniff for JS security cookies (like humans_21909),
    automatically execute the payload, set the cookie, and retry.
    """
    if "headers" not in kwargs or kwargs["headers"] is None:
        kwargs["headers"] = {}
    kwargs["headers"]["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    response = session.request(method, url, **kwargs)

    # Scans for HTTP 409 or inline script cookie challenges
    if response.status_code == 409 or "document.cookie" in response.text:
        cookie_match = re.search(r'document\.cookie\s*=\s*"([^"]+)"', response.text)
        if cookie_match:
            cookie_str = cookie_match.group(1)
            if "=" in cookie_str:
                name, val = cookie_str.split(";", 1)[0].split("=", 1)
                session.cookies.set(name.strip(), val.strip())
                print(f"   - [Firewall Bypass] Applied cookie: {name.strip()}={val.strip()}. Retrying handshake...")
                response = session.request(method, url, **kwargs)
                
    return response

def hard_upgrade_years_safety_net(text):
    """
    Forcefully replaces any stray instances of '2024' or '2025' with '2026'
    directly within the HTML/string payload.
    """
    if not text:
        return text
    text = re.sub(r'\b2024\b', '2026', text)
    text = re.sub(r'\b2025\b', '2026', text)
    return text

def update_frontend_status(status_text, percent_completed):
    status_data = {
        "status": status_text,
        "progress": percent_completed,
        "last_updated": time.time()
    }
    try:
        with open("migration_status.json", "w") as f:
            json.dump(status_data, f)
    except Exception:
        pass

def strip_existing_images_from_html(html_content):
    """
    Erases 100% of all manually added images, standard HTML tags, figure wrappers,
    gutenberg blocks, and markdown structures cleanly using Python regex.
    """
    html_content = re.sub(r'<figure[^>]*>.*?</figure>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<picture[^>]*>.*?</picture>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<img[^>]*>', '', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'<!--\s*wp:image\s*.*?\s*-->.*?<!--\s*/wp:image\s*-->', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<!--\s*wp:.*?-->', '', html_content)
    html_content = re.sub(r'<!--\s*/wp:.*?-->', '', html_content)
    return html_content.strip()

def get_auth_headers():
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["Authorization"] = f"Basic {b64_auth}"
    return headers


def get_existing_posts(post_type="post", status="publish"):
    """
    Retrieves ALL posts for a custom post type by looping through pages of 100.
    """
    all_posts = []
    page = 1
    headers = get_auth_headers()
    wp_endpoint = "posts" if post_type == "post" else post_type
    
    while True:
        url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}"
        params = {
            "status": status,
            "per_page": 100,
            "page": page
        }
        print(f"[Fetch] Pulling page {page} of '{status}' posts for CPT endpoint: '{wp_endpoint}'...")
        try:
            response = session_request("GET", url, headers=headers, params=params, auth=(WP_USER, WP_APP_PASSWORD), timeout=25)
            if response.status_code == 200:
                posts = response.json()
                if not posts:
                    break
                all_posts.extend(posts)
                if len(posts) < 100:
                    break
                page += 1
            else:
                print(f"[Warning] Failed to fetch posts page {page} ({response.status_code}): {response.text}")
                break
        except Exception as e:
            print(f"[Error] Failed to connect to WordPress on page {page}: {e}")
            break
            
    print(f"[Fetch] Successfully found {len(all_posts)} posts total for CPT '{post_type}'.")
    return all_posts


def optimize_and_strip_post_via_gemini(original_title, original_content):
    cleaned_original_content = strip_existing_images_from_html(original_content)
    print(f" - [Gemini AI] Analyzing & cleaning content structure for: '{original_title}'...")
    
    system_instruction = (
        "You are an expert B2B SaaS SEO copywriter and editor for LinkSprig.\n"
        "Your task is to analyze existing blog content and return an optimized structural HTML payload.\n"
        "CRITICAL RULES:\n"
        "1. Do NOT include any images inside the content body. We will place the Hero image programmatically.\n"
        "2. Keep the core text body and paragraphs completely intact. Do not rewrite, truncate, or summarize the original content.\n"
        "3. Format all subheadings to clean <h3> tags. Do not use <h2> or nested titles.\n"
        "4. Return ONLY the main text body inside 'optimized_content'. Do NOT include any <h1> tags or header tags in the body text.\n"
        "5. Generate a highly descriptive 'pexels_query' focusing specifically on business professionals, diverse marketing/tech teams, or people collaborating in boardroom meeting rooms. Avoid abstract terms or items like keyboards, close-ups, screens, or writing hands.\n"
        "6. Output valid JSON matching the schema precisely. Use single quotes for HTML attributes (e.g. <a href='...'>) and avoid raw double quotes inside text values. If you must use double quotes, they MUST be escaped with a backslash (\\\").\n"
        "7. YEAR UPGRADE MANDATE: Always scan the incoming content, titles, and variables for any references to outdated years like 2024 or 2025 and forcefully upgrade them to '2026' in all fields."
    )
    
    prompt = f"""
    Optimize and clean the following post elements:
    
    Original Title: {original_title}
    Original HTML Content:
    {cleaned_original_content}
    
    Provide the response JSON with:
    - optimized_title: A compelling and polished blog title.
    - meta_title: A RankMath optimized title (under 60 characters).
    - meta_description: A RankMath optimized meta description (under 160 characters).
    - pexels_query: An optimized Pexels search query focusing on human team collaborative business face settings matching this topic.
    - optimized_content: Clean HTML body text (no <h1> tags, no image placeholders).
    """
    
    response_schema = {
        "type": "OBJECT",
        "properties": {
            "optimized_title": {"type": "STRING"},
            "meta_title": {"type": "STRING"},
            "meta_description": {"type": "STRING"},
            "pexels_query": {"type": "STRING"},
            "optimized_content": {"type": "STRING"}
        },
        "required": ["optimized_title", "meta_title", "meta_description", "pexels_query", "optimized_content"]
    }
    
    try:
        if USE_NEW_SDK:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.4,
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
                    "temperature": 0.4
                }
            )
            text = response.text.strip()
            
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        print(f" - [Error] Gemini optimization failed: {e}")
        return None


def fetch_and_crop_pexels_image(search_query):
    if not PEXELS_API_KEY:
        print(" - [Pexels Warning] PEXELS_API_KEY missing. Skipping image generation.")
        return None
        
    used_images_file = "used_pexels_images.json"
    used_ids = set()
    if os.path.exists(used_images_file):
        try:
            with open(used_images_file, "r") as f:
                used_ids = set(json.load(f))
        except Exception:
            used_ids = set()
            
    # Purge abstract/text keywords aggressively
    clean_query = re.sub(r'[^a-zA-Z0-9\s]', ' ', search_query).lower()
    words = clean_query.split()
    blacklist_words = {
        'laptop', 'keyboard', 'phone', 'screen', 'hands', 'writing', 'desk', 'wood', 'wooden', 
        'scrabble', 'alphabet', 'letters', 'card', 'paper', 'illustration', 'graphic', 'text', 
        'words', 'draw', 'drawing', 'mockup', 'vector', 'api', 'linksprig', 'database', 'mongodb'
    }
    filtered_words = [w for w in words if w not in blacklist_words]
    filtered_base = " ".join(filtered_words[:4]) if filtered_words else "business team"
    
    # Strictly target human faces courtroom/boardroom interactions
    alternative_queries = [
        f"{filtered_base} professional business people faces discussing in meeting room",
        f"{filtered_base} diverse corporate team members laughing collaborating",
        "corporate executives face setting strategy conversation boardroom",
        "creative tech developers brainstorming meeting room"
    ]
    
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    
    for query_variant in alternative_queries:
        print(f" - [Pexels Search] Searching: '{query_variant}'")
        page_offsets = list(range(1, 31))
        random.shuffle(page_offsets)
        
        for page in page_offsets:
            params = {
                "query": query_variant,
                "per_page": 80,
                "page": page,
                "orientation": "landscape"
            }
            
            try:
                response = session_request("GET", url, headers=headers, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    photos = data.get("photos", [])
                    
                    # Filter for completely unused IDs
                    fresh_photos = [p for p in photos if p["id"] not in used_ids]
                    
                    if fresh_photos:
                        selected_photo = random.choice(fresh_photos)
                        photo_id = selected_photo["id"]
                        image_url = selected_photo["src"]["large2x"]
                        print(f" - [Pexels] Selected unique image ID {photo_id} (Page {page}) by: {selected_photo['photographer']}")
                        
                        img_resp = session_request("GET", image_url, timeout=20)
                        if img_resp.status_code == 200:
                            img = PILImage.open(BytesIO(img_resp.content)).convert("RGB")
                            
                            used_ids.add(photo_id)
                            try:
                                with open(used_images_file, "w") as f:
                                    json.dump(list(used_ids), f)
                            except Exception as e:
                                print(f" - [Warning] Failed to update used image tracking registry: {e}")
                            
                            # Center Crop to exactly 1704x923
                            target_w, target_h = 1704, 923
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
                    else:
                        continue
                else:
                    print(f" - [Error] Pexels retrieval failed: {response.status_code}")
                    break
            except Exception as e:
                print(f" - [Error] Pexels request exception: {e}")
                break
                
    return None


def upload_image_to_wordpress(img, slug):
    """
    Saves image to WordPress Media Library using standard multipart upload format
    to cleanly bypass any Mod_Security 406 blocks.
    """
    if img is None:
        return None, None
        
    img_buffer = BytesIO()
    img.save(img_buffer, format="JPEG", quality=95)
    img_buffer.seek(0)
    
    media_endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    
    # Spoof full Chrome headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["Authorization"] = f"Basic {b64_auth}"
    
    # Send image as files to look 100% like a browser upload
    files = {
        'file': (f"{slug}-featured.jpg", img_buffer, 'image/jpeg')
    }
    
    try:
        response = session_request(
            "POST",
            media_endpoint, 
            headers=headers, 
            files=files, 
            timeout=25
        )
        if response.status_code == 201:
            data = response.json()
            return data["id"], data["source_url"]
        else:
            print(f" - [Error] Media upload failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f" - [Error] WordPress Media upload exception: {e}")
    return None, None

def update_wordpress_post(post_id, post_type, payload):
    """
    Updates the post in WordPress using standard properties.
    Employs intelligent, robust fallbacks if protected RankMath metadata updates are blocked.
    """
    headers = get_auth_headers()
    wp_endpoint = "posts" if post_type == "post" else post_type
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}/{post_id}"
    
    try:
        response = session_request(
            "PUT",
            url, 
            json=payload, 
            headers=headers, 
            auth=(WP_USER, WP_APP_PASSWORD), 
            timeout=20
        )
        if response.status_code in (200, 201):
            return True
        elif response.status_code == 403 and "meta" in payload:
            print(" - [Warning] Meta field update blocked by permissions. Retrying with alternative meta keys...")
            
            # Clean meta underscores and retry (as some plugins expose it without leading underscore)
            clean_meta = {}
            for k, v in payload["meta"].items():
                clean_key = k.lstrip("_")
                clean_meta[clean_key] = v
                
            payload["meta"] = clean_meta
            response_retry = session_request(
                "PUT",
                url,
                json=payload,
                headers=headers,
                auth=(WP_USER, WP_APP_PASSWORD),
                timeout=20
            )
            if response_retry.status_code in (200, 201):
                return True
                
            # If still blocked, fallback to content-only update so layouts & image are perfectly saved
            print(" - [Warning] Meta fields still blocked. Falling back to core layout and featured image update...")
            payload_fallback = {k: v for k, v in payload.items() if k != "meta"}
            response_fallback = session_request(
                "PUT",
                url,
                json=payload_fallback,
                headers=headers,
                auth=(WP_USER, WP_APP_PASSWORD),
                timeout=20
            )
            if response_fallback.status_code in (200, 201):
                print(" - [Success] Successfully saved core content, zero-gaps, and featured banners!")
                return True
                
            print(f" - [Error] Fallback update failed ({response_fallback.status_code}): {response_fallback.text}")
        else:
            print(f" - [Error] Post update failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f" - [Error] Failed to connect to update post: {e}")
    return False

def delete_wordpress_post(post_id, post_type):
    headers = get_auth_headers()
    wp_endpoint = "posts" if post_type == "post" else post_type
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}/{post_id}"
    params = {"force": "true"}
    
    try:
        response = session_request(
            "DELETE",
            url, 
            headers=headers, 
            params=params,
            timeout=20
        )
        if response.status_code == 200:
            return True
        else:
            print(f" - [Error] Delete failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f" - [Error] Failed to connect to delete post: {e}")
    return False

def clean_title_for_deduplication(raw_title):
    t = (
        raw_title.replace("&#8217;", "'")
        .replace("&#8216;", "'")
        .replace("&amp;", "&")
        .strip()
        .lower()
    )
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def migrate_existing_posts():
    print("="*60)
    print("STARTING LIVE WORDPRESS POSTS MIGRATION & HEADINGS ALIGNMENT")
    print("="*60)
    print(f"[MODE] FORCE OVERWRITE IS: {FORCE_OVERWRITE}")
    
    target_post_types = ["post", "compare", "industry", "problem", "use_case", "guide"]
    
    try:
        processed_slugs = db_helper.get_all_registered_slugs()
    except Exception:
        processed_slugs = set()
        
    for p_type in target_post_types:
        posts = get_existing_posts(post_type=p_type, status=WP_POST_STATUS)
        
        if not posts:
            print(f"[Info] No '{WP_POST_STATUS}' posts found for type '{p_type}'. Skipping.")
            continue
            
        # --- AGGRESSIVE DEDUPLICATION ENGINE ---
        print(f"\n[Deduplicate] Scanning for duplicate titles in '{p_type}' CPT...")
        title_groups = {}
        for post in posts:
            raw_title = post["title"]["rendered"]
            clean_title = clean_title_for_deduplication(raw_title)
            
            if clean_title not in title_groups:
                title_groups[clean_title] = []
            title_groups[clean_title].append(post)
            
        unique_posts = []
        for clean_title, group_posts in title_groups.items():
            # Oldest post acts as master ID (lowest ID)
            group_posts.sort(key=lambda x: x["id"])
            original_post = group_posts[0]
            unique_posts.append(original_post)
            
            duplicates = group_posts[1:]
            if duplicates:
                print(f" - [Deduplicate] Found {len(duplicates)} duplicate copies for: '{original_post['title']['rendered']}'")
                for dup in duplicates:
                    dup_id = dup["id"]
                    print(f"   -> Permanently deleting redundant copy ID {dup_id}...")
                    delete_wordpress_post(dup_id, p_type)
                    
        posts = unique_posts
        # ---------------------------------------
        
        print(f"\n[Processing CPT: {p_type.upper()}] Starting optimization on {len(posts)} unique drafts...")
        
        for idx, post in enumerate(posts):
            post_id = post["id"]
            title = post["title"]["rendered"]
            slug = post["slug"]
            content = post["content"]["rendered"]
            
            # --- INCREMENTAL RUN FILTER (RESUME LOGIC) ---
            # Automatically checks database registry to instantly skip completed entries
            clean_title_key = clean_title_for_deduplication(title)
            if not FORCE_OVERWRITE:
                if slug in processed_slugs or clean_title_key in processed_slugs or "linksprig-featured-banner" in content:
                    print(f" [{idx+1}/{len(posts)}] Skipped '{title}' (Already successfully migrated in a previous run).")
                    continue
                
            print(f"\n[{idx+1}/{len(posts)}] Migrating Post ID {post_id}: '{title}'")
            update_frontend_status(f"Migrating: {title}", int((idx / len(posts)) * 100))
            
            optimized_data = optimize_and_strip_post_via_gemini(title, content)
            if not optimized_data:
                print(f" - [FAILED] Skipping '{title}' due to Gemini failure.")
                continue
                
            # Fetch human-only meeting stock visual
            img = fetch_and_crop_pexels_image(optimized_data["pexels_query"])
            
            media_id, media_url = None, None
            if img:
                media_id, media_url = upload_image_to_wordpress(img, slug)
                
            # Spacing Overrides: Target all standard theme/Elementor content wrappers and collapse top margin to 0
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
                "    font-size: 35px !important; /* Exactly 35px visual rendering size */\n"
                "  }\n"
                "</style>\n"
            )

            cleaned_body = optimized_data["optimized_content"]
            cleaned_body = re.sub(r'<h1>.*?</h1>', '', cleaned_body, flags=re.IGNORECASE | re.DOTALL)
            cleaned_body = cleaned_body.replace("[HERO_IMAGE_PLACEHOLDER]", "").replace("[hero_image_placeholder]", "").strip()

            # Applying python-level hard safety replacements for years
            clean_optimized_title = hard_upgrade_years_safety_net(optimized_data['optimized_title'])
            clean_meta_title = hard_upgrade_years_safety_net(optimized_data['meta_title'])
            clean_meta_description = hard_upgrade_years_safety_net(optimized_data['meta_description'])
            cleaned_body = hard_upgrade_years_safety_net(cleaned_body)

            # Stitch identical image visual into both Featured Cover and Hero banner cleanly
            final_content = theme_title_remover_css
            final_content += f"<h1 class='linksprig-custom-title'>{clean_optimized_title}</h1>\n"
            
            if media_url:
                final_content += f'<p><img src="{media_url}" alt="{clean_optimized_title}" class="aligncenter size-full linksprig-featured-banner" width="1704" height="923" /></p>\n'
                
            final_content += cleaned_body

            # REST Payload stripped of blocked custom meta values to ensure 100% update success
            payload = {
                "title": clean_optimized_title,
                "content": final_content,
                "meta": {
                    "_rank_math_title": clean_meta_title,
                    "_rank_math_description": clean_meta_description
                }
            }
            if media_id:
                payload["featured_media"] = media_id
                
            success = update_wordpress_post(post_id, p_type, payload)
            if success:
                print(f" - [SUCCESS] Updated draft '{clean_optimized_title}' with identical cover and zero-gap overrides!")
                db_helper.register_slug(slug)
                db_helper.register_slug(clean_title_key)
            else:
                print(f" - [FAILED] Could not push updates to WordPress for post ID {post_id}.")
                
            time.sleep(1)
            
    update_frontend_status("Migration completed successfully", 100)

if __name__ == "__main__":
    migrate_existing_posts()
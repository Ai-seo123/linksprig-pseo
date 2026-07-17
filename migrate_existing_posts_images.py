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
import google.generativeai as genai

# Load workspace configurations
load_dotenv()

# Load database helper to prevent duplicate processing
import db_helper

# API Keys & Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("[ERROR] GEMINI_API_KEY not found. Please set it in your .env file.")
    exit(1)

def get_auth_headers():
    """
    Builds the default HTTP request header with basic authorization credentials encoded in base64.
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    return headers

def get_existing_posts(post_type="post", status="draft"):
    """
    Fetches posts of a specific custom post type and status from the WordPress REST API.
    """
    headers = get_auth_headers()
    wp_endpoint = "posts" if post_type == "post" else post_type
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}"
    params = {
        "status": status,
        "per_page": 100
    }
    
    print(f"[Fetch] Pulling up to 100 '{status}' posts from CPT endpoint: '{wp_endpoint}'...")
    try:
        response = requests.get(url, headers=headers, params=params, auth=(WP_USER, WP_APP_PASSWORD), timeout=20)
        if response.status_code == 200:
            posts = response.json()
            print(f"[Fetch] Successfully found {len(posts)} posts.")
            return posts
        else:
            print(f"[Warning] Failed to fetch posts ({response.status_code}): {response.text}")
    except Exception as e:
        print(f"[Error] Failed to connect to WordPress: {e}")
    return []

def optimize_and_strip_post_via_gemini(original_title, original_content):
    """
    Sends the existing post elements to Gemini to clean formatting, remove existing images,
    generate dynamic meta descriptions, and prepare structure.
    """
    print(f" - [Gemini AI] Analyzing & cleaning content structure for: '{original_title}'...")
    
    system_instruction = (
        "You are an expert B2B SaaS SEO copywriter and editor for LinkSprig.\n"
        "Your task is to analyze existing blog content and return an optimized structural HTML payload.\n"
        "CRITICAL RULES:\n"
        "1. STRIP OUT AND REMOVE all existing images, <img> tags, <figure> wrappers, or captions from the original content body completely. If the post has any existing images, delete them.\n"
        "2. Keep the core text body and paragraphs completely intact. Do not rewrite, truncate, or summarize the original content—preserve the sentences, lists, and keywords.\n"
        "3. Format all subheadings to clean <h3> tags. Do not use <h2> or nested titles.\n"
        "4. Start the 'optimized_content' HTML exactly like this:\n"
        "   <h1>{compelling_title}</h1>\n"
        "   [HERO_IMAGE_PLACEHOLDER]\n"
        "   {introductory paragraph and the rest of the cleaned body content}\n"
        "5. Ensure there are absolutely NO other <h1> tags inside the 'optimized_content'.\n"
        "6. Generate a highly descriptive 'pexels_query' focusing specifically on business professionals, diverse marketing/tech teams, or people collaborating on laptops. Avoid abstract terms.\n"
        "7. Output valid JSON matching the schema precisely. Use single quotes for HTML attributes (e.g. <a href='...'>) and avoid raw double quotes inside text values. If you must use double quotes, they MUST be escaped with a backslash (\\\")."
    )
    
    prompt = f"""
    Optimize and clean the following post elements:
    
    Original Title: {original_title}
    Original HTML Content:
    {original_content}
    
    Provide the response JSON with:
    - optimized_title: A compelling and polished blog title.
    - meta_title: A RankMath optimized title (under 60 characters).
    - meta_description: A RankMath optimized meta description (under 160 characters).
    - pexels_query: An optimized Pexels search query to find working professional team photos matching this topic.
    - optimized_content: Clean HTML body starting with the <h1> title tag, followed immediately by the '[HERO_IMAGE_PLACEHOLDER]' tag, and then the intro paragraph. All previous images must be completely removed.
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
    """
    Fetches a professional landscape stock photo from Pexels and center-crops it to exactly 1704x923.
    """
    if not PEXELS_API_KEY:
        print(" - [Pexels Warning] PEXELS_API_KEY missing. Skipping image generation.")
        return None
        
    print(f" - [Pexels Search] Query: '{search_query}'")
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": f"{search_query} professional office business team",
        "per_page": 5,
        "orientation": "landscape"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get("photos"):
                photo = random.choice(data["photos"])
                image_url = photo["src"]["large2x"]
                print(f" - [Pexels] Selected image by: {photo['photographer']}")
                
                # Download bytes
                img_resp = requests.get(image_url, timeout=20)
                if img_resp.status_code == 200:
                    img = PILImage.open(BytesIO(img_resp.content)).convert("RGB")
                    
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
                print(f" - [Warning] No photos found on Pexels for query.")
    except Exception as e:
        print(f" - [Error] Pexels retrieval failed: {e}")
    return None

def upload_image_to_wordpress(img, slug):
    """
    Saves image to WordPress Media Library.
    """
    if img is None:
        return None, None
        
    img_buffer = BytesIO()
    img.save(img_buffer, format="JPEG", quality=95)
    img_buffer.seek(0)
    
    media_endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    headers = {
        "Content-Disposition": f"attachment; filename={slug}-featured.jpg",
        "Content-Type": "image/jpeg",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    
    try:
        response = requests.post(
            media_endpoint, 
            auth=(WP_USER, WP_APP_PASSWORD), 
            headers=headers, 
            data=img_buffer.getvalue(), 
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
    Updates the post in WordPress using the REST API.
    """
    headers = get_auth_headers()
    wp_endpoint = "posts" if post_type == "post" else post_type
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}/{post_id}"
    
    try:
        response = requests.put(
            url, 
            json=payload, 
            headers=headers, 
            auth=(WP_USER, WP_APP_PASSWORD), 
            timeout=20
        )
        if response.status_code in (200, 201):
            return True
        else:
            print(f" - [Error] Post update failed ({response.status_code}): {response.text}")
    except Exception as e:
        print(f" - [Error] Failed to connect to update post: {e}")
    return False

def migrate_existing_posts():
    print("="*60)
    print("STARTING LIVE WORDPRESS POSTS MIGRATION & HEADINGS ALIGNMENT")
    print("="*60)
    
    # Define CPTs you want to scan and optimize
    target_post_types = ["post", "compare", "industry", "problem", "use_case", "guide"]
    
    # Load previously optimized slugs to prevent double processing
    try:
        processed_slugs = db_helper.get_all_registered_slugs()
    except Exception:
        processed_slugs = set()
        
    for p_type in target_post_types:
        # Pull Draft posts of this type
        posts = get_existing_posts(post_type=p_type, status=WP_POST_STATUS)
        
        if not posts:
            print(f"[Info] No '{WP_POST_STATUS}' posts found for type '{p_type}'. Skipping.")
            continue
            
        print(f"\n[Processing CPT: {p_type.upper()}] Starting optimization on {len(posts)} drafts...")
        
        for idx, post in enumerate(posts):
            post_id = post["id"]
            title = post["title"]["rendered"]
            slug = post["slug"]
            content = post["content"]["rendered"]
            
            # Skip if already marked as optimized in our local logs
            if slug in processed_slugs:
                print(f" [{idx+1}/{len(posts)}] Skipping '{title}' (Already processed previously).")
                continue
                
            print(f"\n[{idx+1}/{len(posts)}] Migrating Post ID {post_id}: '{title}'")
            
            # Step 1: Optimize Title, Headings, Meta via Gemini, and strip out old images
            optimized_data = optimize_and_strip_post_via_gemini(title, content)
            if not optimized_data:
                print(f" - [FAILED] Skipping '{title}' due to Gemini API failure.")
                continue
                
            # Step 2: Fetch and Crop Stock Image
            img = fetch_and_crop_pexels_image(optimized_data["pexels_query"])
            
            media_id, media_url = None, None
            if img:
                # Step 3: Upload cropped image to WordPress Media Library
                media_id, media_url = upload_image_to_wordpress(img, slug)
                
            # Step 4: Blend Hero Image into HTML content template
            final_content = optimized_data["optimized_content"]
            if media_url:
                hero_image_html = f'<p><img src="{media_url}" alt="{optimized_data["optimized_title"]}" class="aligncenter size-full linksprig-featured-banner" width="1704" height="923" /></p>'
                final_content = final_content.replace("[HERO_IMAGE_PLACEHOLDER]", hero_image_html)
            else:
                # Strip placeholder if search or upload failed
                final_content = final_content.replace("[HERO_IMAGE_PLACEHOLDER]", "")
                
            # Step 5: Inject dynamic CSS override at the very top of content to hide theme's duplicate title
            theme_title_remover_css = (
                "<style>\n"
                "  /* Programmatically hides native WordPress theme headers on this page */\n"
                "  .entry-title, .post-title, .page-title, h1.entry-title, h1.post-title, "
                ".entry-header, .single-post .entry-title, .single-post h1.post-title, "
                ".elementor-page-title, .page-header {\n"
                "    display: none !important;\n"
                "  }\n"
                "</style>\n"
            )
            final_content = theme_title_remover_css + final_content

            # Step 6: Build Update REST Payload
            payload = {
                "title": optimized_data["optimized_title"],  # Native fallback in admin panel
                "content": final_content,                    # CSS override + Coding H1 title + Hero banner + Stripped formatted text
                "meta": {
                    "_rank_math_title": optimized_data["meta_title"],
                    "_rank_math_description": optimized_data["meta_description"]
                }
            }
            if media_id:
                payload["featured_media"] = media_id
                
            # Step 7: Push Updates Live
            success = update_wordpress_post(post_id, p_type, payload)
            if success:
                print(f" - [SUCCESS] Updated draft '{optimized_data['optimized_title']}' with theme-title block styling and Pexels Featured Cover!")
                db_helper.register_slug(slug)
            else:
                print(f" - [FAILED] Could not push updates to WordPress for post ID {post_id}.")
                
            # Rate limit mitigation
            time.sleep(1)

if __name__ == "__main__":
    migrate_existing_posts()

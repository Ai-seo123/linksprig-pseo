import os
import requests
import base64
import time
from dotenv import load_dotenv

# Load configuration
load_dotenv()

WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
    print("[ERROR] Please configure WP_URL, WP_USER, and WP_APP_PASSWORD in your .env file.")
    exit(1)

# Search folders for local images
IMAGE_DIRS = [
    os.path.join("output", "images"),
    "output",
    "images",
    "assets"
]

def upload_media_to_wp(image_path):
    """Uploads a local image file to the WordPress Media Library and returns its ID and URL."""
    if not os.path.exists(image_path):
        return None, None
    
    filename = os.path.basename(image_path)
    ext = os.path.splitext(filename)[1].lower()
    
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
    
    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media"
    
    try:
        with open(image_path, "rb") as img_file:
            media_data = img_file.read()
        
        response = requests.post(
            endpoint,
            data=media_data,
            headers=headers,
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=30
        )
        if response.status_code == 201:
            res_json = response.json()
            media_id = res_json.get("id")
            media_url = res_json.get("source_url")
            print(f"   [Media] Successfully uploaded '{filename}' (ID: {media_id})")
            return media_id, media_url
        else:
            print(f"   [Warning] Failed to upload '{filename}': {response.status_code} - {response.text}")
    except Exception as e:
        print(f"   [Warning] Error uploading media: {e}")
        
    return None, None

def find_local_image_for_slug(slug):
    """Searches for a matching image file in the configured search directories."""
    for sdir in IMAGE_DIRS:
        if not os.path.exists(sdir):
            continue
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            candidate_path = os.path.join(sdir, f"{slug}{ext}")
            if os.path.exists(candidate_path):
                return candidate_path
    return None

def fetch_all_posts(post_type="post"):
    """Fetches all posts of a specific post type from WordPress REST API (paginated)."""
    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{post_type}"
    posts = []
    page = 1
    per_page = 100
    
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    
    while True:
        try:
            print(f"Fetching page {page} of '{post_type}' posts...")
            response = requests.get(
                endpoint,
                params={"page": page, "per_page": per_page, "status": "any"},
                headers=headers,
                auth=(WP_USER, WP_APP_PASSWORD),
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                posts.extend(data)
                page += 1
            else:
                # 400 page limit reached
                break
        except Exception as e:
            print(f"Error fetching posts: {e}")
            break
            
    print(f"Found {len(posts)} total posts for type '{post_type}'.")
    return posts

def inject_image_tag_below_h1(html_content, img_url, title):
    """Inserts a responsive image tag directly below the main H1 tag in HTML."""
    if not html_content or not img_url:
        return html_content
        
    # Check if an image tag is already injected to prevent duplicates
    if "linksprig-featured-image" in html_content or img_url in html_content:
        return html_content
        
    img_tag = f'\n    <img src="{img_url}" class="linksprig-featured-image featured-image" alt="{title}" style="width: 100%; max-width: 1704px; height: auto; aspect-ratio: 1704/923; object-fit: cover; border-radius: 8px; margin-top: 10px; margin-bottom: 24px;" />'
    
    # Locate H1 and insert right after it
    if "</h1>" in html_content:
        parts = html_content.split("</h1>", 1)
        return parts[0] + "</h1>" + img_tag + parts[1]
    
    return html_content

def process_bulk_update():
    post_types = ['post', 'compare', 'industry', 'problem', 'use_case', 'guide']
    total_updated = 0
    
    for ptype in post_types:
        print(f"\n--- Starting Migration for Post Type: {ptype.upper()} ---")
        posts = fetch_all_posts(ptype)
        
        for idx, post in enumerate(posts):
            post_id = post.get("id")
            slug = post.get("slug")
            title = post.get("title", {}).get("rendered", "")
            current_featured_media = post.get("featured_media")
            content_html = post.get("content", {}).get("rendered", "")
            
            # Find local image
            local_img = find_local_image_for_slug(slug)
            if not local_img:
                continue
                
            print(f"\n[{idx+1}/{len(posts)}] Processing Post ID {post_id} | Slug: {slug}")
            
            media_id = None
            media_url = None
            
            # If the post doesn't have a featured media, upload and set it
            if not current_featured_media or current_featured_media == 0:
                print(f" -> No featured image found on WP. Uploading local image: {local_img}")
                media_id, media_url = upload_media_to_wp(local_img)
            else:
                print(f" -> Post already has featured media ID: {current_featured_media}. Checking if we need to update content tag...")
                # We can retrieve the media URL to check content tags
                try:
                    media_resp = requests.get(
                        f"{WP_URL.rstrip('/')}/wp-json/wp/v2/media/{current_featured_media}",
                        auth=(WP_USER, WP_APP_PASSWORD),
                        timeout=10
                    )
                    if media_resp.status_code == 200:
                        media_url = media_resp.json().get("source_url")
                except Exception as e:
                    print(f"    Failed to fetch existing media URL: {e}")
            
            # Prepare update payload
            payload = {}
            if media_id:
                payload["featured_media"] = media_id
                
            # Check if we should inject the image tag below H1 inside the body content
            if media_url:
                new_content = inject_image_tag_below_h1(content_html, media_url, title)
                if new_content != content_html:
                    payload["content"] = new_content
                    print(" -> Injected image tag below the H1 block.")
            
            # If there's anything to update, push it
            if payload:
                endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{ptype}/{post_id}"
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0"
                }
                try:
                    response = requests.post(
                        endpoint,
                        json=payload,
                        auth=(WP_USER, WP_APP_PASSWORD),
                        headers=headers,
                        timeout=15
                    )
                    if response.status_code == 200:
                        print(f" -> [Success] Post {post_id} updated successfully.")
                        total_updated += 1
                    else:
                        print(f" -> [Error] Failed to update post {post_id}: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f" -> [Error] Connection error while updating post: {e}")
            else:
                print(" -> Post is already up-to-date.")
                
            # Polite sleep to respect API limits
            time.sleep(0.5)

    print(f"\n[Migration Complete] Successfully updated {total_updated} posts across WordPress.")

if __name__ == "__main__":
    process_bulk_update()

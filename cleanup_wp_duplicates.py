import os
import re
import json
import base64
import requests
import argparse
import time
from dotenv import load_dotenv

# Load configuration
load_dotenv()

WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

STATE_FILE = os.path.join("output", "cleanup_state.json")
POST_TYPES = ["posts", "compare", "industry", "problem", "use_case", "guide"]


def get_auth_headers():
    if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
        raise ValueError("WP_URL, WP_USER, and WP_APP_PASSWORD must be set in your .env file.")
    auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
    b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
    return {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LinkSprig-Cleaner/1.0",
        "X-HTTP-Authorization": f"Basic {b64_auth}"
    }


def load_state():
    """Loads checkpoint state from output/cleanup_state.json"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load cleanup state file: {e}. Starting fresh.")
    return {
        "current_endpoint_idx": 0,
        "current_page": 1,
        "last_processed_id": 0,
        "total_posts_examined": 0,
        "total_duplicates_cleaned": 0,
        "cleaned_ids": [],
        "finished": False
    }


def save_state(state):
    """Saves checkpoint state to output/cleanup_state.json"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save cleanup state file: {e}")


def extract_base_slug(slug: str) -> tuple[str, bool]:
    """
    Checks if a slug ends with -2, -3, etc. (WordPress auto-increment suffix).
    Returns (base_slug, is_duplicate_pattern).
    Example: 'linkedin-outreach-2' -> ('linkedin-outreach', True)
    """
    slug = str(slug).strip("/").strip()
    match = re.match(r"^(.*?)-(\d+)$", slug)
    if match:
        base_slug = match.group(1)
        suffix_num = int(match.group(2))
        if suffix_num >= 2:
            return base_slug, True
    return slug, False


def fetch_posts_page(endpoint: str, page: int, headers: dict, per_page: int = 100):
    """Fetches a page of posts from WordPress REST API across all active statuses."""
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{endpoint}"
    valid_statuses = "publish,draft,pending,private,future"
    params = {
        "per_page": per_page,
        "page": page,
        "status": valid_statuses,
        "orderby": "id",
        "order": "asc"
    }
    try:
        resp = requests.get(url, params=params, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, timeout=25)
        if resp.status_code == 200:
            posts = resp.json()
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            total_posts = int(resp.headers.get("X-WP-Total", len(posts)))
            return posts, total_pages, total_posts
        elif resp.status_code == 400:
            # Fallback without status parameter if custom endpoint restricts status
            params.pop("status", None)
            fallback = requests.get(url, params=params, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, timeout=25)
            if fallback.status_code == 200:
                posts = fallback.json()
                total_pages = int(fallback.headers.get("X-WP-TotalPages", 1))
                total_posts = int(fallback.headers.get("X-WP-Total", len(posts)))
                return posts, total_pages, total_posts
        print(f" - [HTTP {resp.status_code}] Failed to fetch page {page} for '{endpoint}': {resp.text[:200]}")
    except Exception as e:
        print(f" - [Connection Error] Error fetching page {page} for '{endpoint}': {e}")
    return [], 0, 0


def trash_post(endpoint: str, post_id: int, headers: dict, force: bool = False):
    """Deletes or trashes a post in WordPress."""
    url = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{endpoint}/{post_id}"
    params = {"force": "true" if force else "false"}
    try:
        resp = requests.delete(url, params=params, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, timeout=20)
        return resp.status_code in (200, 202, 204)
    except Exception as e:
        print(f"   [Error] Failed to trash post ID {post_id}: {e}")
        return False


def run_cleanup(batch_limit: int = 500, dry_run: bool = False, force_delete: bool = False):
    print("=" * 65)
    print("LINKSPRIG WORDPRESS DUPLICATE POST CLEANUP ENGINE")
    print(f"Batch Limit : {batch_limit} posts per run")
    print(f"Dry Run     : {'YES (Preview mode - no deletions)' if dry_run else 'NO (Live deletion/trashing)'}")
    print(f"Permanent   : {'YES (Force Delete)' if force_delete else 'NO (Move to Trash)'}")
    print("=" * 65)

    headers = get_auth_headers()
    state = load_state()

    if state.get("finished", False):
        print("\n[INFO] State indicates previous cleanup run completed all post types.")
        print("[INFO] Resetting checkpoint to start a fresh verification cycle.")
        state["current_endpoint_idx"] = 0
        state["current_page"] = 1
        state["last_processed_id"] = 0
        state["finished"] = False

    endpoint_idx = state.get("current_endpoint_idx", 0)
    current_page = state.get("current_page", 1)

    print(f"[RESUME] Resuming from endpoint '{POST_TYPES[endpoint_idx]}' at page {current_page} (Last ID: {state.get('last_processed_id', 0)})")
    print(f"[STATS] All-time cleaned so far: {state.get('total_duplicates_cleaned', 0)} duplicate posts.")

    examined_in_batch = 0
    cleaned_in_batch = 0
    start_time = time.time()

    # Pre-build slug lookup cache for exact matching across active posts
    slug_to_canonical = {}

    while endpoint_idx < len(POST_TYPES) and examined_in_batch < batch_limit:
        endpoint = POST_TYPES[endpoint_idx]
        print(f"\n---> Scanning endpoint: [{endpoint.upper()}] (Page {current_page})")

        posts, total_pages, total_in_endpoint = fetch_posts_page(endpoint, current_page, headers)

        if not posts:
            print(f" - [Notice] No posts returned for '{endpoint}' on page {current_page}. Moving to next endpoint.")
            endpoint_idx += 1
            current_page = 1
            state["current_endpoint_idx"] = endpoint_idx
            state["current_page"] = current_page
            save_state(state)
            continue

        print(f" - Retrieved {len(posts)} posts (Page {current_page}/{total_pages} | Total in endpoint: {total_in_endpoint})")

        for post in posts:
            post_id = post.get("id")
            post_slug = str(post.get("slug", "")).strip()
            post_title = post.get("title", {}).get("rendered", "") if isinstance(post.get("title"), dict) else str(post.get("title", ""))
            post_status = post.get("status", "")

            # Count towards the 500 post batch limit
            examined_in_batch += 1
            state["total_posts_examined"] = state.get("total_posts_examined", 0) + 1
            state["last_processed_id"] = post_id

            base_slug, is_numbered_duplicate = extract_base_slug(post_slug)

            # Detect duplicate condition:
            # 1. Numbered duplicate (e.g. slug-2, slug-3) where base slug is already known or exists
            # 2. Or two posts having the identical slug within the same endpoint
            is_duplicate = False
            duplicate_reason = ""

            if is_numbered_duplicate:
                is_duplicate = True
                duplicate_reason = f"Numbered duplicate slug '{post_slug}' of base '{base_slug}'"
            elif post_slug in slug_to_canonical:
                is_duplicate = True
                orig_id = slug_to_canonical[post_slug]["id"]
                duplicate_reason = f"Duplicate slug collision '{post_slug}' (Original ID: {orig_id})"
            else:
                slug_to_canonical[post_slug] = {
                    "id": post_id,
                    "title": post_title,
                    "status": post_status
                }

            if is_duplicate:
                cleaned_in_batch += 1
                state["total_duplicates_cleaned"] = state.get("total_duplicates_cleaned", 0) + 1
                state.setdefault("cleaned_ids", []).append(post_id)

                print(f"   [DUPLICATE DETECTED] ID {post_id} | Status: {post_status.upper()} | Slug: '{post_slug}'")
                print(f"      Reason: {duplicate_reason} | Title: '{post_title[:60]}'")

                if not dry_run:
                    action = "Permanently deleting" if force_delete else "Moving to Trash"
                    print(f"      --> {action} post ID {post_id}...")
                    success = trash_post(endpoint, post_id, headers, force=force_delete)
                    if success:
                        print(f"      [OK] Post ID {post_id} cleaned.")
                    else:
                        print(f"      [FAILED] Could not trash post ID {post_id}.")
                else:
                    print(f"      [DRY RUN] Would delete/trash post ID {post_id}.")

            if examined_in_batch >= batch_limit:
                print(f"\n[LIMIT REACHED] Hit batch limit of {batch_limit} examined posts.")
                break

        # Advance pagination or move to next endpoint
        if examined_in_batch < batch_limit:
            if current_page < total_pages:
                current_page += 1
                state["current_page"] = current_page
            else:
                endpoint_idx += 1
                current_page = 1
                state["current_endpoint_idx"] = endpoint_idx
                state["current_page"] = current_page

        save_state(state)

    if endpoint_idx >= len(POST_TYPES):
        state["finished"] = True
        save_state(state)
        print("\n" + "=" * 65)
        print("CLEANUP ENGINE COMPLETED: All post types and endpoints scanned!")
        print("=" * 65)
    else:
        print("\n" + "=" * 65)
        print(f"BATCH FINISHED ({examined_in_batch}/{batch_limit} posts examined in this run).")
        print(f"Duplicates removed this run : {cleaned_in_batch}")
        print(f"Total duplicates removed    : {state.get('total_duplicates_cleaned', 0)}")
        print(f"Next run will resume from   : Endpoint '{POST_TYPES[state['current_endpoint_idx']]}' at page {state['current_page']}")
        print("=" * 65)
        print("To clean the next 500 posts, simply run this script again:")
        print("  python cleanup_wp_duplicates.py")
        print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="LinkSprig WordPress Duplicate Post Cleaner (500 per batch with resume support)")
    parser.add_argument("--batch-size", type=int, default=500, help="Number of posts to examine per run (default: 500)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without actually deleting/trashing posts")
    parser.add_argument("--force", action="store_true", help="Permanently delete posts instead of moving them to trash")
    parser.add_argument("--reset", action="store_true", help="Reset state and start from the beginning")
    args = parser.parse_args()

    if args.reset:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
            print("[INFO] Cleanup state has been reset.")

    run_cleanup(batch_limit=args.batch_size, dry_run=args.dry_run, force_delete=args.force)


if __name__ == "__main__":
    main()

import os
import sys
import csv
import json
import requests
import pandas as pd
from dotenv import load_dotenv

# Ensure the script's directory is in python path for local imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from ai_writer import AIWriter
from internal_linker import InternalLinker
from qa_validator import QAValidator

# Load environment
# Try loading .env from current directory first, then from parent directory as fallback
if os.path.exists(os.path.join(SCRIPT_DIR, ".env")):
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
else:
    load_dotenv()

# Constants
EXPORT_MODE = os.getenv("EXPORT_MODE", "csv").lower()
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()
RUN_QA_VALIDATOR = os.getenv("RUN_QA_VALIDATOR", "True").lower() == "true"
DAILY_PAGES_GOAL = int(os.getenv("DAILY_PAGES_GOAL", "50"))

def get_pexels_image_url(query):
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return None
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": 1,
        "orientation": "landscape"
    }
    try:
        print(f" - [Pexels] Searching for stock image: '{query}'...")
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            photos = data.get("photos", [])
            if photos:
                img_url = photos[0]["src"]["large"]
                print(f" - [Pexels] Found image URL: {img_url}")
                return img_url
            else:
                print(f" - [Pexels] No images found for query: '{query}'")
        else:
            print(f" - [Pexels] Failed to search: {response.status_code} - {response.text}")
    except Exception as e:
        print(f" - [Pexels Warning] Error calling Pexels API: {e}")
    return None

def upload_media_to_wp(image_path, wp_url, auth_user, auth_password):
    """Uploads a local image file or a remote image URL to WordPress Media Library and returns (media_id, media_url)."""
    is_url = str(image_path).startswith("http://") or str(image_path).startswith("https://")
    
    if not is_url and not os.path.exists(image_path):
        return None, None
    
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
    
    import base64
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
                return None, None
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
            res_json = response.json()
            media_id = res_json.get("id")
            media_url = res_json.get("source_url")
            print(f" - [Media] Successfully uploaded featured image '{filename}' (ID: {media_id})")
            return media_id, media_url
        else:
            print(f" - [Warning] Media upload failed for '{filename}': {response.status_code} - {response.text}")
    except Exception as e:
        print(f" - [Warning] Error uploading media: {e}")
        
    return None, None

class PSEOEngine:
    def __init__(self):
        self.db_dir = os.path.join(SCRIPT_DIR, "database")
        self.output_dir = os.path.join(SCRIPT_DIR, "output")
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.writer = AIWriter()
        self.linker = InternalLinker()
        self.validator = QAValidator()
        
        # Load historical intros to prevent duplication
        self.intro_history_file = os.path.join(self.output_dir, "intro_history.txt")
        if os.path.exists(self.intro_history_file):
            with open(self.intro_history_file, "r", encoding="utf-8") as f:
                for line in f:
                    self.validator.add_historical_intro(line.strip())

        # Load generated registry to skip already generated pages
        self.registry_file = os.path.join(self.output_dir, "generated_registry.json")
        self.generated_slugs = set()
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self.generated_slugs = set(json.load(f))
            except Exception as e:
                print(f"[WARNING] Failed to load registry file: {e}")
        elif os.path.exists(self.intro_history_file):
            self.seed_registry_from_history()

    def save_registry(self):
        try:
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(list(self.generated_slugs), f, indent=2)
        except Exception as e:
            print(f"[WARNING] Failed to save registry file: {e}")

    def seed_registry_from_history(self):
        print("[INFO] Seeding generated_registry.json from intro_history.txt...")
        try:
            with open(self.intro_history_file, "r", encoding="utf-8") as f:
                history_content = f.read().lower()
            
            competitors, industries, use_cases, problems, guides = self.load_local_csvs()
            
            # Check competitors
            for _, row in competitors.iterrows():
                name = str(row['competitor']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/compare/{self.clean_slug(row['competitor'])}-vs-petalrank")
                    
            # Check industries
            for _, row in industries.iterrows():
                name = str(row['industry']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/industry/search-visibility-for-{self.clean_slug(row['industry'])}")
                    
            # Check problems
            for _, row in problems.iterrows():
                name = str(row['issue']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/problem/how-to-solve-{self.clean_slug(row['issue'])}")
                    
            # Check use cases
            for _, row in use_cases.iterrows():
                name = str(row['use_case']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/use-case/{self.clean_slug(row['use_case'])}-tool")
                    
            # Check guides
            for _, row in guides.iterrows():
                name = str(row['guide']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/guides/{self.clean_slug(row['guide'])}")
            
            self.save_registry()
            print(f"[SUCCESS] Registry seeded with {len(self.generated_slugs)} previously generated slugs.")
        except Exception as e:
            print(f"[WARNING] Failed to seed registry: {e}")

    def load_local_csvs(self):
        """Load entity databases from local CSV files."""
        print(f"[INFO] Loading database tables from local CSV files at {self.db_dir}...")
        
        competitors = pd.read_csv(os.path.join(self.db_dir, "competitors.csv"))
        industries = pd.read_csv(os.path.join(self.db_dir, "industries.csv"))
        use_cases = pd.read_csv(os.path.join(self.db_dir, "use_cases.csv"))
        problems = pd.read_csv(os.path.join(self.db_dir, "problems.csv"))
        guides = pd.read_csv(os.path.join(self.db_dir, "guides.csv"))
        
        return competitors, industries, use_cases, problems, guides

    def build_page_entities(self, count_per_type=10):
        """Combine entities into distinct page definitions for generation."""
        competitors, industries, use_cases, problems, guides = self.load_local_csvs()
        
        generation_list = []
        
        # 1. Compare pages
        compare_added = 0
        for i, row in competitors.iterrows():
            slug = f"/compare/{self.clean_slug(row['competitor'])}-vs-petalrank"
            if slug in self.generated_slugs:
                continue
            generation_list.append({
                "post_type": "compare",
                "slug": slug,
                "entity": row["competitor"],
                "data": row.to_dict()
            })
            compare_added += 1
            if compare_added >= count_per_type:
                break
            
        # 2. Industry pages
        industry_added = 0
        for i, row in industries.iterrows():
            slug = f"/industry/search-visibility-for-{self.clean_slug(row['industry'])}"
            if slug in self.generated_slugs:
                continue
            generation_list.append({
                "post_type": "industry",
                "slug": slug,
                "entity": row["industry"],
                "data": row.to_dict()
            })
            industry_added += 1
            if industry_added >= count_per_type:
                break
            
        # 3. Problem pages
        problem_added = 0
        for i, row in problems.iterrows():
            slug = f"/problem/how-to-solve-{self.clean_slug(row['issue'])}"
            if slug in self.generated_slugs:
                continue
            generation_list.append({
                "post_type": "problem",
                "slug": slug,
                "entity": row["issue"],
                "data": row.to_dict()
            })
            problem_added += 1
            if problem_added >= count_per_type:
                break
            
        # 4. Use Case pages
        use_case_added = 0
        for i, row in use_cases.iterrows():
            slug = f"/use-case/{self.clean_slug(row['use_case'])}-tool"
            if slug in self.generated_slugs:
                continue
            generation_list.append({
                "post_type": "use_case",
                "slug": slug,
                "entity": row["use_case"],
                "data": row.to_dict()
            })
            use_case_added += 1
            if use_case_added >= count_per_type:
                break
            
        # 5. Guide pages
        guide_added = 0
        for i, row in guides.iterrows():
            slug = f"/guides/{self.clean_slug(row['guide'])}"
            if slug in self.generated_slugs:
                continue
            generation_list.append({
                "post_type": "guide",
                "slug": slug,
                "entity": row["guide"],
                "data": row.to_dict()
            })
            guide_added += 1
            if guide_added >= count_per_type:
                break
            
        return generation_list

    def clean_slug(self, text):
        import re
        text = str(text).lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'[\s-]+', '-', text)
        return text.strip('-')

    def run_pipeline(self):
        """Main execution flow for generating the daily batch of articles."""
        print("="*60)
        print("STARTING PETALRANK pSEO GENERATION PIPELINE")
        print("="*60)
        
        # Prepare targets (10 pages per CPT, total 50)
        pages_to_generate = self.build_page_entities(count_per_type=DAILY_PAGES_GOAL // 5)
        
        print(f"[INFO] Prepared {len(pages_to_generate)} target pages for generation.")
        
        # Register targets in the internal linker registry
        self.linker.update_registered_pages([
            {"post_type": p["post_type"], "slug": p["slug"], "title": p["entity"], "entity": p["entity"]}
            for p in pages_to_generate
        ])
        
        generated_pages = []
        rejected_count = 0
        
        for idx, page in enumerate(pages_to_generate):
            post_type = page["post_type"]
            entity = page["entity"]
            entity_data = page["data"]
            
            print(f"\n[Generating {idx+1}/{len(pages_to_generate)}] Type: {post_type.upper()} | Entity: {entity}")
            
            # 1. AI Content Generation
            raw_draft = self.writer.generate_content(post_type, entity_data)
            
            # 2. Run QA Checks
            is_valid = True
            reasons = []
            if RUN_QA_VALIDATOR:
                # Send competitor data for validation if comparing
                comp_data = entity_data if post_type == "compare" else None
                is_valid, reasons = self.validator.validate_page(post_type, raw_draft, comp_data)
                
            if not is_valid:
                print(f"[REJECTED] {post_type.upper()} '{entity}' failed QA checks:")
                for r in reasons:
                    print(f" - {r}")
                rejected_count += 1
                continue
                
            # 3. Add to validation history
            self.validator.add_historical_intro(raw_draft["intro"])
            
            # Keep in buffer for batch internal linking resolution
            page["draft"] = raw_draft
            generated_pages.append(page)
            
        print("\n" + "="*40)
        print(f"BATCH GENERATION COMPLETE: {len(generated_pages)} passed, {rejected_count} rejected.")
        print("="*40)
        
        if not generated_pages:
            print("[INFO] No pages passed generation/QA steps. Exiting pipeline.")
            return

        # 4. Resolve Internal Links for all passed pages
        print("[INFO] Injecting internal links...")
        final_pages = []
        for page in generated_pages:
            draft = page["draft"]
            injected_sections, links_count = self.linker.inject_links(page["post_type"], draft["body_sections"])
            draft["body_sections"] = injected_sections
            draft["internal_links_count"] = links_count
            final_pages.append(draft)
            
            # Record intro in file to persist history
            with open(self.intro_history_file, "a", encoding="utf-8") as f:
                f.write(draft["intro"].replace('\n', ' ') + "\n")
                
        # 5. Export Output
        success_slugs = set()
        if EXPORT_MODE in ["csv", "both"]:
            self.export_to_csv(final_pages, generated_pages)
            if EXPORT_MODE == "csv":
                success_slugs = {page["slug"] for page in generated_pages}
            
        if EXPORT_MODE in ["wp_api", "both"]:
            pushed_slugs = self.push_to_wordpress_api(final_pages, generated_pages)
            if EXPORT_MODE == "wp_api":
                success_slugs = pushed_slugs
            else: # EXPORT_MODE == "both"
                success_slugs = pushed_slugs

        if success_slugs:
            for slug in success_slugs:
                self.generated_slugs.add(slug)
            self.save_registry()
            
        print("[SUCCESS] Pipeline execution finished.")

    def export_to_csv(self, final_pages, original_pages):
        """Export generated content to a CSV file structure ready for WP All Import."""
        csv_file = os.path.join(self.output_dir, "pseo_export_batch.csv")
        print(f"[INFO] Exporting content to CSV: {csv_file}")
        
        rows = []
        for idx, page in enumerate(final_pages):
            orig_page = original_pages[idx]
            post_type = orig_page["post_type"]
            
            # Flatten body sections into standard HTML content
            content_html = page["intro"]
            for sec in page["body_sections"]:
                content_html += f"\n\n<h3>{sec['heading']}</h3>\n{sec['content']}"
            
            # Format FAQs as HTML block
            faq_html = "\n\n<h3>Frequently Asked Questions</h3>\n<dl>"
            for faq in page["faqs"]:
                faq_html += f"\n  <dt><strong>{faq['question']}</strong></dt>\n  <dd>{faq['answer']}</dd>"
            faq_html += "\n</dl>"
            content_html += faq_html
            
            # Format JSON-LD schema
            schema_str = json.dumps(page["schema_json"])
            
            # Flatten ACF field groups
            acf = page["acf_fields"]
            
            row = {
                "post_title": page["title"],
                "post_slug": page["slug"],
                "post_content": content_html,
                "post_status": "draft",
                "post_type": post_type,
                "meta_title": page["meta_title"],
                "meta_description": page["meta_description"],
                "schema_json": schema_str,
                "internal_links_count": page.get("internal_links_count", 0),
                
                # Compare fields
                "competitor_name": acf.get("competitor_name", ""),
                "competitor_strength": acf.get("competitor_strength", ""),
                "competitor_weakness": acf.get("competitor_weakness", ""),
                "ideal_user": acf.get("ideal_user", ""),
                "comparison_summary": acf.get("comparison_summary", ""),
                "CTA": acf.get("CTA", ""),
                
                # Industry fields
                "industry_name": acf.get("industry_name", ""),
                "SEO_challenge": acf.get("SEO_challenge", ""),
                "outreach_problem": acf.get("outreach_problem", ""),
                "relevant_feature": acf.get("relevant_feature", ""),
                "success_metric": acf.get("success_metric", ""),
                
                # Problem fields
                "issue": acf.get("issue", ""),
                "why_it_happens": acf.get("why_it_happens", ""),
                "business_impact": acf.get("business_impact", ""),
                "fix": acf.get("fix", ""),
                "PetalRank_solution": acf.get("PetalRank_solution", ""),
                
                # Use case fields
                "use_case_name": acf.get("use_case_name", ""),
                "why_it_matters": acf.get("why_it_matters", ""),
                "target_audience": acf.get("target_audience", ""),
                "key_workflow": acf.get("key_workflow", ""),
                "benefits": acf.get("benefits", ""),
                
                # Guide fields
                "guide_title": acf.get("guide_title", ""),
                "difficulty_level": acf.get("difficulty_level", ""),
                "time_required": acf.get("time_required", ""),
                "key_takeaways": acf.get("key_takeaways", ""),
                "steps": acf.get("steps", "")
            }
            rows.append(row)
            
        df = pd.DataFrame(rows)
        df.to_csv(csv_file, index=False, encoding="utf-8")
        print(f"[SUCCESS] CSV Export complete. Generated {len(rows)} pages.")

    def push_to_wordpress_api(self, final_pages, original_pages):
        """Pushes drafts directly into WordPress using REST API credentials."""
        if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
            print("[WARNING] WordPress credentials not complete. Skipping direct API push.")
            return set()

        print(f"[INFO] Pushing drafts directly to WordPress REST API at {WP_URL}")
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Workaround for Nginx/Apache stripping the standard 'Authorization' header:
        # Send a duplicate header as 'X-HTTP-Authorization' which is passed by default.
        import base64
        import time
        auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
        b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
        
        pushed_slugs = set()
        
        for idx, page in enumerate(final_pages):
            orig_page = original_pages[idx]
            post_type = orig_page["post_type"]
            slug = orig_page["slug"]
            
            wp_post_type = post_type
            
            focus_keyword = orig_page.get("entity", "")

            # -------------------------------------------------------------------------
            # AUTOMATIC PEXELS STOCK IMAGE INTEGRATION
            # -------------------------------------------------------------------------
            media_id = None
            media_url = None
            if os.getenv("PEXELS_API_KEY"):
                img_url = get_pexels_image_url(focus_keyword or page["title"])
                if img_url:
                    media_id, media_url = upload_media_to_wp(img_url, WP_URL, WP_USER, WP_APP_PASSWORD)
            # -------------------------------------------------------------------------

            intro_content = page["intro"]
            if media_url:
                image_html = f'\n<p><img src="{media_url}" alt="{page["title"]}" class="aligncenter size-full linksprig-featured-image" /></p>\n'
                intro_content = intro_content + image_html

            # Build body content
            content_html = intro_content
            for sec in page["body_sections"]:
                content_html += f"\n\n<h3>{sec['heading']}</h3>\n{sec['content']}"
            
            faq_html = "\n\n<h3>Frequently Asked Questions</h3>\n<dl>"
            for faq in page["faqs"]:
                faq_html += f"\n  <dt><strong>{faq['question']}</strong></dt>\n  <dd>{faq['answer']}</dd>"
            faq_html += "\n</dl>"
            content_html += faq_html
            
            # REST payload
            payload = {
                "title": page["title"],
                "slug": page["slug"],
                "content": content_html,
                "status": WP_POST_STATUS,
                "type": wp_post_type,
                # Custom fields meta mapping
                "meta": {
                    "_rank_math_title": page["meta_title"],
                    "_rank_math_description": page["meta_description"],
                    "schema_json_ld": json.dumps(page["schema_json"]),
                    # ACF custom fields
                    **page["acf_fields"]
                }
            }
            if media_id:
                payload["featured_media"] = media_id
            
            max_retries = 3
            backoff_factor = 2
            success = False
            
            for attempt in range(max_retries):
                try:
                    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_post_type}"
                    response = requests.post(
                        endpoint,
                        json=payload,
                        auth=(WP_USER, WP_APP_PASSWORD),
                        headers=headers,
                        timeout=15
                    )
                    
                    if response.status_code == 201:
                        print(f" - [Success] Draft created: '{page['title']}'")
                        pushed_slugs.add(slug)
                        success = True
                        break
                    elif response.status_code == 404:
                        print(f" - [Error] Failed to create '{page['title']}': 404 - Post type '{wp_post_type}' is not registered on WordPress. Please import custom post types using 'wp-import/cpt-ui-import.json'.")
                        break
                    elif response.status_code == 401:
                        print(f" - [Error] Failed to create '{page['title']}': 401 - Unauthorized. Please ensure WP_USER in .env is your WordPress username (not email) and the Application Password is correct. If the server strips 'Authorization', see instructions to enable the X-HTTP-Authorization workaround.")
                        break
                    else:
                        print(f" - [Error] Failed to create '{page['title']}': {response.status_code} - {response.text}")
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    print(f" - [Attempt {attempt+1}/{max_retries}] Connection/Timeout error for '{page['title']}': {e}")
                except Exception as e:
                    print(f" - [Error] Unexpected exception: {e}")
                    break
                
                if attempt < max_retries - 1:
                    sleep_time = backoff_factor ** attempt
                    print(f"   Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
            
            if not success:
                print(f" - [FAILED] Could not push '{page['title']}' to WordPress after {max_retries} attempts.")
                
        return pushed_slugs

if __name__ == "__main__":
    engine = PSEOEngine()
    engine.run_pipeline()

import os
import csv
import json
import requests
import pandas as pd
from dotenv import load_dotenv
from ai_writer import AIWriter
from internal_linker import InternalLinker
from qa_validator import QAValidator

# Load environment
load_dotenv()

# Constants
EXPORT_MODE = os.getenv("EXPORT_MODE", "csv").lower()
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()
RUN_QA_VALIDATOR = os.getenv("RUN_QA_VALIDATOR", "True").lower() == "true"
DAILY_PAGES_GOAL = int(os.getenv("DAILY_PAGES_GOAL", "50"))

import re

def clean_slug_helper(text):
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
            "slug": clean_slug_helper(canonical_name)
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

class PSEOEngine:
    def __init__(self):
        self.db_dir = "database"
        self.output_dir = "output"
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
                    self.generated_slugs.add(f"/compare/{self.clean_slug(row['competitor'])}-vs-linksprig")
                    
            # Check industries
            for _, row in industries.iterrows():
                name = str(row['industry']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/industry/link-building-software-for-{self.clean_slug(row['industry'])}")
                    
            # Check problems
            for _, row in problems.iterrows():
                name = str(row['issue']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/problem/how-to-fix-{self.clean_slug(row['issue'])}")
                    
            # Check use cases
            for _, row in use_cases.iterrows():
                name = str(row['use_case']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/use-case/{self.clean_slug(row['use_case'])}-outreach-tool")
                    
            # Check guides
            for _, row in guides.iterrows():
                name = str(row['guide']).lower()
                if name in history_content:
                    self.generated_slugs.add(f"/guides/{self.clean_slug(row['guide'])}")
            
            self.save_registry()
            print(f"[SUCCESS] Registry seeded with {len(self.generated_slugs)} previously generated slugs.")
        except Exception as e:
            print(f"[WARNING] Failed to seed registry: {e}")

    def pull_google_sheet_rows(self, spreadsheet_id, credentials_path=None):
        """
        Reference function for pulling from Google Sheets.
        To use this in production:
        1. Install gspread: pip install gspread oauth2client
        2. Set up service account credentials and pass the JSON path.
        """
        print("[INFO] Pulling rows from Google Sheets...")
        try:
            import gspread
            from oauth2client.service_account import ServiceAccountCredentials
            
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_path, scope)
            client = gspread.authorize(creds)
            sheet = client.open_by_key(spreadsheet_id)
            
            # Example load
            competitors = pd.DataFrame(sheet.worksheet("competitors").get_all_records())
            industries = pd.DataFrame(sheet.worksheet("industries").get_all_records())
            use_cases = pd.DataFrame(sheet.worksheet("use_cases").get_all_records())
            problems = pd.DataFrame(sheet.worksheet("problems").get_all_records())
            guides = pd.DataFrame(sheet.worksheet("guides").get_all_records())
            
            return competitors, industries, use_cases, problems, guides
        except ImportError:
            print("[WARNING] gspread/oauth2client not installed. Using local CSVs instead.")
            return self.load_local_csvs()
        except Exception as e:
            print(f"[ERROR] Failed to load Google Sheet: {e}. Using local CSVs.")
            return self.load_local_csvs()

    def load_local_csvs(self):
        """Load entity databases from local CSV files."""
        print("[INFO] Loading database tables from local CSV files...")
        
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
            slug = f"/compare/{self.clean_slug(row['competitor'])}-vs-linksprig"
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
            slug = f"/industry/link-building-software-for-{self.clean_slug(row['industry'])}"
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
            slug = f"/problem/how-to-fix-{self.clean_slug(row['issue'])}"
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
            slug = f"/use-case/{self.clean_slug(row['use_case'])}-outreach-tool"
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
        print("STARTING LINKSPRIG pSEO GENERATION PIPELINE")
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
                success_slugs = {page["slug"] for page in original_pages}
            
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
                "category": page.get("category", ""),
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
                "LinkSprig_solution": acf.get("LinkSprig_solution", ""),
                
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
            
            # Map CPTs to WordPress custom type slugs if different
            # Make sure these match custom post types created in WP (compare, industry, problem, use_case, guide)
            wp_post_type = post_type
            
            # Build body content
            content_html = page["intro"]
            for sec in page["body_sections"]:
                content_html += f"\n\n<h3>{sec['heading']}</h3>\n{sec['content']}"
            
            faq_html = "\n\n<h3>Frequently Asked Questions</h3>\n<dl>"
            for faq in page["faqs"]:
                faq_html += f"\n  <dt><strong>{faq['question']}</strong></dt>\n  <dd>{faq['answer']}</dd>"
            faq_html += "\n</dl>"
            content_html += faq_html
            
            cat_name = page.get("category", "")
            cat_id = get_wp_category_id(cat_name, WP_URL, WP_USER, WP_APP_PASSWORD) if cat_name else None
            
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
            if cat_id:
                payload["categories"] = [cat_id]
            
            max_retries = 3
            backoff_factor = 2
            success = False
            
            wp_endpoint = "posts" if wp_post_type == "post" else wp_post_type
            
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

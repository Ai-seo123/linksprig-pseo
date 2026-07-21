import os
import csv
import json
import base64
import requests
import time
import random
from io import BytesIO
import pandas as pd
from dotenv import load_dotenv
from ai_writer import AIWriter
from internal_linker import InternalLinker
from qa_validator import QAValidator
from formatter import format_blog_html
from PIL import Image as PILImage

load_dotenv()

# Constants
EXPORT_MODE = os.getenv("EXPORT_MODE", "csv").lower()
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
WP_POST_STATUS = os.getenv("WP_POST_STATUS", "draft").lower()
RUN_QA_VALIDATOR = os.getenv("RUN_QA_VALIDATOR", "True").lower() == "true"
DAILY_PAGES_GOAL = int(os.getenv("DAILY_PAGES_GOAL", "50"))

import re
import db_helper

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
            "slug": clean_slug_helper(canonical_name)
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
    Sweeps the entire title context, filters out abstract and technical stop words,
    and appends face-only meeting room parameters.
    """
    clean_title = re.sub(r'[^a-zA-Z0-9\s]', ' ', title).lower()
    words = clean_title.split()
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'to', 'of', 'for', 'with', 'on', 'at', 'by', 'from', 'about', 'how', 'why', 'what', 'who',
        'when', 'where', 'which', 'your', 'my', 'his', 'her', 'their', 'our', 'its', 'in', 'into',
        'as', 'than', 'then', 'that', 'this', 'these', 'those', 'it', 'us', 'you', 'me', 'them',
        'vs', 'versus', 'linksprig', 'software', 'tool', 'platform', 'api', 'mongodb', 'excel', 
        'csv', 'xlsx', 'json', 'cpt', 'gutenberg', 'html', 'css', 'style', 'code', 'coding', 'script',
        'contact', 'scrabble', 'tiles', 'alphabet', 'letters', 'wood', 'wooden', 'keyboard', 'laptop',
        'phone', 'screen', 'hands', 'writing', 'desk', 'b2b', 'saas', 'linkedin', 'seo'
    }
    keywords = [w for w in words if w not in stop_words and len(w) > 2]
    if len(keywords) < 2:
        keywords = [w for w in words if len(w) > 3]
    base_keywords = " ".join(keywords[:3])
    
    # Strict "professional human faces" boardroom conversation setting
    return f"{base_keywords} professional business people faces discussing in meeting room"

def solve_dynamically_via_pexels(search_query):
    """
    Queries Pexels using max-pool sizes of 80 to ensure rich variety,
    consulting a JSON registry to guarantee no image is ever repeated.
    """
    if not PEXELS_API_KEY:
        return None
        
    # Track previously downloaded image IDs across scripts
    used_images_file = "used_pexels_images.json"
    used_ids = set()
    if os.path.exists(used_images_file):
        try:
            with open(used_images_file, "r") as f:
                used_ids = set(json.load(f))
        except Exception:
            used_ids = set()
            
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": search_query, 
        "per_page": 80, # Maximized pool size to ensure deduplication succeeds
        "orientation": "landscape"
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=25)
        if response.status_code == 200:
            data = response.json()
            photos = data.get("photos", [])
            
            # Select only images that haven't been used on other posts yet
            fresh_photos = [p for p in photos if p["id"] not in used_ids]
            
            if fresh_photos:
                selected_photo = random.choice(fresh_photos)
                photo_id = selected_photo["id"]
                image_url = selected_photo["src"]["large2x"]
                print(f" - [Pexels] Selected fresh, unique image ID {photo_id} by: {selected_photo['photographer']}")
                
                # Download bytes
                img_resp = requests.get(image_url, timeout=40)
                if img_resp.status_code == 200:
                    # Update tracking database
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
    except Exception as e:
        print(f" - [Pexels Warning] Failed to fetch unique image: {e}")
    return None

def process_clean_landscape_banner(img, target_size=(1704, 923)):
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
    except Exception as e:
        print(f" - [Media Error] WordPress Upload Exception: {e}")
    return None, None

class PSEOEngine:
    def __init__(self):
        self.db_dir = "database"
        self.output_dir = "output"
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.writer = AIWriter()
        self.linker = InternalLinker()
        self.validator = QAValidator()
        
        self.intro_history_file = os.path.join(self.output_dir, "intro_history.txt")
        if os.path.exists(self.intro_history_file):
            with open(self.intro_history_file, "r", encoding="utf-8") as f:
                for line in f:
                    self.validator.add_historical_intro(line.strip())

        self.registry_file = os.path.join(self.output_dir, "generated_registry.json")
        self.generated_slugs = set()
        try:
            self.generated_slugs = db_helper.get_all_registered_slugs()
        except Exception as e:
            print(f"[WARNING] Failed to load registry from DB: {e}")

    def load_local_csvs(self):
        print("[INFO] Loading database tables from local CSV files...")
        competitors = pd.read_csv(os.path.join(self.db_dir, "competitors.csv"))
        industries = pd.read_csv(os.path.join(self.db_dir, "industries.csv"))
        use_cases = pd.read_csv(os.path.join(self.db_dir, "use_cases.csv"))
        problems = pd.read_csv(os.path.join(self.db_dir, "problems.csv"))
        guides = pd.read_csv(os.path.join(self.db_dir, "guides.csv"))
        return competitors, industries, use_cases, problems, guides

    def build_page_entities(self, count_per_type=10):
        competitors, industries, use_cases, problems, guides = self.load_local_csvs()
        generation_list = []
        
        # 1. Compare pages
        compare_added = 0
        for i, row in competitors.iterrows():
            slug = f"/compare/{self.clean_slug(row['competitor'])}-vs-linksprig"
            if slug in self.generated_slugs: continue
            generation_list.append({"post_type": "compare", "slug": slug, "entity": row["competitor"], "data": row.to_dict()})
            compare_added += 1
            if compare_added >= count_per_type: break
            
        # 2. Industry pages
        industry_added = 0
        for i, row in industries.iterrows():
            slug = f"/industry/link-building-software-for-{self.clean_slug(row['industry'])}"
            if slug in self.generated_slugs: continue
            generation_list.append({"post_type": "industry", "slug": slug, "entity": row["industry"], "data": row.to_dict()})
            industry_added += 1
            if industry_added >= count_per_type: break
            
        # 3. Problem pages
        problem_added = 0
        for i, row in problems.iterrows():
            slug = f"/problem/how-to-fix-{self.clean_slug(row['issue'])}"
            if slug in self.generated_slugs: continue
            generation_list.append({"post_type": "problem", "slug": slug, "entity": row["issue"], "data": row.to_dict()})
            problem_added += 1
            if problem_added >= count_per_type: break
            
        # 4. Use Case pages
        use_case_added = 0
        for i, row in use_cases.iterrows():
            slug = f"/use-case/{self.clean_slug(row['use_case'])}-outreach-tool"
            if slug in self.generated_slugs: continue
            generation_list.append({"post_type": "use_case", "slug": slug, "entity": row["use_case"], "data": row.to_dict()})
            use_case_added += 1
            if use_case_added >= count_per_type: break
            
        # 5. Guide pages
        guide_added = 0
        for i, row in guides.iterrows():
            slug = f"/guides/{self.clean_slug(row['guide'])}"
            if slug in self.generated_slugs: continue
            generation_list.append({"post_type": "guide", "slug": slug, "entity": row["guide"], "data": row.to_dict()})
            guide_added += 1
            if guide_added >= count_per_type: break
            
        return generation_list

    def clean_slug(self, text):
        text = str(text).lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'[\s-]+', '-', text)
        return text.strip('-')

    def run_pipeline(self):
        print("="*60)
        print("STARTING LINKSPRIG pSEO GENERATION PIPELINE WITH DYNAMIC IMAGES")
        print("="*60)
        
        pages_to_generate = self.build_page_entities(count_per_type=DAILY_PAGES_GOAL // 5)
        print(f"[INFO] Prepared {len(pages_to_generate)} target pages for generation.")
        
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
            
            raw_draft = self.writer.generate_content(post_type, entity_data)
            
            is_valid = True
            reasons = []
            if RUN_QA_VALIDATOR:
                comp_data = entity_data if post_type == "compare" else None
                is_valid, reasons = self.validator.validate_page(post_type, raw_draft, comp_data)
                
            if not is_valid:
                print(f"[REJECTED] {post_type.upper()} '{entity}' failed QA checks:")
                for r in reasons: print(f" - {r}")
                rejected_count += 1
                continue
                
            self.validator.add_historical_intro(raw_draft["intro"])
            page["draft"] = raw_draft
            generated_pages.append(page)
            
        print("\n" + "="*40)
        print(f"BATCH GENERATION COMPLETE: {len(generated_pages)} passed, {rejected_count} rejected.")
        print("="*40)
        
        print("[INFO] Injecting internal links...")
        final_pages = []
        for page in generated_pages:
            draft = page["draft"]
            injected_sections, links_count = self.linker.inject_links(page["post_type"], draft["body_sections"])
            draft["body_sections"] = injected_sections
            draft["internal_links_count"] = links_count
            final_pages.append(draft)
            
            with open(self.intro_history_file, "a", encoding="utf-8") as f:
                f.write(draft["intro"].replace('\n', ' ') + "\n")
                
        success_slugs = set()
        if EXPORT_MODE in ["csv", "both"]:
            self.export_to_csv(final_pages, generated_pages)
            if EXPORT_MODE == "csv":
                success_slugs = {page["slug"] for page in generated_pages}
            
        if EXPORT_MODE in ["wp_api", "both"]:
            pushed_slugs = self.push_to_wordpress_api(final_pages, generated_pages)
            success_slugs = pushed_slugs

        if success_slugs:
            for slug in success_slugs:
                db_helper.register_slug(slug)
            
        print("[SUCCESS] Pipeline execution finished.")

    def export_to_csv(self, final_pages, original_pages):
        csv_file = os.path.join(self.output_dir, "pseo_export_batch.csv")
        print(f"[INFO] Exporting content to CSV: {csv_file}")
        
        rows = []
        for idx, page in enumerate(final_pages):
            orig_page = original_pages[idx]
            post_type = orig_page["post_type"]
            content_html = format_blog_html(title=page["title"], intro_html=page["intro"], body_sections=page["body_sections"], faqs_list=page["faqs"])
            schema_str = json.dumps(page["schema_json"])
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
                "competitor_name": acf.get("competitor_name", ""),
                "competitor_strength": acf.get("competitor_strength", ""),
                "competitor_weakness": acf.get("competitor_weakness", ""),
                "ideal_user": acf.get("ideal_user", ""),
                "comparison_summary": acf.get("comparison_summary", ""),
                "CTA": acf.get("CTA", ""),
                "industry_name": acf.get("industry_name", ""),
                "SEO_challenge": acf.get("SEO_challenge", ""),
                "outreach_problem": acf.get("outreach_problem", ""),
                "relevant_feature": acf.get("relevant_feature", ""),
                "success_metric": acf.get("success_metric", ""),
                "issue": acf.get("issue", ""),
                "why_it_happens": acf.get("why_it_happens", ""),
                "business_impact": acf.get("business_impact", ""),
                "fix": acf.get("fix", ""),
                "LinkSprig_solution": acf.get("LinkSprig_solution", ""),
                "use_case_name": acf.get("use_case_name", ""),
                "why_it_matters": acf.get("why_it_matters", ""),
                "target_audience": acf.get("target_audience", ""),
                "key_workflow": acf.get("key_workflow", ""),
                "benefits": acf.get("benefits", ""),
                "guide_title": acf.get("guide_title", ""),
                "difficulty_level": acf.get("difficulty_level", ""),
                "time_required": acf.get("time_required", ""),
                "key_takeaways": acf.get("key_takeaways", ""),
                "steps": acf.get("steps", "")
            }
            rows.append(row)
            
        df = pd.DataFrame(rows)
        # Apply physical year safe filter across database rows as well
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].apply(lambda x: hard_upgrade_years_safety_net(x) if isinstance(x, str) else x)
                
        df.to_csv(csv_file, index=False, encoding="utf-8")
        print(f"[SUCCESS] CSV Export complete. Generated {len(rows)} pages.")

    def push_to_wordpress_api(self, final_pages, original_pages):
        if not WP_URL or not WP_USER or not WP_APP_PASSWORD:
            print("[WARNING] WordPress credentials not complete. Skipping direct API push.")
            return set()

        print(f"[INFO] Pushing drafts directly to WordPress REST API at {WP_URL}")
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        auth_str = f"{WP_USER}:{WP_APP_PASSWORD}"
        b64_auth = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        headers["X-HTTP-Authorization"] = f"Basic {b64_auth}"
        
        pushed_slugs = set()
        
        for idx, page in enumerate(final_pages):
            orig_page = original_pages[idx]
            post_type = orig_page["post_type"]
            slug = orig_page["slug"]
            wp_post_type = "post" if post_type == "post" else post_type
            
            # Pexels workflow integration for custom landing page types
            print(f" - [Visual Discovery] Extracting search queries for: '{page['title']}'...")
            pexels_query = generate_pexels_query_from_title(page['title'])
            raw_photo = solve_dynamically_via_pexels(pexels_query)
            
            media_id, media_url = None, None
            wp_slug = slug.strip("/").split("/")[-1]
            
            if raw_photo:
                processed_img = process_clean_landscape_banner(raw_photo)
                img_buffer = BytesIO()
                processed_img_rgb = processed_img.convert("RGB")
                processed_img_rgb.save(img_buffer, format="JPEG", quality=98)
                img_buffer.seek(0)
                media_id, media_url = upload_image_to_wordpress(img_buffer, wp_slug)

            # Prepend CSS override to drop WordPress native headers and collapse margins cleanly
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
                "    font-size: 40px !important; /* Exactly 40px visual rendering size */\n"
                "  }\n"
                "</style>\n"
            )

            # Sanitize content year references forcefully using python safetynet before merging
            clean_title = hard_upgrade_years_safety_net(page["title"])
            clean_meta_title = hard_upgrade_years_safety_net(page["meta_title"])
            clean_meta_desc = hard_upgrade_years_safety_net(page["meta_description"])
            clean_intro = hard_upgrade_years_safety_net(page["intro"])
            
            # Format main body contents
            content_html = format_blog_html(title=clean_title, intro_html=clean_intro, body_sections=page["body_sections"], faqs_list=page["faqs"])
            content_html = hard_upgrade_years_safety_net(content_html)
            
            final_content = theme_title_remover_css
            final_content += f"<h1 class='linksprig-custom-title'>{clean_title}</h1>\n"
            
            if media_url:
                final_content += f'<p><img src="{media_url}" alt="{clean_title}" class="aligncenter size-full linksprig-featured-banner" width="1704" height="923" /></p>\n'
                
            final_content += content_html
            cat_name = page.get("category", "")
            cat_id = get_wp_category_id(cat_name, WP_URL, WP_USER, WP_APP_PASSWORD) if cat_name else None
            
            # Sanitize ACF fields
            clean_acf = {}
            for k, v in page["acf_fields"].items():
                clean_acf[k] = hard_upgrade_years_safety_net(v)
                
            payload = {
                "title": clean_title,
                "slug": wp_slug,
                "content": final_content,
                "status": WP_POST_STATUS,
                "type": wp_post_type,
                "meta": {
                    "_rank_math_title": clean_meta_title,
                    "_rank_math_description": clean_meta_desc,
                    "schema_json_ld": json.dumps(page["schema_json"]),
                    **clean_acf
                }
            }
            if cat_id: payload["categories"] = [cat_id]
            if media_id: payload["featured_media"] = media_id
            
            max_retries = 3
            backoff_factor = 2
            wp_endpoint = "posts" if wp_post_type == "post" else wp_post_type
            
            for attempt in range(max_retries):
                try:
                    endpoint = f"{WP_URL.rstrip('/')}/wp-json/wp/v2/{wp_endpoint}"
                    response = requests.post(endpoint, json=payload, auth=(WP_USER, WP_APP_PASSWORD), headers=headers, timeout=15)
                    
                    if response.status_code in (200, 201):
                        print(f" - [Success] Draft CPT created: '{clean_title}' with identical featured/hero banner!")
                        pushed_slugs.add(slug)
                        break
                    else:
                        print(f" - [Error] Failed CPT post push: {response.status_code} - {response.text}")
                except Exception as e:
                    print(f" - [Error] Connection failed: {e}")
                time.sleep(backoff_factor ** attempt)
                
        return pushed_slugs

if __name__ == "__main__":
    engine = PSEOEngine()
    engine.run_pipeline()
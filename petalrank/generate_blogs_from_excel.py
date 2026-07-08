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

# Resolve paths relative to the script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment
if os.path.exists(os.path.join(SCRIPT_DIR, ".env")):
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
else:
    load_dotenv()

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

def generate_blog_post(topic, keyword):
    print(f"\n[AI Writing] Topic: {topic} | Focus Keyword: {keyword}")
    
    system_instruction = (
        "You are a premium B2B SaaS content writer specializing in SEO, GEO (Generative Engine Optimization), and search visibility platform optimization for PetalRank (built by Espial Solutions).\n"
        "Your writing style is professional, data-driven, highly tactical (featuring actionable workflows), and authoritative.\n"
        "CRITICAL GUIDELINES:\n"
        "1. Write a complete, comprehensive, and engaging blog post about the topic. The target word count is 800+ words.\n"
        "2. Integrate the focus keyword naturally throughout the text.\n"
        "3. Structure all body sections using clean HTML tags (e.g. <p>, <ul>, <li>, <strong>, <h3>) for rich layouts. Do NOT wrap headings in <h1> or <h2>, start sub-headings with <h3>. You MUST include at least one bulleted (<ul>, <li>) list in the article.\n"
        "4. Include real-world statistics, metrics, or performance numbers using percent symbols (%) or currency symbols ($), and include a reference to a recent year (e.g., 2026) to establish strong EEAT.\n"
        "5. Ensure the output is a fully complete and valid JSON payload according to the schema. Do not output truncated or invalid JSON.\n"
        "6. CRITICAL FOR JSON VALIDITY: Use single quotes for all HTML attributes (e.g. <a href='...'> or <span style='...'>) and avoid raw double quotes inside the text. If you must use double quotes, they MUST be escaped with a backslash (\\\")."
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
        "required": ["title", "meta_title", "meta_description", "slug", "intro", "body_sections", "faqs"]
    }
    
    max_retries = 3
    for attempt in range(max_retries):
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
                    "temperature": 0.7 + (attempt * 0.1),
                    "max_output_tokens": 8192
                }
            )
            
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            result = json.loads(text)
            if not result.get("slug"):
                result["slug"] = clean_slug(topic)
            return result
        except Exception as e:
            print(f" - [Attempt {attempt+1}/{max_retries}] AI generation failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return None

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
    
    # Build content HTML
    content_html = page["intro"]
    for sec in page["body_sections"]:
        content_html += f"\n\n<h3>{sec['heading']}</h3>\n{sec['content']}"
    
    faq_html = "\n\n<h3>Frequently Asked Questions</h3>\n<dl>"
    for faq in page["faqs"]:
        faq_html += f"\n  <dt><strong>{faq['question']}</strong></dt>\n  <dd>{faq['answer']}</dd>"
    faq_html += "\n</dl>"
    content_html += faq_html
    
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
    excel_path = os.getenv("EXCEL_PATH", r"C:\Users\ARNAV\Downloads\PetalRank-Blogs-Topics-Keywords.xlsx")
    registry_path = os.path.join(SCRIPT_DIR, "output", "generated_registry.json")
    csv_output_path = os.path.join(SCRIPT_DIR, "output", "excel_blogs_export.csv")
    
    # Ensure output folder exists
    os.makedirs(os.path.join(SCRIPT_DIR, "output"), exist_ok=True)
    
    if not os.path.exists(excel_path):
        print(f"[ERROR] Excel file not found at: {excel_path}")
        print("Please place your Excel topics sheet at that path or configure the EXCEL_PATH environment variable.")
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
        return
    
    print(f"[INFO] Found {len(df)} topics in Excel sheet.")
    
    # Load registry to skip already generated pages
    generated_slugs = set()
    if os.path.exists(registry_path):
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                generated_slugs = set(json.load(f))
        except Exception as e:
            print(f"[WARNING] Failed to load registry file: {e}")
            
    rows_for_csv = []
    successful_slugs = set()
    
    for idx, row in df.iterrows():
        topic = row["Topics"].strip()
        keyword = str(row["Keyword"]).strip() if "Keyword" in df.columns else ""
        
        # Check if already generated
        slug_check = clean_slug(topic)
        if f"/blog/{slug_check}" in generated_slugs or slug_check in generated_slugs:
            print(f"[{idx+1}/{len(df)}] Skipping already generated topic: {topic}")
            continue
            
        page_data = generate_blog_post(topic, keyword)
        if not page_data:
            print(f" - [FAILED] Skipping '{topic}' due to AI writing error.")
            continue
            
        # Flatten content HTML for CSV export
        content_html = page_data["intro"]
        for sec in page_data["body_sections"]:
            content_html += f"\n\n<h3>{sec['heading']}</h3>\n{sec['content']}"
            
        faq_html = "\n\n<h3>Frequently Asked Questions</h3>\n<dl>"
        for faq in page_data["faqs"]:
            faq_html += f"\n  <dt><strong>{faq['question']}</strong></dt>\n  <dd>{faq['answer']}</dd>"
        faq_html += "\n</dl>"
        content_html += faq_html
        
        csv_row = {
            "post_title": page_data["title"],
            "post_slug": page_data["slug"],
            "post_content": content_html,
            "post_status": "draft",
            "post_type": "post",
            "focus_keyword": keyword,
            "meta_title": page_data["meta_title"],
            "meta_description": page_data["meta_description"]
        }
        rows_for_csv.append(csv_row)
        
        # Upload directly to WordPress
        if EXPORT_MODE in ["wp_api", "both"]:
            success = push_post_to_wordpress(page_data, keyword)
            if success:
                successful_slugs.add(page_data["slug"])
        else:
            # If CSV only, immediately count as success
            successful_slugs.add(page_data["slug"])
            
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
        
    # Update registry with successful uploads
    if successful_slugs:
        for s in successful_slugs:
            generated_slugs.add(s)
        try:
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(list(generated_slugs), f, indent=2)
            print(f"[INFO] Registry updated with {len(successful_slugs)} new uploads.")
        except Exception as e:
            print(f"[WARNING] Failed to save registry: {e}")
            
    print("\n[SUCCESS] Pipeline execution finished.")

if __name__ == "__main__":
    main()

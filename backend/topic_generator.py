import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

# Load workspace .env if present
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(parent_dir, ".env"))

API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

def generate_topics(user_prompt: str) -> list:
    """
    Generate a list of keywords and topics based on the user prompt using Gemini.
    """
    if not API_KEY:
        print("[WARNING] GEMINI_API_KEY not found in environment. Returning mock topics.")
        return get_mock_topics(user_prompt)

    system_instruction = (
        "You are an SEO strategist generating high-impact keyword ideas and blog/landing page topics for a B2B SaaS website called LinkSprig.\n"
        "LinkSprig is a modern link-building outreach automation tool.\n"
        "Your task is to take the user's input/prompt and generate a list of SEO keywords, matching page titles (topics), and categories.\n"
        "Provide at least 5 to 10 distinct keywords and topics that directly answer or expand upon the user's prompt.\n"
        "You MUST categorize each keyword/topic into exactly one of these five canonical categories (case-sensitive, exact match):\n"
        "- Category A — LinkedIn Outreach Strategy\n"
        "- Category B — AI Personalization & Technology\n"
        "- Category C — Role-Specific Outreach Guides\n"
        "- Category D — Message Templates & Copywriting\n"
        "- Category E — Lead Generation & Pipeline Building\n\n"
        "Format the output strictly as a JSON array of objects, where each object has 'keyword', 'topic', and 'category' fields."
    )

    response_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "keyword": {"type": "STRING"},
                "topic": {"type": "STRING"},
                "category": {"type": "STRING"}
            },
            "required": ["keyword", "topic", "category"]
        }
    }

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            system_instruction=system_instruction
        )
        
        response = model.generate_content(
            user_prompt,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": response_schema,
                "temperature": 0.7,
                "max_output_tokens": 4096
            }
        )
        
        return json.loads(response.text)
    except Exception as e:
        print(f"[ERROR] Failed to generate topics via Gemini: {e}")
        return get_mock_topics(user_prompt)

def get_mock_topics(prompt: str) -> list:
    """Fallback mock topics generator"""
    return [
        {
            "keyword": f"linkedin automation {prompt.lower()[:20].strip()}",
            "topic": f"The Ultimate Guide to Safe LinkedIn Automation for {prompt.strip()} in 2026",
            "category": "Category A — LinkedIn Outreach Strategy"
        },
        {
            "keyword": f"ai personalization for {prompt.lower()[:20].strip()}",
            "topic": f"How to Use AI Personalization to Boost Your {prompt.strip()} campaign",
            "category": "Category B — AI Personalization & Technology"
        },
        {
            "keyword": f"link building for {prompt.lower()[:20].strip()}",
            "topic": f"Top Strategy: How to Build Backlinks for {prompt.strip()}",
            "category": "Category E — Lead Generation & Pipeline Building"
        }
    ]

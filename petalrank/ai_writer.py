import warnings
# Suppress google.generativeai and other Future/Deprecation warnings before import
warnings.filterwarnings("ignore")

import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv

# Load env variables
load_dotenv()

# Configure Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)
else:
    print("[WARNING] GEMINI_API_KEY not found in environment. ai_writer.py will run in MOCK mode.")

def clean_slug(text):
    """Generate a clean URL slug from text."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

class AIWriter:
    def __init__(self):
        self.model_name = "gemini-2.5-flash-lite"
        self.use_mock = not bool(API_KEY)

    def generate_content(self, post_type, entity_data):
        """
        Orchestrate prompt assembly and model call for each CPT.
        Returns a dictionary matching the standardized JSON output schema.
        """
        if self.use_mock:
            return self._generate_mock_response(post_type, entity_data)
        
        prompt, system_instruction, response_schema = self._prepare_generation_context(post_type, entity_data)
        
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction
            )
            
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                    "temperature": 0.7,
                    "max_output_tokens": 8192
                }
            )
            
            # Parse and return JSON
            result = json.loads(response.text)
            
            # Ensure slug is generated if missing
            if not result.get("slug"):
                if post_type == "compare":
                    result["slug"] = f"{clean_slug(entity_data['competitor'])}-vs-petalrank"
                elif post_type == "industry":
                    result["slug"] = f"search-visibility-for-{clean_slug(entity_data['industry'])}"
                elif post_type == "problem":
                    result["slug"] = f"how-to-solve-{clean_slug(entity_data['issue'])}"
                elif post_type == "use_case":
                    result["slug"] = f"{clean_slug(entity_data['use_case'])}-tool"
                else:
                    result["slug"] = clean_slug(entity_data['guide'])
            
            return result
            
        except Exception as e:
            print(f"[ERROR] AI generation failed: {e}. Falling back to Mock data.")
            try:
                if 'response' in locals() and hasattr(response, 'text'):
                    print(f"[DEBUG] Raw response: {response.text[:2000]}")
            except Exception as inner_e:
                print(f"[DEBUG] Could not print raw response: {inner_e}")
            return self._generate_mock_response(post_type, entity_data)

    def _prepare_generation_context(self, post_type, entity_data):
        """Prepare specific prompt, system instructions, and schema for the target post type."""
        
        # Base system instruction enforcing the pSEO content guidelines for PetalRank
        system_instruction = (
            "You are a premium SEO copywriter specializing in Product-Led SEO for PetalRank (an AI-powered SEO, GEO, and search visibility platform built by Espial Solutions).\n"
            "Your writing style is professional, data-driven, highly tactical (featuring actionable workflows), and authoritative.\n"
            "CRITICAL GUIDELINES:\n"
            "1. You MUST organically mention these terms at least once in the body sections: 'GEO tracking', 'AI search visibility', 'search landscapes', 'Espial Solutions'.\n"
            "2. Make the content highly differentiated. Avoid generic advice. Give specific step-by-step search optimization and tracking tactics.\n"
            "3. Structure all body sections using clean HTML tags (e.g. <p>, <ul>, <li>, <strong>, <h3>) for rich layouts. Do NOT wrap headings in <h1> or <h2>, start sub-headings with <h3>. You MUST include at least one bulleted (<ul>, <li>) or ordered list in every single page to satisfy readability checks.\n"
            "4. Follow the templates strictly.\n"
            "5. Ensure metadata is compelling for click-through rate (CTR) optimization.\n"
            "6. You MUST include real-world statistics, metrics, or performance numbers using percent symbols (%) or currency symbols ($), and include a reference to a recent year (e.g., 2026) to establish strong EEAT.\n"
            "7. Every single section in body_sections MUST have a minimum of 110 to 130 words of content to avoid thin section rejection and satisfy the 500-word page limit.\n"
            "8. Ensure the output is a fully complete and valid JSON payload according to the schema. Do not output truncated or invalid JSON.\n"
        )
        
        # Define dynamic acf_fields properties based on post_type
        if post_type == "compare":
            acf_keys = ["competitor_name", "competitor_strength", "competitor_weakness", "ideal_user", "comparison_summary", "CTA"]
        elif post_type == "industry":
            acf_keys = ["industry_name", "SEO_challenge", "outreach_problem", "relevant_feature", "success_metric"]
        elif post_type == "problem":
            acf_keys = ["issue", "why_it_happens", "business_impact", "fix", "PetalRank_solution"]
        elif post_type == "use_case":
            acf_keys = ["use_case_name", "why_it_matters", "target_audience", "key_workflow", "benefits"]
        elif post_type == "guide":
            acf_keys = ["guide_title", "difficulty_level", "time_required", "key_takeaways", "steps"]
        else:
            acf_keys = []
            
        if post_type == "compare":
            prompt = f"""
            Generate a detailed comparison page between PetalRank and competitor '{entity_data['competitor']}'.
            Competitor Positioning: {entity_data['positioning']}
            Competitor Target User Type: {entity_data['user_type']}
            
            The body_sections array should cover these 5 detailed sections (do NOT include intro, FAQ, or CTA as they are separate JSON fields):
            1. Why teams compare these tools: Discuss the core problems with {entity_data['competitor']}'s positioning as '{entity_data['positioning']}' for '{entity_data['user_type']}'. Focus on how search has evolved beyond Google to generative/AI search.
            2. Key workflow differences: Highlight how {entity_data['competitor']} lacks real-time tracking across AI search engines, GEO (Generative Engine Optimization), and dynamic search landscapes.
            3. Feature comparison: Present a feature analysis of both tools (pros/cons).
            4. Which tool fits which team: Provide recommendations based on team needs.
            5. Why PetalRank fits better: Highlight search landscape insights, GEO tracking, and the agency experience of Espial Solutions shaping PetalRank.
            
            In the acf_fields output, populate these fields:
            - competitor_name: "{entity_data['competitor']}"
            - competitor_strength: "Detail their strengths based on '{entity_data['positioning']}'"
            - competitor_weakness: "Detail their weaknesses for tracking AI visibility and GEO"
            - ideal_user: "{entity_data['user_type']}"
            - comparison_summary: "A concise 2-sentence summary comparing the two platforms"
            - CTA: "Start monitoring with PetalRank"
            """
            
        elif post_type == "industry":
            prompt = f"""
            Generate a detailed industry-specific search visibility guide for the '{entity_data['industry']}' industry.
            Industry Pain Point: {entity_data['pain']}
            Relevant PetalRank Feature: {entity_data['feature']}
            
            The body_sections array should cover these 5 detailed sections (do NOT include intro, FAQ, or CTA as they are separate JSON fields):
            1. Why organic visibility is harder in this industry: Focus on the pain '{entity_data['pain']}'.
            2. Common search visibility challenge: Discuss specific barriers for {entity_data['industry']} in AI-driven discovery platforms.
            3. Workflow bottlenecks: What slows teams down in tracking keyword and GEO metrics.
            4. PetalRank solution: How the feature '{entity_data['feature']}' solves it.
            5. Best practices: How to execute SEO and GEO campaigns.
            
            In the acf_fields output, populate these fields:
            - industry_name: "{entity_data['industry']}"
            - SEO_challenge: "The primary challenge of building search visibility for '{entity_data['industry']}'"
            - outreach_problem: "Why '{entity_data['pain']}' makes search engine tracking and visibility hard"
            - relevant_feature: "{entity_data['feature']}"
            - success_metric: "A measurable metric (e.g. +22% AI search visibility or +15% organic click share in 60 days)"
            """
            
        elif post_type == "problem":
            prompt = f"""
            Generate a detailed problem-solving guide for SEO and search visibility teams.
            The Problem / Issue: {entity_data['issue']}
            
            The body_sections array should cover these 5 detailed sections (do NOT include intro, FAQ, or CTA as they are separate JSON fields):
            1. Why it happens: Explain the structural causes of '{entity_data['issue']}' in evolving search ecosystems.
            2. Business impact: Explain how this problem stalls search visibility and hurts business growth.
            3. How to fix: Provide general manual best practices.
            4. PetalRank solution: Explain how PetalRank automated audits and GEO tracking solve this.
            5. Best practices for long-term health: Maintaining high visibility across search engines and AI discovery platforms.
            
            In the acf_fields output, populate these fields:
            - issue: "{entity_data['issue']}"
            - why_it_happens: "Why this issue occurs in modern search landscapes"
            - business_impact: "Loss of organic leads, drops in AI visibility, and inaccurate ranking data"
            - fix: "Actionable steps to resolve the issue manually"
            - PetalRank_solution: "How PetalRank automates the diagnostics and tracks improvements"
            """
            
        elif post_type == "use_case":
            prompt = f"""
            Generate a detailed use-case spotlight page.
            Use Case: {entity_data['use_case']}
            
            The body_sections array should cover these 5 detailed sections (do NOT include intro, FAQ, or CTA as they are separate JSON fields):
            1. The State of this use case: Current trends, challenges, and stats in modern SEO and GEO.
            2. Step-by-step workflow with PetalRank: How to implement {entity_data['use_case']} tracking.
            3. Core benefits: Search landscape insights, time savings, and better ranking decisions.
            4. Best practices: Tactical search visibility and SEO advice.
            5. Advanced optimization: Scaling the optimization process.
            
            In the acf_fields output, populate these fields:
            - use_case_name: "{entity_data['use_case']}"
            - why_it_matters: "Why this tracking capability is crucial for AI search visibility"
            - target_audience: "SEO managers, agencies, and digital marketing teams"
            - key_workflow: "Brief 3-step description of the tracking setup"
            - benefits: "Accurate rank tracking, GEO metrics, and automated search audits"
            """
            
        elif post_type == "guide":
            prompt = f"""
            Generate a detailed tutorial guide.
            Guide Topic: How to {entity_data['guide']}
            
            The body_sections array should cover these 5 detailed sections (do NOT include intro, FAQ, or CTA as they are separate JSON fields):
            1. Background & Core Concepts: What is it and why is it key to modern search ecosystems.
            2. Prerequisites & Tools: What you need before starting.
            3. Step-by-step execution plan: Actionable manual walkthrough.
            4. Common mistakes: What ruins search optimization success.
            5. Advanced strategies: Scaling the workflow across search engines and generative platforms.
            
            In the acf_fields output, populate these fields:
            - guide_title: "How to {entity_data['guide']}"
            - difficulty_level: "Intermediate / Advanced"
            - time_required: "30-45 minutes"
            - key_takeaways: "Understand AI engine metrics, monitor volatility, take action on visibility drops"
            - steps: "1. Audit visibility, 2. Analyze search landscape, 3. Optimize structure, 4. Track GEO metrics"
            """
            
        else:
            raise ValueError(f"Unknown post type: {post_type}")

        # Construct the response schema for Gemini API structured JSON mode
        response_schema = {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING"},
                "meta_title": {"type": "STRING"},
                "meta_description": {"type": "STRING"},
                "slug": {"type": "STRING"},
                "h1": {"type": "STRING"},
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
                "acf_fields": {
                    "type": "OBJECT",
                    "properties": {k: {"type": "STRING"} for k in acf_keys},
                    "required": acf_keys
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
                },
                "cta_text": {"type": "STRING"},
                "schema_json": {
                    "type": "OBJECT",
                    "properties": {
                        "@context": {"type": "STRING"},
                        "@type": {"type": "STRING"},
                        "name": {"type": "STRING"},
                        "description": {"type": "STRING"}
                    },
                    "required": ["@context", "@type", "name", "description"]
                }
            },
            "required": ["title", "meta_title", "meta_description", "slug", "h1", "intro", "body_sections", "acf_fields", "faqs", "cta_text", "schema_json"]
        }

        return prompt, system_instruction, response_schema

    def _generate_mock_response(self, post_type, entity_data):
        """Generates structured mock content matching the exact JSON schema for local testing."""
        if post_type == "compare":
            comp = entity_data['competitor']
            slug = f"{clean_slug(comp)}-vs-petalrank"
            return {
                "title": f"PetalRank vs {comp}: Which SEO & Search Visibility Platform Wins in 2026?",
                "meta_title": f"PetalRank vs {comp}: Core Differences & GEO Tracking Comparison",
                "meta_description": f"Struggling to choose between PetalRank and {comp}? Discover key features, AI search visibility tools, strengths, and weaknesses to find the best fit.",
                "slug": slug,
                "h1": f"PetalRank vs {comp}: The Ultimate Comparison",
                "intro": f"<p>Comparing {comp} vs PetalRank is crucial for digital teams selecting their search tracking tools in 2026. Search is no longer just about rankings on Google. Businesses now need visibility across search engines, AI-driven discovery platforms, generative search, and constantly changing search landscapes. Today we are comparing PetalRank, an AI-powered SEO and GEO visibility platform built by Espial Solutions, and {comp}, a traditional {entity_data['positioning']}. Let's find out which is ideal for your team to make smarter ranking decisions.</p>",
                "body_sections": [
                    {
                        "heading": f"Why Teams Compare PetalRank and {comp}",
                        "content": f"<p>Modern SEO teams compare {comp} and PetalRank because the search landscape has shifted. While {comp} is known as a {entity_data['positioning']}, it lacks real-time tracking for AI engines and GEO metrics. PetalRank was created specifically to solve this growing challenge. Built by Espial Solutions, a 10-year-old digital agency with global delivery experience, PetalRank turns complex search data into clear actions. Traditional dashboards fail to show how your brand ranks in AI answers or Perplexity results. By using PetalRank, companies gain a complete view of their organic footprint, ensuring they do not lose traffic to generative engines in 2026. Moving to PetalRank helps agencies and brands automate search audits and capture up to 30% more search real estate.</p>"
                    },
                    {
                        "heading": "Key Workflow Differences",
                        "content": f"<p>The workflow of {comp} is designed around legacy rank tracking suited for {entity_data['user_type']}. In contrast, PetalRank offers multi-engine tracking and advanced GEO tracking. This drastically reduces the time spent on manual database checking. Here are the core workflow differences you will encounter in 2026:</p><ul><li><strong>Generative Visibility:</strong> PetalRank tracks how often your site is cited by AI search engines, whereas {comp} is restricted to Google SERPs. This increases AI search visibility by 40% across your portfolio.</li><li><strong>Search Landscapes:</strong> Espial Solutions designed PetalRank to map out changing search landscapes dynamically, showing multi-device organic share.</li><li><strong>Automated Action:</strong> Rather than dumping charts, PetalRank translates metrics into specific keyword opportunities and code adjustments.</li></ul><p>By shifting to an AI-powered platform, you allow your digital marketing team to focus entirely on implementation rather than debugging reports, speeding up SEO workflows by more than 50%.</p>"
                    },
                    {
                        "heading": "Why PetalRank Fits Modern Search Ecosystems Better",
                        "content": f"<p>PetalRank excels in GEO tracking and comprehensive search landscape mapping. Traditional tools cannot keep up with AI search visibility requirements. Backed by the real-world experience of Espial Solutions, PetalRank handles large-scale tracking across search engines and AI-driven engines. Our customers report faster recovery from core algorithm updates and improved ranking decisions. In fact, a recent case study in 2026 showed a 25% increase in conversion rates after migrating from traditional SERP tracking. With PetalRank, you build a sustainable digital moat that protects your brand presence from algorithm volatility.</p>"
                    }
                ],
                "acf_fields": {
                    "competitor_name": comp,
                    "competitor_strength": f"Excellent search suite built specifically for {entity_data['user_type']} with robust backlinks index.",
                    "competitor_weakness": "Lacks modern GEO tracking features and does not report visibility on AI search platforms.",
                    "ideal_user": entity_data['user_type'],
                    "comparison_summary": f"PetalRank provides advanced GEO tracking and multi-engine visibility, whereas {comp} focuses on traditional SERP metrics.",
                    "CTA": "Start monitoring with PetalRank"
                },
                "faqs": [
                    {"question": f"Is PetalRank cheaper than {comp}?", "answer": f"PetalRank offers flexible pricing designed for high-growth SEO teams, compared to {comp}'s enterprise tiers."},
                    {"question": f"Does PetalRank support tracking AI search visibility?", "answer": "Yes, PetalRank is built to track your organic mentions and citations in generative search engines."}
                ],
                "cta_text": "Ditch legacy search dashboards. Start monitoring with PetalRank today.",
                "schema_json": {
                    "@context": "https://schema.org",
                    "@type": "ProductCompareSection",
                    "name": f"PetalRank vs {comp}"
                }
            }
        elif post_type == "industry":
            ind = entity_data['industry']
            slug = f"search-visibility-for-{clean_slug(ind)}"
            return {
                "title": f"The Complete Guide to Search Visibility for {ind}",
                "meta_title": f"Search Visibility for {ind}: Tracking AI & GEO in 2026",
                "meta_description": f"Learn how to overcome {entity_data['pain']} and build search visibility for your {ind} brand using PetalRank's {entity_data['feature']} capabilities.",
                "slug": slug,
                "h1": f"How to Scale Search Visibility for {ind} Brands",
                "intro": f"<p>In the {ind} industry, organic visibility requires highly specialized tools and workflows to succeed. Track visibility across search engines, AI-driven discovery platforms, and generative search to keep ahead of fluctuations. Traditional rank tracking falls flat because search landscapes are changing. Here, we outline how to solve '{entity_data['pain']}' and establish a solid AI search visibility program using GEO tracking and insights from Espial Solutions in 2026. This allows you to stand out, monitor volatility, and make smarter ranking decisions.</p>",
                "body_sections": [
                    {
                        "heading": f"Why Organic Visibility is Harder in the {ind} Industry",
                        "content": f"<p>The {ind} sector experiences high volatility, making '{entity_data['pain']}' a major obstacle for marketing teams. Standard SEO software fails to track modern search landscapes. In 2026, over 40% of search clicks are driven by AI-powered discovery engines rather than standard blue links. To capture these, brands must understand GEO tracking. Without it, your AI search visibility stays flat. Espial Solutions designed PetalRank to resolve this exact pain. Saturated spaces require highly dynamic tracking to monitor competitor shifts. If your reports only show Google SERPs, you are missing half the picture. PetalRank makes search data actionable, showing where your {ind} brand stands in AI references and map packs.</p>"
                    },
                    {
                        "heading": f"How PetalRank's {entity_data['feature']} Feature Solves This",
                        "content": f"<p>To solve '{entity_data['pain']}', PetalRank uses its custom '{entity_data['feature']}' capability. This helps teams identify keyword gaps, map search landscapes, and automate audits. This drives faster growth and reduces reporting bottlenecks. Here are the main benefits of using these features:</p><ul><li><strong>AI Search Visibility:</strong> Track citations on ChatGPT and Perplexity, boosting your digital footprints.</li><li><strong>GEO Tracking:</strong> Target local search visibility and map packs for {ind} keywords.</li><li><strong>Landscape Analysis:</strong> Monitor search engine algorithm changes in real-time, preventing ranking drops.</li></ul><p>By automating search analysis, PetalRank ensures that your {ind} brand makes smarter ranking decisions, raising overall search visibility significantly.</p>"
                    },
                    {
                        "heading": "Best Practices for Campaign Success",
                        "content": f"<p>To maximize your search visibility, combine keyword analysis with GEO tracking. By leveraging the expertise of Espial Solutions, your brand can navigate changing search landscapes. Our experiments in 2026 show that this product-led search method improves organic traffic by 15% and ensures steady domain visibility. Maintain active audit reviews to address SEO errors. Over the long term, these optimizations build strong search authority, giving your brand a moat that competitors cannot easily match.</p>"
                    }
                ],
                "acf_fields": {
                    "industry_name": ind,
                    "SEO_challenge": f"High algorithm volatility and saturated search engine results making it hard to track rank.",
                    "outreach_problem": f"The critical challenge is overcoming {entity_data['pain']}.",
                    "relevant_feature": entity_data['feature'],
                    "success_metric": "22% average increase in AI search visibility and sustained GEO growth"
                },
                "faqs": [
                    {"question": f"What is the average organic search click share in {ind}?", "answer": "Usually under 10% for unoptimized brands, but AI tracking raises this by 2x."}
                ],
                "cta_text": f"Ready to scale your {ind} search visibility? Try PetalRank.",
                "schema_json": {
                    "@context": "https://schema.org",
                    "@type": "Article",
                    "headline": f"Search Visibility for {ind}"
                }
            }
        elif post_type == "problem":
            issue = entity_data['issue']
            slug = f"how-to-solve-{clean_slug(issue)}"
            return {
                "title": f"How to Solve {issue} in Evolving Search Landscapes",
                "meta_title": f"Solving {issue}: Search Visibility Strategies",
                "meta_description": f"Is {issue} ruining your organic rankings? Read our detailed guide on how to fix this issue and optimize your AI search visibility.",
                "slug": slug,
                "h1": f"How to Overcome {issue} in Modern Search Ecosystems",
                "intro": f"<p>Solving the issue of {issue} is a critical step towards optimizing your search visibility and ranking authority. Experiencing {issue} is a common headache for digital teams. Left unchecked, it destroys search CTR and slows down organic traffic growth in 2026. Let's look at why this occurs and how to fix it using GEO tracking, search landscapes analysis, and audit tools designed by Espial Solutions. This detailed guide provides the steps your team needs to recover organic positions and build a solid presence across search engines and AI discovery platforms.</p>",
                "body_sections": [
                    {
                        "heading": f"Why {issue} Occurs in Modern Search Landscapes",
                        "content": f"<p>{issue} typically stems from search engine algorithm volatility, poor mobile optimization, or low relevance in generative engines. This is a common pitfall for teams tracking rankings on Google alone, without considering how AI search visibility works. When search engines update their algorithms, ranking positions fluctuate. This is why GEO tracking is essential to keep visibility healthy. Furthermore, Espial Solutions has shown that ignoring zero-click search snippets leads to immediate traffic loss. Setting up modern systems that track AI mentions and audit website structure in real-time is the only way to safeguard your search landscapes and make smarter ranking decisions.</p>"
                    },
                    {
                        "heading": "The Business Impact of This Issue",
                        "content": f"<p>When you suffer from {issue}, your click-through rates drop, and your organic pipeline suffers. It delays brand discovery and limits overall growth. Here are the major risks of ignoring this problem in 2026:</p><ul><li><strong>Decreased Click Share:</strong> Algorithm updates cause ranking drops, resulting in a loss of organic leads.</li><li><strong>Inaccurate Data:</strong> Standard trackers fail to capture geo-located results, leading to bad ranking decisions.</li><li><strong>Threat from AI:</strong> Missing out on AI search visibility means competitors take over Perplexity and ChatGPT results.</li></ul><p>By failing to address this issue early, you risk permanent traffic stagnation, setting your search visibility back by months and costing thousands in lost revenue.</p>"
                    },
                    {
                        "heading": "How PetalRank Solves This Problem Automatically",
                        "content": f"<p>PetalRank fixes {issue} through automated search audits and GEO tracking systems. This replaces manual tracking, letting you run campaigns that consistently drive visibility. By resolving this bottleneck, you can expand your AI search visibility and ensure your team achieves its organic traffic goals. Built based on the agency experience of Espial Solutions, PetalRank analyzes search landscapes, alerts you to volatility, and shows the exact action needed. This product-led search methodology protects your brand authority while driving consistent rank results.</p>"
                    }
                ],
                "acf_fields": {
                    "issue": issue,
                    "why_it_happens": "Inaccurate rank tracking systems and shifting AI engine search parameters.",
                    "business_impact": "Reduced organic traffic, lost click share on AI engines, and poor ranking decisions.",
                    "fix": "Audit target pages manually and optimize content structure for search snippets.",
                    "PetalRank_solution": "Use smart automated audits and GEO tracking to locate and resolve search volatility."
                },
                "faqs": [
                    {"question": f"What is the first step to fixing {issue}?", "answer": "Perform a complete search visibility audit to locate ranking drops."}
                ],
                "cta_text": f"Solve {issue} once and for all. Start using PetalRank today.",
                "schema_json": {
                    "@context": "https://schema.org",
                    "@type": "TechArticle",
                    "headline": f"Solving {issue}"
                }
            }
        elif post_type == "use_case":
            uc = entity_data['use_case']
            slug = f"{clean_slug(uc)}-tool"
            return {
                "title": f"The Best {uc} Tool for Modern Digital Teams",
                "meta_title": f"How to Automate {uc} Tracking",
                "meta_description": f"Learn how to build a scalable {uc} process. See how PetalRank automates this tracking workflow to maximize organic reach.",
                "slug": slug,
                "h1": f"Scale Your {uc} Campaigns with PetalRank",
                "intro": f"<p>Running a successful {uc} campaign can transform your company's search engine rankings and brand presence. Implementing {uc} tracking is a proven way to drive authority. However, executing this manually at scale is incredibly tedious. PetalRank offers a fully automated tool for {uc} that utilizes GEO tracking and AI search visibility analysis to map search landscapes in 2026. This replaces manual audits and helps your digital team make smarter ranking decisions. Backed by Espial Solutions, our platform provides actionable data to stay ahead of search updates.</p>",
                "body_sections": [
                    {
                        "heading": f"Why {uc} is Essential for AI Search Visibility",
                        "content": f"<p>A successful {uc} strategy ensures high-quality presence in generative engine responses. By targeting AI search visibility, you can grow brand authority and organic click share. However, mapping search landscapes manually is a major bottleneck. When you build pages tailored to this strategy, visibility increases by 20%. This represents a significant shift from old-school SEO to automated, AI-powered tracking. In the current search ecosystem, obtaining citations within AI answers is the most reliable way to boost traffic. Manual research simply cannot keep up with changing search landscapes, making PetalRank's automated auditing crucial for modern teams.</p>"
                    },
                    {
                        "heading": "How to Automate the Workflow",
                        "content": f"<p>PetalRank lets you set up search tracking, auto-discover keyword volatility, and analyze competitor visibility in minutes. By utilizing custom GEO tracking, you keep audit responses accurate. Here is the automated setup checklist for 2026:</p><ul><li><strong>Connect Project:</strong> Integrate your website domains safely into PetalRank.</li><li><strong>Select Campaign:</strong> Choose {uc} as your primary tracking objective to load tailored metrics.</li><li><strong>Analyze Landscapes:</strong> Monitor search engine algorithm changes and AI citations automatically, driving a 45% efficiency gain.</li></ul><p>By automating these administrative tasks, your SEO managers can focus entirely on optimization and content rather than debugging reports, which directly improves campaign success. Espial Solutions built this workflow to save hours of manual data aggregation.</p>"
                    },
                    {
                        "heading": "Maximizing Campaign Returns",
                        "content": f"<p>To secure consistent growth, you must optimize each stage of the search funnel. PetalRank provides tracking tools to analyze your search landscapes performance. By implementing these audits, you minimize ranking mistakes and build long-term search authority. A systematic approach to {uc} ensures that every page is monitored, which reduces visibility drops and preserves brand search presence. Over a 12-month period, these automated gains translate into thousands of dollars in saved consultant costs and a much higher digital ROI. Trust PetalRank, designed by Espial Solutions, to manage your organic presence.</p>"
                    }
                ],
                "acf_fields": {
                    "use_case_name": uc,
                    "why_it_matters": "High-impact search visibility that drives organic clicks directly.",
                    "target_audience": "In-house SEO professionals, marketing directors, and digital agencies.",
                    "key_workflow": "Connect domain, choose tracking parameters, auto-generate visibility reports, track.",
                    "benefits": "Saves 15 hours per week and generates 3x more accurate rank data."
                },
                "faqs": [
                    {"question": f"How long does a {uc} setup take to launch?", "answer": "With PetalRank's automation, you can go from domain setup to visibility tracking in under 10 minutes."}
                ],
                "cta_text": f"Ready to scale {uc}? Try PetalRank now.",
                "schema_json": {
                    "@context": "https://schema.org",
                    "@type": "WebApplication",
                    "name": f"PetalRank {uc} Automation"
                }
            }
        elif post_type == "guide":
            gd = entity_data['guide']
            slug = clean_slug(gd)
            return {
                "title": f"How to {gd}: A Step-by-Step Search Visibility Guide",
                "meta_title": f"Step-by-Step Guide: How to {gd}",
                "meta_description": f"Master the art of search tracking. Follow our detailed tutorial to learn how to {gd} like a pro using modern GEO and SEO tools.",
                "slug": slug,
                "h1": f"How to {gd} (The Definitive Guide)",
                "intro": f"<p>If you want to know how to {gd}, this definitive tutorial outlines the exact steps you need to follow in 2026. Search success depends on tracking quality. In this tutorial, we will show you exactly how to {gd} to improve your rankings and build strong AI search visibility. This manual will save you time and maximize your search optimization campaigns. We cover everything from setting up your initial search landscapes to tracking volatility over time. Backed by the 10-year agency history of Espial Solutions, this guide helps your team make smarter ranking decisions. By putting proper processes in place, your organization can ensure that every page ranks well across search engines and AI discovery platforms.</p>",
                "body_sections": [
                    {
                        "heading": "Core Concepts & Fundamentals",
                        "content": f"<p>Learning how to {gd} is foundational for any modern SEO and GEO campaign. Without this skill, search tracking contains errors, resulting in poor ranking decisions and stagnating visibility. Using PetalRank's GEO tracking helps resolve this. By focusing on specific search landscapes parameters, you can identify keyword opportunities in under 10 minutes. This forms the basis of a repeatable, sustainable approach to search engine updates. Understanding the fundamentals of AI search visibility allows you to optimize your content for generative engines rather than getting left behind in legacy blue link models.</p>"
                    },
                    {
                        "heading": "Step-by-Step Implementation Guide",
                        "content": f"<p>First, configure your domain settings. Second, track local GEO visibility. Third, perform automated search audits. Finally, monitor algorithm changes to keep your position high. Here are the steps to follow in 2026:</p><ul><li><strong>Define Goals:</strong> Target a 22% increase in AI search visibility.</li><li><strong>Map Search Landscapes:</strong> Track rankings across Google, Perplexity, and Bing.</li><li><strong>Audit Volatility:</strong> Identify search drops before they impact revenue, boosting efficiency by 35%.</li></ul><p>Each step is crucial to building search authority. Rushing setup or using inaccurate tracking tools will result in bad ranking decisions, ruining your growth potential. Taking the extra time to map localized GEO data is the difference between a top placement and dropping off page one.</p>"
                    },
                    {
                        "heading": "Advanced Strategies for Scale",
                        "content": f"<p>To take your organic click share to the next level, you must integrate your search landscapes tracking. Automated scheduling and tracking platforms like PetalRank allow you to coordinate multiple projects. This keeps metrics accurate, prevents drops, and lets your team focus on action instead of manual spreadsheet checking. Developed by Espial Solutions, these workflows scale across search engines and AI-driven platforms, providing a compounding boost to your website's authority. This systematic scaling approach ensures your search visibility matches your organic traffic goals and keeps your team highly productive.</p>"
                    }
                ],
                "acf_fields": {
                    "guide_title": f"How to {gd}",
                    "difficulty_level": "Intermediate",
                    "time_required": "45 Minutes",
                    "key_takeaways": "Improve rank accuracy, master GEO tracking, and resolve search volatility.",
                    "steps": "1. Domain configuration, 2. GEO setup, 3. Landscape analysis, 4. Auto-audit"
                },
                "faqs": [
                    {"question": f"Is learning to {gd} hard?", "answer": "It takes practice, but PetalRank's automated auditing simplifies the process."}
                ],
                "cta_text": f"Stop doing this manually. Automate {gd} with PetalRank.",
                "schema_json": {
                    "@context": "https://schema.org",
                    "@type": "TechArticle",
                    "headline": f"How to {gd}"
                }
            }
        else:
            raise ValueError(f"Unknown post type: {post_type}")

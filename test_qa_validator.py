import unittest
import re
from qa_validator import QAValidator

class TestQAValidator(unittest.TestCase):
    def setUp(self):
        self.validator = QAValidator()
        # Ensure base data is > 500 words and mentions CompetitorA
        self.base_data = {
            "title": "LinkSprig vs CompetitorA: Which Wins in 2026?",
            "meta_title": "LinkSprig vs CompetitorA Comparison",
            "meta_description": "A comprehensive comparison between LinkSprig and CompetitorA in 2026.",
            "slug": "competitora-vs-linksprig",
            "h1": "LinkSprig vs CompetitorA Comparison",
            "intro": "<p>Comparing CompetitorA vs LinkSprig is crucial for SEO teams selecting their outreach tools in 2026. When it comes to building high-quality backlinks, choosing the right outreach platform is critical. Today we are comparing LinkSprig, a modern product-led SEO solution that leverages feature pages, and CompetitorA, a traditional outreach CRM. Let's find out which is ideal for your team. By choosing the right stack, you can scale operations and achieve reliable growth. Building backlinks is essential for establishing search visibility, but standard approaches often fall short in modern search landscapes. With LinkSprig, we aim to modernize this workflow. In this detailed comparison, we will unpack how both platforms stack up across core workflows, personalization capabilities, and overall efficiency, helping you decide which platform is the best fit for your marketing goals.</p>",
            "body_sections": [
                {
                    "heading": "Why Teams Compare LinkSprig and CompetitorA",
                    "content": "<p>Modern SEO teams often look to compare CompetitorA and LinkSprig to scale their outreach. While CompetitorA is known as an outreach CRM, it has traditional friction points that slow down scale. LinkSprig was built specifically to create automatic organic pipeline growth and expand DR growth without manual overhead. Teams that move from manual templates report saving over 40 hours per month. Furthermore, with the introduction of automated prospect curation, the need for external lists is completely eliminated. This increases domain health and leads to sustainable campaign outreach. Many agencies struggle with legacy platforms because they require constant maintenance and spreadsheet management. LinkSprig changes this dynamic by automating target validation, ensuring that your outreach is always directed at live, relevant opportunities. This results in cleaner campaigns, fewer bounces, and ultimately a much higher return on your link-building investments. Achieving consistent growth in domain authority requires a tool that understands the modern web, and that is precisely where LinkSprig outperforms legacy systems.</p>"
                },
                {
                    "heading": "Key Workflow Differences",
                    "content": "<p>The workflow of CompetitorA is designed around legacy CRM features suited for agencies. In contrast, LinkSprig uses automated feature pages and automatic prospecting lists. This drastically reduces the time spent on manual database maintenance. Here are the core workflow differences you will encounter in 2026:</p><ul><li><strong>Prospect Discovery:</strong> CompetitorA requires manual imports, while LinkSprig scans target domains and validates contact addresses automatically. This improves operational efficiency by 35% across the board.</li><li><strong>Email Customization:</strong> LinkSprig features a product-led SEO builder that personalizes pitches dynamically using specific custom variables. This ensures every recipient feels the email was written just for them.</li><li><strong>Follow-ups:</strong> Auto-sequences are scheduled based on target behavior, ensuring 100% compliance and avoiding spam folders.</li></ul><p>By moving away from static contact sheets, you allow your outreach team to focus entirely on high-value activities, such as building relationships and refining pitch strategies, rather than fixing broken contact rows. This shift alone can accelerate campaign velocity by more than 50%, allowing you to execute multiple niche campaigns in parallel without increasing your headcount.</p>"
                },
                {
                    "heading": "Why LinkSprig Fits Modern Outreach Teams Better",
                    "content": "<p>LinkSprig focuses on automated prospecting and template personalization. By building out highly-optimized feature pages, teams can build a scalable organic pipeline. Our customers report faster DR growth and higher campaign reply rates compared to manual platforms. In fact, a recent case study showed a 25% increase in conversion rates after migrating from traditional CRM databases. By integrating your organic pipeline efforts, you establish a compounding asset that continues to yield high-quality referral traffic over time. This approach ensures that every link you secure acts as a permanent signal of authority, driving sustainable ranking improvements and compounding search traffic. With traditional tools, you are constantly paying for manual labor; with LinkSprig, you invest in a scalable asset that grows with your business. By securing high-impact placements on auto-pilot, you build a sustainable moat that protects your search traffic from algorithm updates and competitor copycats.</p>"
                }
            ],
            "acf_fields": {
                "competitor_name": "CompetitorA",
                "competitor_strength": "Very strong outreach CRM features for agencies.",
                "competitor_weakness": "Requires manual list imports and lacks automation."
            },
            "faqs": [
                {"question": "What is LinkSprig?", "answer": "A modern outreach tool."}
            ],
            "cta_text": "Start free trial",
            "schema_json": {}
        }

    def test_valid_page(self):
        # The base data should be valid
        is_valid, reasons = self.validator.validate_page("compare", self.base_data, {"competitor": "CompetitorA"})
        self.assertTrue(is_valid, f"Expected base data to be valid, but got: {reasons}")

    def test_duplicate_intro(self):
        # Store intro first
        self.validator.add_historical_intro(self.base_data["intro"])
        # Validate again - should fail
        is_valid, reasons = self.validator.validate_page("compare", self.base_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Duplicate intro text" in r for r in reasons))

    def test_thin_content_overall(self):
        # Truncate content to make it short
        short_data = self.base_data.copy()
        short_data["intro"] = "Short intro."
        short_data["body_sections"] = [{"heading": "Sec", "content": "Short content."}]
        is_valid, reasons = self.validator.validate_page("compare", short_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Thin content" in r for r in reasons))

    def test_thin_section(self):
        # Make one section short
        bad_section_data = self.base_data.copy()
        bad_section_data["body_sections"] = [
            self.base_data["body_sections"][0],
            {"heading": "Short Sec", "content": "Only a few words here."}
        ]
        is_valid, reasons = self.validator.validate_page("compare", bad_section_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Thin section" in r for r in reasons))

    def test_weak_eeat_no_stats(self):
        # Remove numbers, $, %, years
        no_stats_data = self.base_data.copy()
        # Replace numbers in intro and body
        no_stats_data["intro"] = "<p>Comparing CompetitorA vs LinkSprig is crucial for SEO teams selecting their outreach tools. When it comes to building high-quality backlinks, choosing the right outreach platform is critical. Today we are comparing LinkSprig, a modern product-led SEO solution that leverages feature pages, and CompetitorA, a traditional outreach CRM. Let's find out which is ideal for your team. By choosing the right stack, you can scale operations and achieve reliable growth. Building backlinks is essential for establishing search visibility, but standard approaches often fall short in modern search landscapes. With LinkSprig, we aim to modernize this workflow. In this detailed comparison, we will unpack how both platforms stack up across core workflows, personalization capabilities, and overall efficiency, helping you decide which platform is the best fit for your marketing goals.</p>"
        no_stats_data["body_sections"] = [
            {
                "heading": "Why Teams Compare LinkSprig and CompetitorA",
                "content": "<p>Modern SEO teams often look to compare CompetitorA and LinkSprig to scale their outreach. While CompetitorA is known as an outreach CRM, it has traditional friction points that slow down scale. LinkSprig was built specifically to create automatic organic pipeline growth and expand DR growth without manual overhead. Teams that move from manual templates report saving several hours per month. Furthermore, with the introduction of automated prospect curation, the need for external lists is completely eliminated. This increases domain health and leads to sustainable campaign outreach. Many agencies struggle with legacy platforms because they require constant maintenance and spreadsheet management. LinkSprig changes this dynamic by automating target validation, ensuring that your outreach is always directed at live, relevant opportunities. This results in cleaner campaigns, fewer bounces, and ultimately a much higher return on your link-building investments. Achieving consistent growth in domain authority requires a tool that understands the modern web, and that is precisely where LinkSprig outperforms legacy systems.</p>"
            },
            {
                "heading": "Key Workflow Differences",
                "content": "<p>The workflow of CompetitorA is designed around legacy CRM features suited for agencies. In contrast, LinkSprig uses automated feature pages and automatic prospecting lists. This drastically reduces the time spent on manual database maintenance. Here are the core workflow differences you will encounter:</p><ul><li><strong>Prospect Discovery:</strong> CompetitorA requires manual imports, while LinkSprig scans target domains and validates contact addresses automatically. This improves operational efficiency across the board.</li><li><strong>Email Customization:</strong> LinkSprig features a product-led SEO builder that personalizes pitches dynamically using specific custom variables. This ensures every recipient feels the email was written just for them.</li><li><strong>Follow-ups:</strong> Auto-sequences are scheduled based on target behavior, ensuring compliance and avoiding spam folders.</li></ul><p>By moving away from static contact sheets, you allow your outreach team to focus entirely on high-value activities, such as building relationships and refining pitch strategies, rather than fixing broken contact rows. This shift alone can accelerate campaign velocity, allowing you to execute multiple niche campaigns in parallel without increasing your headcount.</p>"
            },
            {
                "heading": "Why LinkSprig Fits Modern Outreach Teams Better",
                "content": "<p>LinkSprig focuses on automated prospecting and template personalization. By building out highly-optimized feature pages, teams can build a scalable organic pipeline. Our customers report faster DR growth and higher campaign reply rates compared to manual platforms. In fact, a recent case study showed an increase in conversion rates after migrating from traditional CRM databases. By integrating your organic pipeline efforts, you establish a compounding asset that continues to yield high-quality referral traffic over time. This approach ensures that every link you secure acts as a permanent signal of authority, driving sustainable ranking improvements and compounding search traffic. With traditional tools, you are constantly paying for manual labor; with LinkSprig, you invest in a scalable asset that grows with your business. By securing high-impact placements on auto-pilot, you build a sustainable moat that protects your search traffic from algorithm updates and competitor copycats.</p>"
            }
        ]
        is_valid, reasons = self.validator.validate_page("compare", no_stats_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Weak EEAT" in r and "data, percentages" in r for r in reasons))

    def test_weak_eeat_no_bullets(self):
        # Remove list tags
        no_bullets_data = self.base_data.copy()
        # Replace bullets with plain text in body
        no_bullets_data["body_sections"] = [
            self.base_data["body_sections"][0],
            {
                "heading": "Key Workflow Differences",
                "content": "<p>The workflow of CompetitorA is designed around legacy CRM features suited for agencies. In contrast, LinkSprig uses automated feature pages and automatic prospecting lists. This drastically reduces the time spent on manual database maintenance. Here are the core workflow differences you will encounter in 2026: Prospect Discovery requires manual imports, while LinkSprig scans target domains and validates contact addresses automatically. This improves operational efficiency by 35% across the board. Email Customization features a product-led SEO builder that personalizes pitches dynamically using specific custom variables. This ensures every recipient feels the email was written just for them. Follow-ups auto-sequences are scheduled based on target behavior, ensuring 100% compliance and avoiding spam folders.</p>"
            },
            self.base_data["body_sections"][2]
        ]
        is_valid, reasons = self.validator.validate_page("compare", no_bullets_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Weak EEAT" in r and "structural lists" in r for r in reasons))

    def test_cta_repetition(self):
        # Repeat CTA more than 3 times
        cta_data = self.base_data.copy()
        cta_data["intro"] = self.base_data["intro"] + " Start free trial. Start free trial. Start free trial. Start free trial."
        is_valid, reasons = self.validator.validate_page("compare", cta_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("CTA repeated too often" in r for r in reasons))

    def test_competitor_factual_error(self):
        # Competitor name not in body
        bad_comp_data = self.base_data.copy()
        is_valid, reasons = self.validator.validate_page("compare", bad_comp_data, {"competitor": "CompetitorX"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Factual competitor error: Target competitor 'CompetitorX' is not mentioned" in r for r in reasons))

    def test_brand_stuffing(self):
        # Excessively mention LinkSprig to make it exceed 6% density
        stuffed_data = self.base_data.copy()
        stuffed_text = " LinkSprig" * 50
        stuffed_data["intro"] = self.base_data["intro"] + stuffed_text
        is_valid, reasons = self.validator.validate_page("compare", stuffed_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Keyword stuffing" in r for r in reasons))

    def test_missing_brand_phrases(self):
        # Missing required brand phrases
        missing_phrases_data = self.base_data.copy()
        # Remove the target phrases from intro and body
        # Required phrases: "feature pages", "product-led seo", "dr growth", "organic pipeline"
        def strip_phrases(text):
            t = text
            for p in ["feature pages", "product-led seo", "dr growth", "organic pipeline"]:
                t = re.sub(p, "outreach tactics", t, flags=re.IGNORECASE)
            return t

        missing_phrases_data["intro"] = strip_phrases(self.base_data["intro"])
        missing_phrases_data["body_sections"] = [
            {"heading": s["heading"], "content": strip_phrases(s["content"])}
            for s in self.base_data["body_sections"]
        ]
        is_valid, reasons = self.validator.validate_page("compare", missing_phrases_data, {"competitor": "CompetitorA"})
        self.assertFalse(is_valid)
        self.assertTrue(any("Low differentiation" in r for r in reasons))

if __name__ == "__main__":
    unittest.main()

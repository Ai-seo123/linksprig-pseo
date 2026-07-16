import unittest
from formatter import slugify, format_blog_html, format_imported_blog_html
from bs4 import BeautifulSoup

class TestFormatter(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("Hello World!"), "hello-world")
        self.assertEqual(slugify("SEO: Personalization & CRM"), "seo-personalization-crm")
        self.assertEqual(slugify("  outreach-tactic_123  "), "outreach-tactic-123")

    def test_format_blog_html(self):
        title = "My Test Blog Post"
        intro_html = "<p>Welcome to our new platform.</p>"
        body_sections = [
            {"heading": "Why Scale Matters", "content": "<p>Content of section 1.</p>"},
            {"heading": "Tactic 2: Automated Curation", "content": "<p>Content of section 2.</p>"}
        ]
        faqs = [
            {"question": "How to start?", "answer": "Click the button."}
        ]
        
        result_html = format_blog_html(title, intro_html, body_sections, faqs)
        
        # Parse result using BeautifulSoup
        soup = BeautifulSoup(result_html, "html.parser")
        
        # Verify Main Title H1 is not present in body content (WordPress theme handles it)
        h1 = soup.find("h1", class_="linksprig-main-title")
        self.assertIsNone(h1)
        
        # Verify 3-column layout classes
        self.assertIsNotNone(soup.find(class_="linksprig-blog-container"))
        self.assertIsNotNone(soup.find(class_="linksprig-toc-sidebar"))
        self.assertIsNotNone(soup.find(class_="linksprig-right-sidebar"))
        
        # Verify section heading tags are <h2> (for better hierarchy)
        h2_headings = soup.find_all("h2")
        # h2s should include: "Table of Contents", "Why Scale Matters", "Tactic 2: Automated Curation", "Frequently Asked Questions"
        h2_texts = [h.text.strip() for h in h2_headings]
        self.assertIn("Why Scale Matters", h2_texts)
        self.assertIn("Tactic 2: Automated Curation", h2_texts)
        self.assertIn("Frequently Asked Questions", h2_texts)
        
        # Verify IDs exist on section headings and match TOC hrefs
        toc_links = soup.find_all("a", class_="linksprig-toc-link")
        self.assertEqual(len(toc_links), 3) # 2 sections + 1 faq
        
        for link in toc_links:
            href = link["href"]
            self.assertTrue(href.startswith("#"))
            target_id = href[1:]
            # Ensure target exists in document
            target_el = soup.find(id=target_id)
            self.assertIsNotNone(target_el, f"Target element with id {target_id} not found")
            
        # Verify sticky right author card details
        author_card = soup.find(class_="sidebar-blog-author")
        self.assertIsNotNone(author_card)
        self.assertIn("sticky", author_card["class"])
        self.assertEqual(author_card.find(class_="cta-card-heading").text.strip(), "Like what you see?")
        self.assertEqual(author_card.find(class_="cta-card-text").text.strip(), "You can test it out yourself - no credit card needed")
        
        # Verify CSS styles are present and contain our spacing custom properties
        style_block = soup.find("style")
        self.assertIsNotNone(style_block)
        self.assertIn("margin-top: 50px", style_block.text)
        self.assertIn("margin-bottom: 8px", style_block.text)
        self.assertIn("padding: 10px 15px", style_block.text)

    def test_format_imported_blog_html(self):
        title = "Imported Blog Post"
        flat_html = """
        <h3>Why Scale Matters</h3>
        <p>Content 1</p>
        <h3>Tactic 2</h3>
        <p>Content 2</p>
        <h3>Frequently Asked Questions</h3>
        <p>FAQs list here</p>
        """
        
        result_html = format_imported_blog_html(title, flat_html)
        
        soup = BeautifulSoup(result_html, "html.parser")
        
        # Verify Main Title H1 is not present in body content (WordPress theme handles it)
        h1 = soup.find("h1", class_="linksprig-main-title")
        self.assertIsNone(h1)
        
        # Verify TOC links
        toc_links = soup.find_all("a", class_="linksprig-toc-link")
        self.assertEqual(len(toc_links), 3)
        self.assertEqual(toc_links[0].text.strip(), "Why Scale Matters")
        self.assertEqual(toc_links[1].text.strip(), "Tactic 2")
        self.assertEqual(toc_links[2].text.strip(), "Frequently Asked Questions")
        
        # Verify the target IDs were injected in-place in flat body
        headings = soup.find("article", class_="linksprig-content-area").find_all("h3")
        self.assertEqual(len(headings), 3)
        self.assertEqual(headings[0]["id"], "sec-1-why-scale-matters")

if __name__ == "__main__":
    unittest.main()

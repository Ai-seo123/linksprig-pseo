import re
from bs4 import BeautifulSoup

def slugify(text):
    """Generate a clean slug for anchor IDs."""
    text = str(text).lower()
    text = text.replace('_', '-')
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

# Shared CSS stylesheet for embedding in post HTML
CSS_STYLES = """
<style>
.linksprig-blog-container {
    --primary: #2563eb;
    --primary-hover: #1d4ed8;
    --text-main: #334155;
    --text-headings: #0f172a;
    --bg-sidebar: #f8fafc;
    --border-color: #e2e8f0;
    --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;

    display: grid;
    grid-template-columns: 240px minmax(0, 1fr) 260px;
    gap: 40px;
    max-width: 1280px;
    margin-top: 50px; /* 50px space below theme navbar when opened */
    margin-bottom: 0;
    margin-left: auto;
    margin-right: auto;
    padding: 10px 15px; /* Decreased padding to save space */
    font-family: var(--font-stack);
    color: var(--text-main);
    line-height: 1.75;
}

/* Left Sidebar (TOC) */
.linksprig-toc-sidebar {
    grid-column: 1;
}

.linksprig-toc-wrapper {
    position: -webkit-sticky;
    position: sticky;
    top: 32px;
    padding: 16px; /* Decreased padding */
    background: var(--bg-sidebar);
    border-radius: 12px;
    border: 1px solid var(--border-color);
}

.linksprig-toc-title {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #64748b;
    margin-top: 0;
    margin-bottom: 12px;
    padding-bottom: 6px;
    border-bottom: 2px solid var(--border-color);
}

.linksprig-toc-list {
    list-style: none;
    padding: 0;
    margin: 0;
}

.linksprig-toc-item {
    margin-bottom: 8px;
    line-height: 1.3;
}

.linksprig-toc-link {
    color: #475569;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 500;
    display: block;
    padding-left: 10px;
    border-left: 2px solid transparent;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.linksprig-toc-link:hover {
    color: var(--text-headings);
    border-left-color: var(--primary);
    padding-left: 14px;
}

/* Middle Column (Content) */
.linksprig-content-area {
    grid-column: 2;
}

.linksprig-main-title {
    font-size: 2.5rem;
    font-weight: 800;
    letter-spacing: -0.025em;
    color: var(--text-headings);
    line-height: 1.15;
    margin-top: 0;
    margin-bottom: 24px;
}

.linksprig-intro-section {
    font-size: 1.1rem;
    color: #475569;
    line-height: 1.8;
    margin-bottom: 24px;
}

.linksprig-content-area h2, .linksprig-content-area h3 {
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--text-headings);
    margin-top: 24px; /* Decreased space before headings */
    margin-bottom: 8px; /* Decreased space between subtitle and text */
    scroll-margin-top: 40px;
    border-bottom: 1px solid var(--border-color);
    padding-bottom: 6px;
}

.linksprig-content-area h2 {
    font-size: 1.45rem;
}

.linksprig-content-area h3 {
    font-size: 1.25rem;
}

.linksprig-content-area p {
    margin-bottom: 16px; /* Decreased spacing between text paragraphs */
}

.linksprig-content-area ul, .linksprig-content-area ol {
    margin-bottom: 18px;
    padding-left: 20px;
}

.linksprig-content-area li {
    margin-bottom: 6px;
}

.linksprig-content-area strong {
    color: var(--text-headings);
}

/* FAQ Accordion Styling */
.linksprig-faq-list {
    margin-top: 16px;
}

.linksprig-faq-item {
    background: #ffffff;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    margin-bottom: 10px;
    padding: 14px;
    transition: box-shadow 0.2s ease;
}

.linksprig-faq-item:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
}

.linksprig-faq-question {
    font-weight: 600;
    color: var(--text-headings);
    margin: 0 0 6px 0;
    font-size: 1rem;
}

.linksprig-faq-answer {
    color: var(--text-main);
    margin: 0;
    font-size: 0.9rem;
}

/* Right Sidebar (CTA/Author) */
.linksprig-right-sidebar {
    grid-column: 3;
}

.sidebar-blog-author.sticky {
    position: -webkit-sticky;
    position: sticky;
    top: 32px;
    padding: 20px;
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border-radius: 12px;
    color: #ffffff;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    display: flex;
    flex-direction: column;
    gap: 14px;
    border: 1px solid rgba(255, 255, 255, 0.08);
}

.cta-card-heading {
    font-size: 1.15rem;
    font-weight: 700;
    color: #ffffff;
    line-height: 1.3;
}

.cta-card-text {
    font-size: 0.85rem;
    color: #94a3b8;
    line-height: 1.5;
}

.cta-card-button {
    display: inline-block;
    text-align: center;
    background: var(--primary);
    color: #ffffff;
    text-decoration: none;
    font-weight: 600;
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 0.85rem;
    transition: background 0.2s ease, transform 0.1s ease;
}

.cta-card-button:hover {
    background: var(--primary-hover);
    transform: translateY(-1px);
}

.cta-card-button:active {
    transform: translateY(0);
}

/* Intermediate screens - 2 columns, move right sidebar to bottom */
@media (max-width: 1200px) {
    .linksprig-blog-container {
        grid-template-columns: 220px minmax(0, 1fr);
    }
    
    .linksprig-right-sidebar {
        grid-column: 1 / span 2;
        margin-top: 30px;
    }
    
    .sidebar-blog-author.sticky {
        position: static;
        width: 100%;
        max-width: 500px;
        margin: 0 auto;
    }
}

/* Mobile screens - stack everything */
@media (max-width: 768px) {
    .linksprig-blog-container {
        display: flex;
        flex-direction: column;
        gap: 24px;
        padding: 10px 5px;
    }
    
    .linksprig-toc-sidebar {
        width: 100%;
        position: static;
    }
    
    .linksprig-toc-wrapper {
        position: static;
        padding: 16px;
    }
    
    .linksprig-main-title {
        font-size: 2rem;
    }
    
    .linksprig-right-sidebar {
        width: 100%;
    }
}
</style>
"""

def build_layout_html(title, toc_list_html, body_content_html, meta_title=None, meta_description=None, focus_keyword=None):
    """Wrapper template for building the 3-column post content."""
    head_html = ""
    if meta_title or meta_description or focus_keyword:
        head_html = f"""<head>
  <meta charset="UTF-8">
  <title>{meta_title or title}</title>
  <meta name="description" content="{meta_description or ''}">
  <meta name="keywords" content="{focus_keyword or ''}">
  {CSS_STYLES}
</head>
"""
    else:
        head_html = CSS_STYLES

    body_open = "<body>\n" if head_html.startswith("<head>") else ""
    body_close = "\n</body>" if head_html.startswith("<head>") else ""

    return f"""{head_html}
{body_open}<div class="linksprig-blog-container">
  <!-- Left Sidebar (Table of Contents) -->
  <aside class="linksprig-toc-sidebar">
    <nav class="linksprig-toc-wrapper">
      <h2 class="linksprig-toc-title">Table of Contents</h2>
      <ul class="linksprig-toc-list">{toc_list_html}
      </ul>
    </nav>
  </aside>

  <!-- Middle Column (Main Blog Content) -->
  <article class="linksprig-content-area">
    <h1 class="linksprig-main-title main-title post-title">{title}</h1>
    {body_content_html}
  </article>

  <!-- Right Sidebar (Sticky CTA) -->
  <aside class="linksprig-right-sidebar">
    <div class="sidebar-blog-author sticky">
      <div class="cta-card-heading">Like what you see?</div>
      <div class="cta-card-text">You can test it out yourself - no credit card needed</div>
      <a href="https://linksprig.com/signup" class="cta-card-button">Get Started Free</a>
    </div>
  </aside>
</div>{body_close}
"""

def format_blog_html(title, intro_html, body_sections, faqs_list=None, meta_title=None, meta_description=None, focus_keyword=None):
    """Formats structured blog content (from generator/excel pipelines)."""
    toc_items = []
    
    # Process sections and generate IDs
    sections_html = ""
    for idx, sec in enumerate(body_sections):
        heading_text = sec["heading"]
        heading_slug = f"sec-{idx+1}-{slugify(heading_text)}"
        toc_items.append((heading_text, heading_slug))
        
        # Primary section subtitles are <h2> now
        sections_html += f"\n\n<h2 id=\"{heading_slug}\">{heading_text}</h2>\n{sec['content']}"
        
    # Process FAQs
    faq_html = ""
    if faqs_list:
        faq_slug = "frequently-asked-questions"
        toc_items.append(("Frequently Asked Questions", faq_slug))
        
        faq_html += f"\n\n<h2 id=\"{faq_slug}\">Frequently Asked Questions</h2>\n<div class=\"linksprig-faq-list\">"
        for faq in faqs_list:
            faq_html += f"\n  <div class=\"linksprig-faq-item\">\n    <h4 class=\"linksprig-faq-question\">{faq['question']}</h4>\n    <p class=\"linksprig-faq-answer\">{faq['answer']}</p>\n  </div>"
        faq_html += "\n</div>"
        
    # Build TOC list HTML
    toc_list_html = ""
    for label, slug in toc_items:
        toc_list_html += f"\n        <li class=\"linksprig-toc-item\"><a class=\"linksprig-toc-link\" href=\"#{slug}\">{label}</a></li>"
        
    # Assemble body content
    body_content_html = f"""<div class="linksprig-intro-section">
      {intro_html}
    </div>{sections_html}{faq_html}"""
    
    return build_layout_html(title, toc_list_html, body_content_html, meta_title, meta_description, focus_keyword)

def format_imported_blog_html(title, flat_body_html):
    """Formats flat body HTML (from imported WordPress HTML posts)."""
    soup = BeautifulSoup(flat_body_html, "html.parser")
    
    # Decompose any existing custom layout/sidebars if already present
    for el in soup.find_all(class_=["linksprig-blog-container", "linksprig-toc-sidebar", "linksprig-right-sidebar"]):
        el.decompose()
        
    # Extract headings (h2 and h3)
    headings = soup.find_all(["h2", "h3"])
    toc_items = []
    
    for idx, heading in enumerate(headings):
        heading_text = heading.text.strip()
        if not heading_text:
            continue
            
        # Treat FAQs uniquely
        if "frequently asked questions" in heading_text.lower() or "faq" == heading_text.lower():
            heading_slug = "frequently-asked-questions"
        else:
            heading_slug = f"sec-{idx+1}-{slugify(heading_text)}"
            
        heading["id"] = heading_slug
        toc_items.append((heading_text, heading_slug))
        
    # Build TOC list HTML
    toc_list_html = ""
    for label, slug in toc_items:
        toc_list_html += f"\n        <li class=\"linksprig-toc-item\"><a class=\"linksprig-toc-link\" href=\"#{slug}\">{label}</a></li>"
        
    # Assemble body content from the modified soup
    body_content_html = str(soup)
    
    return build_layout_html(title, toc_list_html, body_content_html)

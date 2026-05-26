import re

class InternalLinker:
    def __init__(self, registered_pages=None):
        """
        registered_pages is a list of dicts:
        [
            {"post_type": "compare", "slug": "/compare/buzzstream-vs-linksprig", "title": "BuzzStream vs LinkSprig", "entity": "BuzzStream"},
            {"post_type": "industry", "slug": "/industry/link-building-software-for-saas", "title": "Link Building for SaaS", "entity": "SaaS"},
            ...
        ]
        """
        self.registered_pages = registered_pages or []

    def update_registered_pages(self, pages):
        self.registered_pages = pages

    def inject_links(self, post_type, body_sections):
        """
        Injects links into the body sections based on rules.
        Ensures 5-8 links per page by combining inline injections and a related links section.
        """
        injected_sections = []
        links_added = 0
        used_urls = set()

        # Define external static destinations for commercial CTAs
        static_destinations = {
            "pricing": "/pricing",
            "demo": "/demo",
            "signup": "/signup"
        }

        # Rule matching setup
        target_types = []
        if post_type == "compare":
            target_types = ["pricing", "demo"]
        elif post_type == "industry":
            target_types = ["use_case"]
        elif post_type == "problem":
            target_types = ["guide"]
        elif post_type == "guide":
            target_types = ["compare", "use_case"]
        elif post_type == "use_case":
            target_types = ["signup"]

        # 1. Contextual inline injection
        for section in body_sections:
            content = section["content"]
            
            # Match entities in registered pages or static targets
            for target_type in target_types:
                if target_type in static_destinations:
                    # Static link injection
                    url = static_destinations[target_type]
                    keyword = target_type.capitalize()
                    
                    if url not in used_urls and keyword in content:
                        # Replace first occurrence of the keyword that is not already inside an anchor tag
                        pattern = re.compile(rf'(?<!<a href=")(?<!>)\b{keyword}\b(?!</a>)', re.IGNORECASE)
                        content, count = pattern.subn(f'<a href="{url}">{keyword}</a>', content, count=1)
                        if count > 0:
                            used_urls.add(url)
                            links_added += 1
                else:
                    # Dynamic link injection from registered pages
                    for page in self.registered_pages:
                        if page["post_type"] == target_type and page["slug"] not in used_urls:
                            entity_name = page["entity"]
                            url = page["slug"]
                            
                            # Simple regex match for the entity name outside tags
                            pattern = re.compile(rf'(?<!<a href=")(?<!>)\b{re.escape(entity_name)}\b(?!</a>)', re.IGNORECASE)
                            content, count = pattern.subn(f'<a href="{url}">{entity_name}</a>', content, count=1)
                            if count > 0:
                                used_urls.add(url)
                                links_added += 1
            
            injected_sections.append({
                "heading": section["heading"],
                "content": content
            })

        # 2. Append Related Resources Section if we have less than 5 links
        # We need between 5 and 8 links total. Let's pull additional matching pages
        needed_links = max(0, 5 - links_added)
        extra_links_html = []
        
        # Pull candidate pages to link to
        candidates = []
        for target_type in target_types:
            if target_type in static_destinations:
                url = static_destinations[target_type]
                if url not in used_urls:
                    candidates.append({"title": f"LinkSprig {target_type.capitalize()}", "slug": url})
            else:
                for page in self.registered_pages:
                    url = page["slug"]
                    if page["post_type"] == target_type and url not in used_urls:
                        candidates.append({"title": page["title"], "slug": url})

        # If we still need more candidates to hit 5, pull from any other CPTs as fallback
        if len(candidates) < needed_links:
            for page in self.registered_pages:
                url = page["slug"]
                if url not in used_urls and url != f"/{post_type}/...": # Avoid self-linking
                    candidates.append({"title": page["title"], "slug": url})

        # Select candidates and append as "Related Resources"
        for cand in candidates[:max(needed_links, 6)]: # Cap at 8 total links (5-8 range)
            if links_added >= 8:
                break
            url = cand["slug"]
            title = cand["title"]
            extra_links_html.append(f'<li><a href="{url}">{title}</a></li>')
            used_urls.add(url)
            links_added += 1

        if extra_links_html:
            related_section_html = f"<h3>Recommended Resources</h3>\n<ul>\n" + "\n".join(extra_links_html) + "\n</ul>"
            # Append this related resources section to the last body section
            injected_sections[-1]["content"] += f"\n\n{related_section_html}"

        return injected_sections, links_added

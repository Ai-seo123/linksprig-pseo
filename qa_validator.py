import re

class QAValidator:
    def __init__(self, historical_intros=None):
        self.historical_intros = historical_intros or set()

    def add_historical_intro(self, intro_text):
        normalized = self._normalize_text(intro_text)
        if normalized:
            self.historical_intros.add(normalized[:80]) # Store first 80 chars of normalized text

    def _normalize_text(self, text):
        if not text:
            return ""
        # Remove HTML tags, multiple spaces, and convert to lowercase
        clean = re.sub(r'<[^>]*>', '', text)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip().lower()

    def validate_page(self, post_type, generated_data, competitor_data=None):
        """
        Validates the generated page against the QA rules.
        Returns:
            (bool, list): A tuple where the first element is True if valid, False otherwise,
                          and the second element is a list of rejection reasons.
        """
        reasons = []
        body_sections = generated_data.get("body_sections", [])
        intro = generated_data.get("intro", "")
        acf = generated_data.get("acf_fields", {})
        
        # Combined content for checks
        full_content = intro + " " + " ".join([s.get("content", "") for s in body_sections])
        plain_content = self._normalize_text(full_content)

        # 1. Duplicate Intro check
        norm_intro = self._normalize_text(intro)[:80]
        if norm_intro in self.historical_intros:
            reasons.append("Duplicate intro text: This intro pattern was already used in a previous page.")

        # 2. Thin Content Check
        word_count = len(plain_content.split())
        if word_count < 500:
            reasons.append(f"Thin content: Total word count is {word_count}, which is under the 500-word limit.")
            
        for idx, sec in enumerate(body_sections):
            sec_words = len(self._normalize_text(sec.get("content", "")).split())
            if sec_words < 50:
                reasons.append(f"Thin section: Section {idx+1} ('{sec.get('heading')}') has only {sec_words} words. Minimum is 50.")

        # 3. Weak EEAT Check (Check for numbers, statistics, bullet points, or year references)
        has_stats = any(char in plain_content for char in ['%', '$']) or any(str(year) in plain_content for year in range(2020, 2030))
        has_bullets = "<li>" in full_content or "<ul>" in full_content
        
        if not has_stats:
            reasons.append("Weak EEAT: Content lacks data, percentages, currency metrics, or recent year references.")
        if not has_bullets:
            reasons.append("Weak EEAT: Content lacks structural lists (bullet points or ordered lists) for readability.")

        # 4. Same CTA Repeated Check (CTA link or phrase repeated more than 3 times)
        cta_text = generated_data.get("cta_text", "")
        if cta_text:
            cta_count = plain_content.count(self._normalize_text(cta_text))
            if cta_count > 3:
                reasons.append(f"CTA repeated too often: The CTA phrase was found {cta_count} times in the body.")

        # 5. Factual Competitor Error (Check for competitor swaps or blank field values)
        if post_type == "compare" and competitor_data:
            comp_name = competitor_data.get("competitor", "")
            comp_strength = acf.get("competitor_strength", "")
            comp_weakness = acf.get("competitor_weakness", "")
            
            if not comp_name or comp_name.lower() not in plain_content:
                reasons.append(f"Factual competitor error: Target competitor '{comp_name}' is not mentioned in the body.")
            
            # Check if competitor details are blank or contain placeholder text
            if not comp_strength or len(comp_strength) < 10:
                reasons.append("Factual competitor error: Competitor strength is blank or too short.")
            if not comp_weakness or len(comp_weakness) < 10:
                reasons.append("Factual competitor error: Competitor weakness is blank or too short.")

        # 6. Keyword Overlap (Keyword stuffing check - e.g. 'LinkSprig' density > 6%)
        linksprig_count = plain_content.count("linksprig")
        total_words = len(plain_content.split())
        if total_words > 0:
            density = (linksprig_count / total_words) * 100
            if density > 6.0:
                reasons.append(f"Keyword stuffing: Brand term 'LinkSprig' density is {density:.2f}%, exceeding the 6% limit.")

        # 7. Low Differentiation / Missing Required Phrases
        required_phrases = ["feature pages", "product-led seo", "dr growth", "organic pipeline"]
        missing = [p for p in required_phrases if p not in plain_content]
        if missing:
            reasons.append(f"Low differentiation: Missing required brand/SEO anchor terms: {missing}")

        is_valid = len(reasons) == 0
        return is_valid, reasons

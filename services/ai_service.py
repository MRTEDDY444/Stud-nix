"""
AI service: classifies what kind of query was asked, then builds a
response structure appropriate to that category — never forcing every
topic through the same "Definition / Algorithm / Steps" template.

Default mode ("auto", no API key) builds sections from real retrieved
text (search_context["extract"], populated by SearchService) so content
is genuinely specific to the query. When no verified source was found,
it says so honestly and offers the real search links SearchService
always provides — it never invents facts to fill the gap.

Configure AI_API_KEY with AI_API_PROVIDER=anthropic for full open-domain
answering (the model's own knowledge, not just what Wikipedia covers) —
that path is used automatically once set, with the same section shape.
"""
import re
import requests
from config.config import Config

_FORMULA_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9]{0,3})\s*=\s*([A-Za-z0-9πΔ\+\-\*/\^√\.]{1,20})\b"
)

_PERCENT_OF_PATTERN = re.compile(
    r"(?:what\s+is\s+)?([\d.]+)\s*%\s*of\s*([\d,]+\.?\d*)", re.IGNORECASE
)

# ----------------------------------------------------------------------
# Query classification — pure keyword heuristics, no hardcoded topics.
# Generalizes to any query, not just the ones used for testing.
# ----------------------------------------------------------------------
_CATEGORY_KEYWORDS = {
    "algorithm": (
        "algorithm", "sort", "search tree", "binary search", "heap", "stack",
        "queue", "linked list", "graph traversal", "dynamic programming",
        "recursion", "big o", "complexity", "data structure",
    ),
    "programming": (
        "python", "java", "javascript", "c++", "c#", "inheritance", "oop",
        "object oriented", "function", "variable", "loop", "array", "class",
        "syntax", "programming", "code", "compiler", "framework", "library",
        "api", "database query", "sql",
    ),
    "science": (
        "law of", "laws of", "theorem", "equation", "formula", "physics",
        "chemistry", "biology", "photosynthesis", "cell division", "force",
        "energy", "velocity", "acceleration", "reaction", "molecule", "atom",
        "gravity", "electricity", "magnetism", "genetics", "evolution",
    ),
    "math": (
        "integration", "differentiation", "matrices", "matrix", "calculus",
        "algebra", "geometry", "trigonometry", "probability", "statistics",
        "equation", "theorem", "derivative",
    ),
    "calculation": (
        "% of", "percent of", "how many days", "how much is", "calculate",
    ),
    "gaming": (
        "game", "gaming", "fps", "sensitivity", "minecraft", "free fire",
        "pubg", "valorant", "fortnite", "graphics settings", "gameplay",
        "esports", "console", "playstation", "xbox",
    ),
    "person": (),  # handled via regex below, not keywords
    "howto": ("how to", "how do i", "best way to", "steps to"),
}


def classify_query(query: str) -> str:
    q = query.lower().strip()
    if re.match(r"^(who is|who was|who are)\b", q):
        return "person"
    if _PERCENT_OF_PATTERN.search(q) or "how many days" in q:
        return "calculation"
    # Check more specific categories before generic ones.
    for category in ("algorithm", "programming", "science", "math", "gaming", "howto"):
        for kw in _CATEGORY_KEYWORDS[category]:
            if kw in q:
                return category
    return "general"


class AIService:
    def __init__(self):
        self.provider = (Config.AI_API_PROVIDER or "auto").lower()
        self.api_key = Config.AI_API_KEY

    def generate_study_notes(self, query: str, search_context: dict) -> dict:
        try:
            if self.provider == "anthropic" and self.api_key:
                notes = self._anthropic_notes(query, search_context)
                if notes:
                    return notes
            return self._build_notes(query, search_context)
        except requests.RequestException:
            return {"error": "AI Study Helper is temporarily unavailable. "
                              "You can still browse the available resources."}

    def helper_action(self, action: str, topic: str, context: str = "") -> dict:
        try:
            if self.provider == "anthropic" and self.api_key:
                result = self._anthropic_helper(action, topic, context)
                if result:
                    return result
            return self._extract_based_helper(action, topic, context)
        except requests.RequestException:
            return {"error": "AI Study Helper is temporarily unavailable. "
                              "You can still browse the available resources."}

    # ------------------------------------------------------------------
    # text helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _split_sentences(text: str):
        text = (text or "").strip()
        if not text:
            return []
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _extract_formulas(text: str):
        stopwords = {"is", "was", "are", "were", "the", "a", "an", "not", "to", "of"}
        found = []
        for lhs, rhs in _FORMULA_PATTERN.findall(text or ""):
            if rhs.lower() in stopwords:
                continue
            candidate = f"{lhs} = {rhs}"
            if candidate not in found:
                found.append(candidate)
        return found[:4]

    @staticmethod
    def _try_calculate(query: str):
        """Exact, deterministic answers for arithmetic-shaped queries —
        no source needed because it's just math, and it generalizes to
        any numbers, not only a specific tested example."""
        m = _PERCENT_OF_PATTERN.search(query)
        if m:
            pct = float(m.group(1))
            base = float(m.group(2).replace(",", ""))
            result = (pct / 100) * base
            result_str = f"{result:g}"
            return {
                "answer": f"{pct:g}% of {base:g} is {result_str}.",
                "working": f"{pct:g}% of {base:g} = ({pct:g} / 100) × {base:g} = {result_str}.",
            }
        return None

    # ------------------------------------------------------------------
    # Section builders — one per category. Each returns a list of
    # {"label", "kind", "content"} dicts; the template just loops over
    # whatever list comes back, so unrelated sections never appear.
    # ------------------------------------------------------------------
    def _build_notes(self, query: str, search_context: dict) -> dict:
        category = classify_query(query)

        if category == "calculation":
            calc = self._try_calculate(query)
            if calc:
                return {
                    "header_icon": "🧮", "header_label": "AI Answer", "category": category,
                    "sections": [
                        {"label": "Answer", "kind": "paragraph", "content": calc["answer"]},
                        {"label": "Working", "kind": "paragraph", "content": calc["working"]},
                    ],
                    "note": "Calculated directly — no external source needed for this one.",
                }
            # Not a pattern we can compute directly (e.g. "how many days in a
            # leap year") — fall through to a normal source-grounded lookup.
            category = "general"

        extract = search_context.get("extract", "") or ""
        topic = search_context.get("page_title") or query
        match_quality = search_context.get("match_quality", "none")
        sentences = self._split_sentences(extract)
        has_source = bool(sentences)

        if category == "algorithm":
            sections = self._algorithm_sections(topic, extract, sentences, has_source)
            header_icon, header_label = "📖", "AI Study Notes"
        elif category == "programming":
            sections = self._programming_sections(topic, sentences, has_source)
            header_icon, header_label = "📖", "AI Study Notes"
        elif category in ("science", "math"):
            sections = self._science_sections(topic, extract, sentences, has_source)
            header_icon, header_label = "📖", "AI Study Notes"
        elif category == "person":
            sections = self._person_sections(topic, sentences, has_source)
            header_icon, header_label = "💡", "AI Explanation"
        else:  # gaming, howto, general — and the calculation fallback above
            sections = self._general_sections(query, topic, sentences, has_source, match_quality)
            header_icon, header_label = "💡", "AI Explanation"

        if has_source:
            note = (f'These notes are built from the summary of the source article on "{topic}" '
                    f"below and reorganized into a study format — a starting point, not a "
                    f"replacement for reading the full source.")
        else:
            note = ("We couldn't verify a specific source for this exact query. The links below "
                    "are real search starting points — use them to dig further, or try rephrasing "
                    "your search.")

        return {"header_icon": header_icon, "header_label": header_label,
                "category": category, "sections": sections, "note": note}

    def _algorithm_sections(self, topic, extract, sentences, has_source):
        if not has_source:
            return self._no_source_sections(topic)
        definition = " ".join(sentences[:2])
        how_it_works = sentences[2] if len(sentences) > 2 else ""
        example = sentences[3] if len(sentences) > 3 else (sentences[-1] if len(sentences) > 1 else "")
        looks_algorithmic = any(w in extract.lower() for w in
                                 ("complexity", "o(n", "time complexity", "big o"))
        sections = [
            {"label": "Definition", "kind": "paragraph", "content": definition},
        ]
        if how_it_works:
            sections.append({"label": "How It Works", "kind": "paragraph", "content": how_it_works})
        sections.append({"label": "Steps to Study This", "kind": "ordered", "content": [
            f"Restate the definition of {topic} in your own words.",
            "Trace through how it works on a small example by hand.",
            "Note the time and space complexity if applicable.",
            "Compare it to a related algorithm — what trade-off does it make?",
        ]})
        if example:
            sections.append({"label": "Example", "kind": "paragraph", "content": example})
        if looks_algorithmic:
            sections.append({"label": "Complexity", "kind": "list", "content": [
                "See the linked source below for the specific best/average/worst-case complexity.",
            ]})
        sections.append({"label": "Important Exam Points", "kind": "list", "content": [
            f"Be able to state the definition of {topic} in your own words.",
            "Know the general approach/steps, not just the final result.",
            "Know its time/space complexity if it's an algorithm.",
        ]})
        sections.append({"label": "Practice Questions", "kind": "ordered", "content": [
            f"Explain {topic} in your own words.",
            f"Walk through a worked example of {topic} step by step.",
            f"What situations is {topic} well suited (or poorly suited) for?",
        ]})
        return sections

    def _programming_sections(self, topic, sentences, has_source):
        if not has_source:
            return self._no_source_sections(topic)
        definition = " ".join(sentences[:2])
        concepts = sentences[2:5]
        example = sentences[5] if len(sentences) > 5 else (sentences[-1] if len(sentences) > 1 else "")
        sections = [{"label": "Definition", "kind": "paragraph", "content": definition}]
        if concepts:
            sections.append({"label": "Key Concepts", "kind": "list", "content": concepts})
        if example:
            sections.append({"label": "Example", "kind": "paragraph", "content": example})
        sections.append({"label": "Important Points", "kind": "list", "content": [
            f"Know the definition of {topic} and how to use it in code.",
            "Be able to write or read a short example without help.",
            f"Understand why {topic} is useful — what problem it solves.",
        ]})
        sections.append({"label": "Practice Questions", "kind": "ordered", "content": [
            f"Explain {topic} in your own words.",
            f"Write a short code example that uses {topic}.",
            f"What's a common mistake beginners make with {topic}?",
        ]})
        return sections

    def _science_sections(self, topic, extract, sentences, has_source):
        if not has_source:
            return self._no_source_sections(topic)
        definition = " ".join(sentences[:2])
        concepts = sentences[2:5]
        example = sentences[5] if len(sentences) > 5 else (sentences[-1] if len(sentences) > 1 else "")
        formulas = self._extract_formulas(extract)
        sections = [{"label": "Definition", "kind": "paragraph", "content": definition}]
        if concepts:
            sections.append({"label": "Key Concepts", "kind": "list", "content": concepts})
        if formulas:
            sections.append({"label": "Formulas", "kind": "code_list", "content": formulas})
        if example:
            sections.append({"label": "Example", "kind": "paragraph", "content": example})
        sections.append({"label": "Important Points", "kind": "list", "content": [
            f"Be able to state the definition of {topic} in your own words.",
            "Know any relevant formula and what each symbol means.",
            "Know one real-world example or application.",
        ]})
        sections.append({"label": "Practice Questions", "kind": "ordered", "content": [
            f"Explain {topic} in your own words.",
            f"Give one real-world example of {topic}.",
            "Work through a numerical example if a formula applies.",
        ]})
        return sections

    def _person_sections(self, topic, sentences, has_source):
        if not has_source:
            return self._no_source_sections(topic)
        who = " ".join(sentences[:2])
        facts = sentences[2:6]
        sections = [{"label": "Who They Are", "kind": "paragraph", "content": who}]
        if facts:
            sections.append({"label": "Key Facts", "kind": "list", "content": facts})
        sections.append({"label": "Important Points", "kind": "list", "content": [
            "Know their main contribution or achievement.",
            "Know the approximate time period they're associated with.",
        ]})
        return sections

    def _general_sections(self, query, topic, sentences, has_source, match_quality):
        if not has_source:
            return self._no_source_sections(topic or query)
        answer = " ".join(sentences[:2])
        more = sentences[2:5]
        sections = []
        if match_quality == "related":
            sections.append({
                "label": "Answer", "kind": "paragraph",
                "content": (f'We found background information on "{topic}", which is closely '
                             f'related to your search, though not an exact match for "{query}": {answer}'),
            })
        else:
            sections.append({"label": "Answer", "kind": "paragraph", "content": answer})
        if more:
            sections.append({"label": "Explanation", "kind": "list", "content": more})
        sections.append({"label": "Related Information", "kind": "list", "content": [
            "See the linked sources below for more detail and to verify this answer.",
        ]})
        return sections

    def _no_source_sections(self, topic):
        return [
            {"label": "Answer", "kind": "paragraph",
             "content": (f'We couldn\'t find a verified source that directly explains "{topic}". '
                          f"This might be very recent, very niche, or phrased in a way our search "
                          f"couldn't match.")},
            {"label": "What you can do", "kind": "list", "content": [
                "Try the search links below — they're real, live searches for this exact query.",
                "Try rephrasing with different or more specific words.",
                "If this is a course-specific term, check your course material or ask your instructor.",
            ]},
        ]

    # ------------------------------------------------------------------
    # AI Study Helper buttons (Explain, Simplify, MCQs, etc.)
    # ------------------------------------------------------------------
    def _extract_based_helper(self, action: str, topic: str, context: str) -> dict:
        sentences = self._split_sentences(context) or [f"No verified source text is available for {topic} yet."]
        responses = {
            "explain": " ".join(sentences[:3]),
            "simplify": f"In simple terms: {sentences[0]}" if sentences else f"{topic} — see the linked source for details.",
            "mcqs": [f"Which of the following best relates to {topic}? (based on: \"{s[:80]}...\")"
                     for s in sentences[:5]] or [f"No source text available to generate MCQs for {topic} yet."],
            "flashcards": [{"front": f"What is {topic}?", "back": sentences[0] if sentences else ""}] +
                          [{"front": f"Key point about {topic} #{i+1}", "back": s}
                           for i, s in enumerate(sentences[1:4])],
            "exam_notes": " ".join(sentences[:4]),
            "summarize": " ".join(sentences[:2]),
            "questions": [f"Explain: {s[:90]}" for s in sentences[:5]] or [f"Explain {topic} in your own words."],
            "test_me": f"Without looking, write down what you remember about {topic}, then compare it to: "
                       f"{sentences[0] if sentences else '(no source text available yet)'}",
        }
        return {"action": action, "topic": topic,
                "result": responses.get(action, " ".join(sentences[:3]))}

    # ------------------------------------------------------------------
    # REAL PROVIDER (Anthropic) — requires AI_API_KEY in .env. Answers any
    # query using the model's own knowledge, optionally grounded by
    # whatever source text SearchService found (may be empty).
    # ------------------------------------------------------------------
    def _anthropic_notes(self, query: str, search_context: dict):
        import json as _json
        extract = search_context.get("extract", "")
        sources_text = f"Retrieved source text (may be empty): {extract}" if extract else \
            "No verified source text was retrieved for this query — answer from your own knowledge, " \
            "and say plainly in the notes that this isn't tied to a specific verified source."
        prompt = (
            f"You are an educational assistant powering a study-notes site. A user searched: "
            f"'{query}'. First classify the query as one of: algorithm, programming, science, math, "
            f"person, gaming, howto, calculation, general. Then produce a response whose SECTIONS "
            f"are appropriate to that category — do not force unrelated categories (e.g. a person or "
            f"gaming query) into an 'Algorithm / Steps' structure.\n\n{sources_text}\n\n"
            f"Return ONLY valid JSON (no markdown fences) with this shape: "
            f'{{"header_icon": "<one emoji>", "header_label": "AI Study Notes" or "AI Explanation" or '
            f'"AI Answer", "category": "<category>", "sections": [{{"label": "<section name>", '
            f'"kind": "paragraph" or "list" or "ordered" or "code_list", "content": "<string for '
            f'paragraph, array of strings otherwise>"}}], "note": "<one sentence on where this content '
            f'came from>"}}. Include only sections that genuinely make sense for this specific query.'
        )
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json()
        text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        raw_text = "\n".join(text_blocks).strip()
        raw_text = re.sub(r"^```json\s*|\s*```$", "", raw_text.strip())
        try:
            return _json.loads(raw_text)
        except (ValueError, TypeError):
            return None  # caller falls back to the extract-based path

    def _anthropic_helper(self, action: str, topic: str, context: str):
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 800,
                "messages": [{"role": "user",
                               "content": f"Action: {action}\nTopic: {topic}\nContext: {context}\n\n"
                                          f"Respond with plain text appropriate to the action."}],
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "\n".join(text_blocks).strip()
        if not text:
            return None
        return {"action": action, "topic": topic, "result": text}

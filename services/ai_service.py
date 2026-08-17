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
from services.math_service import solve_math

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
    "debugging": (
        "debug", "why is my code", "why is this code", "fix this code", "fix my code",
        "error in my code", "indexerror", "syntaxerror", "typeerror", "nameerror",
        "valueerror", "keyerror", "attributeerror", "runtime error", "traceback",
        "what does this error mean", "giving an error", "throwing an error",
    ),
    "coding_request": (
        "write a program", "write code", "write a function", "write a python",
        "write a java", "write a c program", "write a c++ program", "generate code",
        "code to ", "program to ", "convert this code", "optimize this code",
        "improve this code", "explain this code", "explain the code",
    ),
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
    if solve_math(query) is not None:
        return "calculation"
    # Check more specific categories before generic ones — debugging/coding
    # before "programming" so "debug this Python code" isn't just filed as
    # a generic Python explanation.
    for category in ("debugging", "coding_request", "algorithm", "programming",
                      "science", "math", "gaming", "howto"):
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
    def _calc_sections(calc: dict):
        sections = [{"label": "Given", "kind": "paragraph", "content": calc["given"]}]
        if calc.get("formula"):
            sections.append({"label": "Formula", "kind": "paragraph", "content": calc["formula"]})
        sections.append({"label": "Calculation", "kind": "paragraph", "content": calc["calculation"]})
        sections.append({"label": "Final Answer", "kind": "paragraph", "content": calc["answer"]})
        return sections

    def try_direct_answer(self, query: str):
        """Answers a query directly with no web search at all — currently
        covers math/calculation. Returns a full notes dict, or None if
        this query needs the normal search-and-classify path instead.
        Called by the route BEFORE SearchService runs, so a calculation
        never gets accidentally matched against an unrelated article."""
        calc = solve_math(query)
        if not calc:
            return None
        return {
            "header_icon": "🧮", "header_label": "AI Answer", "category": "calculation",
            "sections": self._calc_sections(calc),
            "note": "Calculated directly — no external source needed for this one.",
        }

    # ------------------------------------------------------------------
    # Section builders — one per category. Each returns a list of
    # {"label", "kind", "content"} dicts; the template just loops over
    # whatever list comes back, so unrelated sections never appear.
    # ------------------------------------------------------------------
    def _build_notes(self, query: str, search_context: dict) -> dict:
        category = classify_query(query)

        if category == "calculation":
            calc = solve_math(query)
            if calc:
                return {
                    "header_icon": "🧮", "header_label": "AI Answer", "category": category,
                    "sections": self._calc_sections(calc),
                    "note": "Calculated directly — no external source needed for this one.",
                }
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
        elif category == "coding_request":
            sections = self._coding_request_sections(query, topic, sentences, has_source)
            header_icon, header_label = "💻", "AI Coding Help"
        elif category == "debugging":
            sections = self._debugging_sections(query, topic, sentences, has_source)
            header_icon, header_label = "🐛", "AI Debug Help"
        elif category in ("science", "math"):
            sections = self._science_sections(topic, extract, sentences, has_source)
            header_icon, header_label = "📖", "AI Study Notes"
        elif category == "person":
            sections = self._person_sections(topic, sentences, has_source)
            header_icon, header_label = "💡", "AI Explanation"
        else:  # gaming, howto, general
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

    def _coding_request_sections(self, query, topic, sentences, has_source):
        sections = [{
            "label": "Answer", "kind": "paragraph",
            "content": ("Generating correct, working code for a new request needs a real AI model. "
                        "This install is running without one configured (AI_API_PROVIDER=anthropic "
                        "with AI_API_KEY set enables it) — so here's what's available without it:"),
        }]
        if has_source:
            sections.append({"label": "Background", "kind": "paragraph",
                              "content": " ".join(sentences[:2])})
        sections.append({"label": "What you can do", "kind": "list", "content": [
            "Open the Coding Playground to write and run your own code.",
            "Configure AI_API_KEY for full code generation, debugging, and code conversion.",
            "See the linked sources below for reference implementations.",
        ]})
        return sections

    def _debugging_sections(self, query, topic, sentences, has_source):
        sections = [{
            "label": "Problem", "kind": "paragraph",
            "content": ("Diagnosing an actual error needs to see your code and the exact error "
                        "message, and reliably suggesting a fix needs a real AI model. This install "
                        "is running without one configured — set AI_API_KEY with "
                        "AI_API_PROVIDER=anthropic to enable full debugging support."),
        }]
        sections.append({"label": "In the meantime", "kind": "list", "content": [
            "Paste the full error traceback — the last line usually names the exact error type.",
            "Check the line number in the traceback first; that's almost always where the problem is.",
            "Try the Coding Playground to isolate and re-run just the failing part.",
        ]})
        if has_source:
            sections.append({"label": "Background", "kind": "paragraph",
                              "content": " ".join(sentences[:2])})
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

    def code_assist(self, action: str, code: str, language: str = "python") -> dict:
        """Powers the Coding Playground's Explain / Debug / Improve /
        Convert buttons. Without a real AI key this can't reliably
        generate or rewrite code — it says so plainly rather than
        guessing — but syntax errors ARE checked for real via the same
        AST parser the sandbox itself uses, since that's just parsing,
        not generation."""
        try:
            if self.provider == "anthropic" and self.api_key:
                result = self._anthropic_code_assist(action, code, language)
                if result:
                    return result
            return self._fallback_code_assist(action, code, language)
        except requests.RequestException:
            return {"error": "AI Study Helper is temporarily unavailable. "
                              "You can still run your code above."}

    def _fallback_code_assist(self, action: str, code: str, language: str) -> dict:
        labels = {
            "explain_code": "Explaining code",
            "debug_code": "Debugging code",
            "improve_code": "Improving code",
            "convert_code": "Converting code",
        }
        note = (f"{labels.get(action, 'This')} reliably for arbitrary code needs a real AI "
                f"model — set AI_API_KEY with AI_API_PROVIDER=anthropic to enable it.")
        if action == "debug_code" and language == "python":
            import ast as _ast
            try:
                _ast.parse(code)
                syntax_note = "No syntax errors found by Python's own parser — if it's still " \
                               "failing, the problem is likely a runtime issue (check the " \
                               "Output panel after running it)."
            except SyntaxError as e:
                syntax_note = f"Syntax error found: {e.msg} (line {e.lineno})."
            return {"action": action, "result": f"{syntax_note}\n\n{note}"}
        return {"action": action, "result": note}

    def _anthropic_code_assist(self, action: str, code: str, language: str):
        instructions = {
            "explain_code": "Explain what this code does, ideally line by line for the non-obvious parts.",
            "debug_code": "Find the bug or likely cause of an error in this code, and provide corrected code.",
            "improve_code": "Suggest concrete improvements to this code and provide an improved version.",
            "convert_code": f"Convert this {language} code to an equivalent in another common "
                             f"language, and say clearly which language you chose.",
        }
        prompt = (
            f"{instructions.get(action, 'Help with this code.')}\n\nLanguage: {language}\n\n"
            f"Code:\n```{language}\n{code}\n```\n\nRespond in plain text, including any corrected "
            f"or new code in a fenced code block."
        )
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": "claude-sonnet-4-6", "max_tokens": 1200,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=25,
        )
        resp.raise_for_status()
        data = resp.json()
        text_blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "\n".join(text_blocks).strip()
        if not text:
            return None
        return {"action": action, "result": text}

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
            f"You are an AI assistant powering a student site that solves problems, writes code, "
            f"debugs code, and explains topics — like ChatGPT/Claude, not a topic-lookup tool. A "
            f"user asked: '{query}'. First classify the query as one of: calculation, algorithm, "
            f"programming, coding_request, debugging, science, math, person, gaming, howto, general. "
            f"Then produce a response whose SECTIONS are appropriate to that category — do not force "
            f"unrelated categories into an unrelated structure. If the query asks to solve, compute, "
            f"or calculate something, actually perform the calculation and show the result — don't "
            f"describe what calculation/problem-solving is in the abstract. If it's a coding_request, "
            f"actually write the code (in a 'code' kind section) and explain it. If it's debugging, "
            f"explain the likely cause and give corrected code.\n\n{sources_text}\n\n"
            f"Return ONLY valid JSON (no markdown fences) with this shape: "
            f'{{"header_icon": "<one emoji>", "header_label": "AI Study Notes" or "AI Explanation" or '
            f'"AI Answer" or "AI Coding Help" or "AI Debug Help", "category": "<category>", '
            f'"sections": [{{"label": "<section name>", "kind": "paragraph" or "list" or "ordered" or '
            f'"code" or "code_list", "content": "<string for paragraph/code, array of strings '
            f'otherwise>"}}], "note": "<one sentence on where this content came from>"}}. Include only '
            f"sections that genuinely make sense for this specific query."
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

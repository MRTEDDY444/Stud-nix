from flask import Blueprint, render_template, request, jsonify

from services.search_service import SearchService
from services.ai_service import AIService
from models.models import log_search

search_bp = Blueprint("search", __name__)
search_service = SearchService()
ai_service = AIService()


@search_bp.route("/search")
def search_page():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("search.html", query="", results=None, notes=None, error=None)

    # Calculations are answered directly and never touch web search — this
    # is what stops "Solve 2!" from accidentally matching an unrelated
    # "Problem solving" article and showing its definition instead of 2.
    notes = ai_service.try_direct_answer(query)
    if notes:
        results = {"query": query, "web": [], "pdfs": [], "videos": [],
                   "provider": "calculator", "error": None}
        log_search(query, "calculator")
        return render_template("search.html", query=query, results=results,
                                notes=notes, error=None)

    results = search_service.search(query)
    log_search(query, results.get("provider", "mock"))

    notes = None
    if not results.get("error"):
        notes = ai_service.generate_study_notes(query, results)

    return render_template(
        "search.html",
        query=query,
        results=results,
        notes=notes,
        error=results.get("error"),
    )


@search_bp.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    results = search_service.search(query)
    return jsonify(results)


@search_bp.route("/api/ai-helper", methods=["POST"])
def api_ai_helper():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "explain")
    topic = data.get("topic", "")
    context = data.get("context", "")
    if not topic:
        return jsonify({"error": "A topic is required."}), 400
    result = ai_service.helper_action(action, topic, context)
    if "error" in result:
        return jsonify(result), 503
    return jsonify(result)

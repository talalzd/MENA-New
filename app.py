"""
MENA Policy & Regulatory Monitor — Flask Application
"""

import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

import config
import db
import fetcher

app = Flask(__name__)
app.secret_key = os.urandom(24)


@app.before_request
def ensure_db():
    """Initialize DB on first request."""
    if not hasattr(app, "_db_initialized"):
        db.init_db()
        app._db_initialized = True


@app.context_processor
def inject_globals():
    """Inject global template variables."""
    return {
        "unread_count": db.get_unread_count(),
        "countries": config.COUNTRIES,
        "topics": config.TOPICS,
        "country_flags": config.COUNTRY_FLAGS,
        "now": datetime.utcnow(),
    }


# ---------- Pages ----------

@app.route("/")
def dashboard():
    stats = db.get_dashboard_stats()
    recent = db.get_updates(limit=5)
    consultations = db.get_consultations()
    active_consultations = [c for c in consultations if not c["is_expired"]][:5]
    return render_template("dashboard.html",
                           stats=stats,
                           recent=recent,
                           active_consultations=active_consultations)


@app.route("/feed")
def feed():
    country = request.args.get("country")
    topic = request.args.get("topic")
    unread_only = request.args.get("unread") == "1"
    search = request.args.get("q", "").strip()
    updates = db.get_updates(country=country, topic=topic, unread_only=unread_only)
    # Client-side search — filter by title/summary containing the query
    if search:
        q = search.lower()
        updates = [u for u in updates if q in (u["title"] or "").lower()
                   or q in (u["summary"] or "").lower()]
    return render_template("feed.html",
                           updates=updates,
                           selected_country=country,
                           selected_topic=topic,
                           unread_filter=unread_only,
                           search_query=search)


@app.route("/consultations")
def consultations():
    items = db.get_consultations()
    country = request.args.get("country")
    if country:
        items = [i for i in items if i["country"] == country]
    active = [i for i in items if not i["is_expired"]]
    expired = [i for i in items if i["is_expired"]]
    return render_template("consultations.html",
                           active=active, expired=expired,
                           selected_country=country)


@app.route("/starred")
def starred():
    updates = db.get_updates(starred_only=True)
    return render_template("starred.html", updates=updates)


@app.route("/add-clip", methods=["GET", "POST"])
def add_clip():
    if request.method == "POST":
        data = {
            "title": request.form.get("title", "").strip(),
            "url": request.form.get("url", "").strip(),
            "country": request.form.get("country") or None,
            "topic": request.form.get("topic") or None,
            "summary": request.form.get("summary", "").strip(),
            "source_name": "Manual Clip",
            "published_date": datetime.utcnow().isoformat(),
            "is_consultation": 1 if request.form.get("is_consultation") else 0,
            "consultation_deadline": request.form.get("consultation_deadline") or None,
            "issuing_authority": request.form.get("issuing_authority", "").strip() or None,
            "is_manual": 1,
        }

        if not data["title"] or not data["url"]:
            flash("Title and URL are required.", "error")
            return render_template("add_clip.html", data=data)

        db.insert_update(data)
        flash("Clip added successfully.", "success")
        return redirect(url_for("feed"))

    return render_template("add_clip.html", data={})


@app.route("/sources")
def sources():
    all_sources = db.get_sources()
    return render_template("sources.html", sources=all_sources)


@app.route("/sources/add", methods=["POST"])
def sources_add():
    data = {
        "name": request.form.get("name", "").strip(),
        "url": request.form.get("url", "").strip(),
        "source_type": request.form.get("source_type", "rss"),
        "country": request.form.get("country") or None,
        "default_topic": request.form.get("default_topic") or None,
    }
    if not data["name"] or not data["url"]:
        flash("Name and URL are required.", "error")
    elif db.add_source(data):
        flash(f"Source '{data['name']}' added.", "success")
    else:
        flash("Source with that URL already exists.", "error")
    return redirect(url_for("sources"))


@app.route("/sources/toggle/<int:source_id>", methods=["POST"])
def sources_toggle(source_id):
    new_state = db.toggle_source(source_id)
    return jsonify({"active": new_state})


# ---------- API ----------

@app.route("/api/stats")
def api_stats():
    """Dashboard stats as JSON (for AJAX refresh)."""
    return jsonify(db.get_dashboard_stats())


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Start a background refresh (returns immediately)."""
    result = fetcher.start_refresh()
    return jsonify(result)


@app.route("/api/refresh/status")
def api_refresh_status():
    """Poll for refresh progress."""
    return jsonify(fetcher.get_refresh_status())


@app.route("/api/refresh/errors")
def api_refresh_errors():
    """Return detailed error info from the last refresh."""
    status = fetcher.get_refresh_status()
    if status.get("result"):
        return jsonify({"errors": status["result"].get("errors", [])})
    return jsonify({"errors": []})


@app.route("/api/test-source/<int:source_id>")
def api_test_source(source_id):
    """Test fetching a single source and return diagnostic info."""
    import time
    source = db.get_source_by_id(source_id)
    if not source:
        return jsonify({"error": "Source not found"}), 404

    start = time.time()
    try:
        resp = fetcher.SESSION.get(source["url"], timeout=fetcher.REQUEST_TIMEOUT)
        elapsed = round(time.time() - start, 2)
        return jsonify({
            "source": source["name"],
            "url": source["url"],
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type", ""),
            "content_length": len(resp.content),
            "elapsed_seconds": elapsed,
            "response_snippet": resp.text[:500] if resp.text else "",
        })
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        return jsonify({
            "source": source["name"],
            "url": source["url"],
            "error": str(e),
            "elapsed_seconds": elapsed,
        })


@app.route("/api/star/<int:update_id>", methods=["POST"])
def api_star(update_id):
    new_state = db.toggle_star(update_id)
    return jsonify({"is_starred": new_state})


@app.route("/api/read/<int:update_id>", methods=["POST"])
def api_read(update_id):
    new_state = db.toggle_read(update_id)
    return jsonify({"is_read": new_state})


# ---------- Template Filters ----------

@app.template_filter("timeago")
def timeago_filter(dt_str):
    """Convert ISO date string to relative time."""
    if not dt_str:
        return ""
    try:
        from dateutil import parser as dp
        dt = dp.parse(dt_str)
        now = datetime.utcnow()
        diff = now - dt.replace(tzinfo=None)

        seconds = int(diff.total_seconds())
        if seconds < 0:
            return dt_str[:10]
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            m = seconds // 60
            return f"{m}m ago"
        if seconds < 86400:
            h = seconds // 3600
            return f"{h}h ago"
        days = seconds // 86400
        if days == 1:
            return "yesterday"
        if days < 30:
            return f"{days}d ago"
        return dt_str[:10]
    except Exception:
        return dt_str[:10] if dt_str else ""


@app.template_filter("daysuntil")
def daysuntil_filter(date_str):
    """Show days remaining until a deadline."""
    if not date_str:
        return ""
    try:
        from dateutil import parser as dp
        dt = dp.parse(date_str).replace(tzinfo=None)
        diff = (dt - datetime.utcnow()).days
        if diff < 0:
            return f"Expired {abs(diff)}d ago"
        if diff == 0:
            return "Today"
        if diff == 1:
            return "Tomorrow"
        return f"{diff} days remaining"
    except Exception:
        return ""


@app.template_filter("shortdate")
def shortdate_filter(dt_str):
    """Format ISO date as short date like 'Mar 24'."""
    if not dt_str:
        return ""
    try:
        from dateutil import parser as dp
        dt = dp.parse(dt_str)
        return dt.strftime("%b %d")
    except Exception:
        return dt_str[:10] if dt_str else ""


if __name__ == "__main__":
    db.init_db()
    app.run(host="0.0.0.0", port=5000)

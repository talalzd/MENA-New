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
def feed():
    country = request.args.get("country")
    topic = request.args.get("topic")
    unread_only = request.args.get("unread") == "1"
    updates = db.get_updates(country=country, topic=topic, unread_only=unread_only)
    return render_template("feed.html",
                           updates=updates,
                           selected_country=country,
                           selected_topic=topic,
                           unread_filter=unread_only)


@app.route("/consultations")
def consultations():
    items = db.get_consultations()
    active = [i for i in items if not i["is_expired"]]
    expired = [i for i in items if i["is_expired"]]
    return render_template("consultations.html", active=active, expired=expired)


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

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    result = fetcher.fetch_all_sources()
    return jsonify(result)


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


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5000)

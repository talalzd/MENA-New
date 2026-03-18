"""
MENA Policy & Regulatory Monitor — Database Layer
SQLite database setup, queries, and helpers.
"""

import sqlite3
from datetime import datetime

import config


def get_conn():
    conn = sqlite3.connect(config.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            url         TEXT NOT NULL UNIQUE,
            source_type TEXT NOT NULL DEFAULT 'rss',
            country     TEXT,
            default_topic TEXT,
            active      INTEGER NOT NULL DEFAULT 1,
            last_fetched TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS updates (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT NOT NULL,
            url             TEXT NOT NULL UNIQUE,
            source_name     TEXT,
            source_id       INTEGER,
            country         TEXT,
            topic           TEXT,
            summary         TEXT,
            published_date  TEXT,
            fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
            is_consultation INTEGER NOT NULL DEFAULT 0,
            consultation_deadline TEXT,
            issuing_authority TEXT,
            is_read         INTEGER NOT NULL DEFAULT 0,
            is_starred      INTEGER NOT NULL DEFAULT 0,
            is_manual       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (source_id) REFERENCES sources(id)
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_updates_country ON updates(country)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_updates_topic ON updates(topic)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_updates_consultation ON updates(is_consultation)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_updates_starred ON updates(is_starred)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_updates_read ON updates(is_read)")

    # Deactivate broken sources (unreachable gov sites & dead SPA RSS)
    broken_urls = [
        "https://istitlaa.ncc.gov.sa/ar/Pages/default.aspx",
        "https://u.ae/en/participate/consultations",
        "https://tdra.gov.ae/en/Participation/consultations",
        "https://uaelegislation.gov.ae/en",
        "https://www.errada.gov.eg/",
        "https://www.egypt.gov.eg/english/laws/default.aspx",
        "https://www.tra.gov.eg/en/",
        "https://www.spa.gov.sa/rss.xml",
        "https://www.spa.gov.sa/rss5.xml",
        "https://www.spa.gov.sa/rss4.xml",
        "https://www.arabnews.com/rss.xml",
    ]
    for url in broken_urls:
        c.execute("UPDATE sources SET active = 0 WHERE url = ?", (url,))

    # Pre-populate sources (inserts new ones, skips existing)
    for src in config.DEFAULT_SOURCES:
        c.execute("""
            INSERT OR IGNORE INTO sources (name, url, source_type, country, default_topic)
            VALUES (?, ?, ?, ?, ?)
        """, (src["name"], src["url"], src["source_type"], src.get("country"), src.get("default_topic")))

    conn.commit()
    conn.close()


def insert_update(data):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO updates
                (title, url, source_name, source_id, country, topic, summary,
                 published_date, is_consultation, consultation_deadline,
                 issuing_authority, is_manual)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("title", ""),
            data["url"],
            data.get("source_name"),
            data.get("source_id"),
            data.get("country"),
            data.get("topic"),
            data.get("summary"),
            data.get("published_date"),
            data.get("is_consultation", 0),
            data.get("consultation_deadline"),
            data.get("issuing_authority"),
            data.get("is_manual", 0),
        ))
        conn.commit()
        return conn.total_changes
    finally:
        conn.close()


def get_updates(country=None, topic=None, consultations_only=False,
                starred_only=False, unread_only=False, limit=200):
    conn = get_conn()
    query = "SELECT * FROM updates WHERE 1=1"
    params = []

    if country:
        query += " AND country = ?"
        params.append(country)
    if topic:
        query += " AND topic = ?"
        params.append(topic)
    if consultations_only:
        query += " AND is_consultation = 1"
    if starred_only:
        query += " AND is_starred = 1"
    if unread_only:
        query += " AND is_read = 0"

    query += " ORDER BY published_date DESC, fetched_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_consultations():
    conn = get_conn()
    rows = conn.execute("""
        SELECT *,
            CASE
                WHEN consultation_deadline IS NOT NULL AND consultation_deadline >= date('now')
                    THEN 0
                ELSE 1
            END as is_expired,
            CASE
                WHEN consultation_deadline IS NOT NULL
                    THEN julianday(consultation_deadline) - julianday('now')
                ELSE 9999
            END as days_remaining
        FROM updates
        WHERE is_consultation = 1
        ORDER BY is_expired ASC, days_remaining ASC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def toggle_star(update_id):
    conn = get_conn()
    conn.execute("UPDATE updates SET is_starred = 1 - is_starred WHERE id = ?", (update_id,))
    conn.commit()
    row = conn.execute("SELECT is_starred FROM updates WHERE id = ?", (update_id,)).fetchone()
    conn.close()
    return row["is_starred"] if row else None


def toggle_read(update_id):
    conn = get_conn()
    conn.execute("UPDATE updates SET is_read = 1 - is_read WHERE id = ?", (update_id,))
    conn.commit()
    row = conn.execute("SELECT is_read FROM updates WHERE id = ?", (update_id,)).fetchone()
    conn.close()
    return row["is_read"] if row else None


def mark_read(update_id):
    conn = get_conn()
    conn.execute("UPDATE updates SET is_read = 1 WHERE id = ?", (update_id,))
    conn.commit()
    conn.close()


def get_sources(active_only=False):
    conn = get_conn()
    query = "SELECT * FROM sources"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY country, name"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def toggle_source(source_id):
    conn = get_conn()
    conn.execute("UPDATE sources SET active = 1 - active WHERE id = ?", (source_id,))
    conn.commit()
    row = conn.execute("SELECT active FROM sources WHERE id = ?", (source_id,)).fetchone()
    conn.close()
    return row["active"] if row else None


def add_source(data):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO sources (name, url, source_type, country, default_topic)
            VALUES (?, ?, ?, ?, ?)
        """, (data["name"], data["url"], data.get("source_type", "rss"),
              data.get("country"), data.get("default_topic")))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_source_by_id(source_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_unread_count():
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM updates WHERE is_read = 0").fetchone()
    conn.close()
    return row["cnt"]


def update_source_last_fetched(source_id):
    conn = get_conn()
    conn.execute("UPDATE sources SET last_fetched = datetime('now') WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()


def get_update_count():
    conn = get_conn()
    row = conn.execute("SELECT COUNT(*) as cnt FROM updates").fetchone()
    conn.close()
    return row["cnt"]

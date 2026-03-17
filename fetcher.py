"""
MENA Policy & Regulatory Monitor — Fetching Engine
RSS parsing, Google News feeds, and consultation portal scrapers.
"""

import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# Background refresh state
_refresh_lock = threading.Lock()
_refresh_status = {"running": False, "progress": "", "result": None}

# Request timeouts (connect, read)
REQUEST_TIMEOUT = (10, 30)

# Browser-like session for scraping with retry
SESSION = requests.Session()
retry_strategy = Retry(
    total=2,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
SESSION.mount("http://", adapter)
SESSION.mount("https://", adapter)
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
})


def get_refresh_status():
    """Return current refresh status for polling."""
    with _refresh_lock:
        return dict(_refresh_status)


def start_refresh():
    """Start a background refresh. Returns immediately."""
    with _refresh_lock:
        if _refresh_status["running"]:
            return {"started": False, "message": "Refresh already in progress"}
        _refresh_status["running"] = True
        _refresh_status["progress"] = "Starting..."
        _refresh_status["result"] = None

    thread = threading.Thread(target=_run_refresh, daemon=True)
    thread.start()
    return {"started": True, "message": "Refresh started"}


def _fetch_single_source(src):
    """Fetch a single source. Returns (fetched_count, new_count, error_or_None)."""
    try:
        if src["source_type"] == "rss":
            items = fetch_rss(src)
        elif src["source_type"] == "scrape":
            items = fetch_scrape(src)
        else:
            items = fetch_rss(src)

        new_count = 0
        for item in items:
            changes = db.insert_update(item)
            new_count += changes

        db.update_source_last_fetched(src["id"])
        log.info(f"[{src['name']}] fetched={len(items)} new={new_count}")
        return len(items), new_count, None

    except Exception as e:
        err_msg = f"{src['name']}: {e}"
        log.warning(f"Error fetching {src['name']}: {e}")
        return 0, 0, err_msg


def _run_refresh():
    """Background worker: fetch all sources in parallel."""
    try:
        sources = db.get_sources(active_only=True)
        total_fetched = 0
        total_new = 0
        errors = []
        done_count = 0
        total_count = len(sources)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(_fetch_single_source, src): src for src in sources}
            for future in as_completed(futures):
                fetched, new, error = future.result()
                total_fetched += fetched
                total_new += new
                if error:
                    errors.append(error)
                done_count += 1
                with _refresh_lock:
                    _refresh_status["progress"] = f"Fetched {done_count}/{total_count} sources..."

        result = {"fetched": total_fetched, "new": total_new, "errors": errors}
        with _refresh_lock:
            _refresh_status["result"] = result
            _refresh_status["running"] = False
            _refresh_status["progress"] = "Done"

    except Exception as e:
        log.error(f"Background refresh failed: {e}")
        with _refresh_lock:
            _refresh_status["result"] = {"fetched": 0, "new": 0, "errors": [str(e)]}
            _refresh_status["running"] = False
            _refresh_status["progress"] = "Failed"


def fetch_all_sources():
    """Fetch from all active sources (parallel). Returns summary dict."""
    sources = db.get_sources(active_only=True)
    total_fetched = 0
    total_new = 0
    errors = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_single_source, src): src for src in sources}
        for future in as_completed(futures):
            fetched, new, error = future.result()
            total_fetched += fetched
            total_new += new
            if error:
                errors.append(error)

    return {"fetched": total_fetched, "new": total_new, "errors": errors}


def fetch_rss(source):
    """Parse an RSS/Atom feed and return list of update dicts."""
    resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    # Detect Google News consent/block page (returns HTML instead of XML)
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type and "news.google.com" in source.get("url", ""):
        raise ValueError("Google News returned HTML instead of RSS (likely IP-blocked or consent page)")

    items = []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        # Log a snippet of the response for debugging
        snippet = resp.text[:200] if resp.text else "(empty)"
        log.warning(f"Failed to parse XML from {source['name']}. Response snippet: {snippet}")
        raise ValueError(f"Invalid XML response (Content-Type: {content_type})")

    # Handle both RSS and Atom feeds
    # RSS: root is <rss>, items are at channel/item
    # Atom: root is <feed>, items are <entry>
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    entries = root.findall(".//item")  # RSS
    if not entries:
        entries = root.findall(".//atom:entry", ns)  # Atom
        if not entries:
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for entry in entries:
        title = _xml_text(entry, "title", ns)
        link = _xml_link(entry, ns)
        if not title or not link:
            continue

        summary = _xml_text(entry, "description", ns) or _xml_text(entry, "summary", ns)
        if summary:
            summary = BeautifulSoup(summary, "html.parser").get_text(separator=" ").strip()
            if len(summary) > 500:
                summary = summary[:497] + "..."

        pub_date = _xml_text(entry, "pubDate", ns) or _xml_text(entry, "updated", ns) or _xml_text(entry, "published", ns)
        if pub_date:
            try:
                pub_date = dateparser.parse(pub_date).isoformat()
            except Exception:
                pub_date = datetime.utcnow().isoformat()
        else:
            pub_date = datetime.utcnow().isoformat()

        topic = detect_topic(title, summary, source.get("default_topic"))
        country = _detect_country(title, summary, source["country"])
        is_consultation = detect_consultation(title, summary, source["name"])

        items.append({
            "title": title,
            "url": link,
            "source_name": source["name"],
            "source_id": source["id"],
            "country": country,
            "topic": topic,
            "summary": summary,
            "published_date": pub_date,
            "is_consultation": is_consultation,
        })

    return items


def fetch_scrape(source):
    """Route to the appropriate scraper based on source name."""
    scrapers = {
        "Istitlaa": scrape_istitlaa,
        "UAE Consultations": scrape_uae_consultations,
        "TDRA Consultations": scrape_tdra,
        "UAE Legislation": scrape_uae_legislation,
        "ERRADA": scrape_errada,
        "Egypt Laws Portal": scrape_egypt_laws,
        "NTRA Egypt": scrape_ntra,
    }
    scraper_fn = scrapers.get(source["name"])
    if scraper_fn:
        return scraper_fn(source)
    return []


# ---------- Consultation Portal Scrapers ----------

def scrape_istitlaa(source):
    """Scrape Saudi NCC Istitlaa consultation portal."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        # Look for consultation list items (SharePoint-based page)
        for link in soup.select("a[href*='Consultation']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            if not href.startswith("http"):
                href = "https://istitlaa.ncc.gov.sa" + href

            items.append(_make_item(
                title=title, url=href, source=source,
                is_consultation=1, issuing_authority="NCC Saudi Arabia"
            ))

        return items
    except requests.RequestException as e:
        log.warning(f"Istitlaa scrape failed: {e}")
        return []


def scrape_uae_consultations(source):
    """Scrape UAE government consultations page."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for card in soup.select("a[href*='consult'], .consultation-item, .card"):
            title_el = card.select_one("h3, h4, .title, .card-title")
            if not title_el:
                title_el = card
            title = title_el.get_text(strip=True)
            href = card.get("href", "")
            if not href and card.name != "a":
                link = card.select_one("a")
                href = link.get("href", "") if link else ""
            if not title or not href:
                continue
            if not href.startswith("http"):
                href = "https://u.ae" + href

            items.append(_make_item(
                title=title, url=href, source=source,
                is_consultation=1, issuing_authority="UAE Government"
            ))

        return items
    except requests.RequestException as e:
        log.warning(f"UAE Consultations scrape failed: {e}")
        return []


def scrape_tdra(source):
    """Scrape TDRA consultations page."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for link in soup.select("a[href*='consultation'], a[href*='Consultation']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            if not href.startswith("http"):
                href = "https://tdra.gov.ae" + href

            items.append(_make_item(
                title=title, url=href, source=source,
                is_consultation=1, issuing_authority="TDRA UAE"
            ))

        return items
    except requests.RequestException as e:
        log.warning(f"TDRA scrape failed: {e}")
        return []


def scrape_uae_legislation(source):
    """Scrape UAE Legislation portal for new laws/decrees."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for link in soup.select("a[href*='legislation'], a[href*='law'], a[href*='decree']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            if not href.startswith("http"):
                href = "https://uaelegislation.gov.ae" + href

            items.append(_make_item(title=title, url=href, source=source))

        return items
    except requests.RequestException as e:
        log.warning(f"UAE Legislation scrape failed: {e}")
        return []


def scrape_errada(source):
    """Scrape Egypt's ERRADA regulatory portal."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for link in soup.select("a[href]"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or len(title) < 10 or not href:
                continue
            if any(kw in title.lower() for kw in ["study", "news", "regulation", "draft", "consultation"]):
                if not href.startswith("http"):
                    href = "https://www.errada.gov.eg" + href
                items.append(_make_item(title=title, url=href, source=source))

        return items
    except requests.RequestException as e:
        log.warning(f"ERRADA scrape failed: {e}")
        return []


def scrape_egypt_laws(source):
    """Scrape Egypt's Laws Portal."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for link in soup.select("a[href*='law'], a[href*='Law']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href:
                continue
            if not href.startswith("http"):
                href = "https://www.egypt.gov.eg" + href

            items.append(_make_item(title=title, url=href, source=source))

        return items
    except requests.RequestException as e:
        log.warning(f"Egypt Laws scrape failed: {e}")
        return []


def scrape_ntra(source):
    """Scrape Egypt's NTRA portal for telecom/ICT news."""
    try:
        resp = SESSION.get(source["url"], timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for link in soup.select("a[href*='news'], a[href*='decision'], a[href*='regulation']"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or len(title) < 10 or not href:
                continue
            if not href.startswith("http"):
                href = "https://www.tra.gov.eg" + href

            items.append(_make_item(title=title, url=href, source=source))

        return items
    except requests.RequestException as e:
        log.warning(f"NTRA scrape failed: {e}")
        return []


# ---------- Topic & Consultation Detection ----------

def detect_topic(title, summary, default_topic=None):
    """Auto-detect topic from title and summary using keyword matching."""
    text = f"{title} {summary or ''}".lower()

    best_topic = None
    best_score = 0

    for topic, keywords in config.TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text)
        if score > best_score:
            best_score = score
            best_topic = topic

    if best_score > 0:
        return best_topic
    return default_topic


def detect_consultation(title, summary, source_name):
    """Detect if an item is a consultation based on keywords and source name."""
    if source_name in config.CONSULTATION_PORTAL_NAMES:
        return 1

    text = f"{title} {summary or ''}".lower()
    for kw in config.CONSULTATION_KEYWORDS:
        if kw.lower() in text:
            return 1

    return 0


# ---------- Helpers ----------

def _detect_country(title, summary, source_country):
    """Try to detect country from text; fall back to source's country."""
    if source_country:
        return source_country

    text = f"{title} {summary or ''}".lower()
    for country in config.COUNTRIES:
        if country.lower() in text:
            return country
        # Check common aliases
        if country == "UAE" and "emirates" in text:
            return "UAE"
        if country == "Saudi Arabia" and "saudi" in text:
            return "Saudi Arabia"

    return None


def _xml_text(el, tag, ns):
    """Get text content of a child element, trying plain and namespaced."""
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    # Try Atom namespace
    child = el.find(f"atom:{tag}", ns)
    if child is not None and child.text:
        return child.text.strip()
    child = el.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _xml_link(el, ns):
    """Extract link from RSS <link> or Atom <link href='...'/>."""
    # RSS style: <link>url</link>
    link_el = el.find("link")
    if link_el is not None:
        if link_el.text and link_el.text.strip():
            return link_el.text.strip()
        if link_el.get("href"):
            return link_el.get("href")
    # Atom style
    for atom_ns in ["atom:", "{http://www.w3.org/2005/Atom}"]:
        link_el = el.find(f"{atom_ns}link")
        if link_el is not None and link_el.get("href"):
            return link_el.get("href")
    return ""


def _make_item(title, url, source, is_consultation=None, issuing_authority=None):
    """Build an update dict for a scraped item."""
    summary = ""
    topic = detect_topic(title, summary, source.get("default_topic"))
    if is_consultation is None:
        is_consultation = detect_consultation(title, summary, source["name"])

    return {
        "title": title,
        "url": url,
        "source_name": source["name"],
        "source_id": source["id"],
        "country": source.get("country"),
        "topic": topic,
        "summary": summary,
        "published_date": datetime.utcnow().isoformat(),
        "is_consultation": is_consultation,
        "issuing_authority": issuing_authority,
    }

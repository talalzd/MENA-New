"""
MENA Policy & Regulatory Monitor — Configuration
Source definitions, keyword mappings, and settings.
"""

import urllib.parse

# ---------- Database ----------
DATABASE = "mena_monitor.db"

# ---------- Countries ----------
COUNTRIES = ["Saudi Arabia", "UAE", "Egypt"]

# ---------- Topics ----------
TOPICS = [
    "Technology Regulation",
    "Labour Law",
    "Foreign Direct Investment",
    "Competition & Antitrust",
    "Data Privacy",
    "AI Governance",
]

# ---------- Topic keyword mappings ----------
TOPIC_KEYWORDS = {
    "Technology Regulation": [
        "technology regulation", "tech regulation", "digital regulation",
        "telecom", "telecommunications", "ICT", "internet regulation",
        "e-commerce", "electronic transactions", "cybersecurity",
        "cloud computing", "fintech", "digital economy",
        "تنظيم التكنولوجيا", "التنظيم الرقمي", "الاتصالات",
    ],
    "Labour Law": [
        "labour law", "labor law", "labour reform", "labor reform",
        "work permit", "employment law", "workforce", "saudization",
        "emiratization", "nitaqat", "kafala", "wage protection",
        "قانون العمل", "إصلاح العمل", "تصاريح العمل",
    ],
    "Foreign Direct Investment": [
        "foreign direct investment", "FDI", "foreign investment",
        "investment law", "investment regulation", "MISA",
        "free zone", "special economic zone", "SEZ",
        "الاستثمار الأجنبي", "قانون الاستثمار",
    ],
    "Competition & Antitrust": [
        "competition law", "antitrust", "merger control",
        "market dominance", "anti-competitive", "cartel",
        "competition authority", "GAC", "ADGM",
        "قانون المنافسة", "مكافحة الاحتكار",
    ],
    "Data Privacy": [
        "data privacy", "data protection", "personal data",
        "PDPL", "privacy law", "data governance",
        "data localization", "cross-border data",
        "حماية البيانات", "الخصوصية", "البيانات الشخصية",
    ],
    "AI Governance": [
        "artificial intelligence", "AI governance", "AI regulation",
        "AI policy", "AI ethics", "machine learning regulation",
        "SDAIA", "national AI strategy",
        "الذكاء الاصطناعي", "حوكمة الذكاء الاصطناعي",
    ],
}

# ---------- Consultation detection keywords ----------
CONSULTATION_KEYWORDS = [
    "consultation", "public consultation", "stakeholder consultation",
    "request for comments", "RFC", "call for input",
    "draft regulation", "draft law", "draft policy",
    "regulatory sandbox", "public hearing",
    "استطلاع", "مشاورة", "استشارة عامة",
    "مشروع نظام", "مشروع لائحة", "مشروع قانون",
]

# ---------- Consultation portal source names ----------
CONSULTATION_PORTAL_NAMES = [
    "Istitlaa",
    "UAE Consultations",
    "TDRA Consultations",
    "UAE Legislation",
    "ERRADA",
    "Egypt Laws Portal",
    "NTRA Egypt",
]


def _gnews_rss(query):
    """Build a Google News RSS URL for a search query."""
    encoded = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"


# ---------- Pre-populated sources ----------
DEFAULT_SOURCES = [
    # --- Tier 0: Consultation Portals (via Google News) ---
    # Direct scraping is unreachable from cloud hosts; use Google News as proxy
    {"name": "GN: Saudi consultations", "url": _gnews_rss("Saudi Arabia public consultation regulation NCC Istitlaa"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Technology Regulation"},
    {"name": "GN: UAE consultations", "url": _gnews_rss("UAE public consultation regulation TDRA"),
     "source_type": "rss", "country": "UAE", "default_topic": "Technology Regulation"},
    {"name": "GN: UAE legislation", "url": _gnews_rss("UAE new law decree legislation"),
     "source_type": "rss", "country": "UAE", "default_topic": "Technology Regulation"},
    {"name": "GN: Egypt regulation", "url": _gnews_rss("Egypt regulation NTRA ERRADA consultation"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Technology Regulation"},

    # --- Tier 1: Government News Agencies (via Google News) ---
    # SPA no longer serves RSS feeds; use Google News site-search instead
    {"name": "SPA via Google News", "url": _gnews_rss("site:spa.gov.sa"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": None},
    {"name": "WAM via Google News", "url": _gnews_rss("site:wam.ae"),
     "source_type": "rss", "country": "UAE", "default_topic": None},

    # --- Tier 2: Google News RSS (country × topic) ---
    # Saudi Arabia
    {"name": "GN: Saudi tech regulation", "url": _gnews_rss("Saudi Arabia technology regulation"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Technology Regulation"},
    {"name": "GN: Saudi labour law", "url": _gnews_rss("Saudi Arabia labour law reform"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Labour Law"},
    {"name": "GN: Saudi FDI", "url": _gnews_rss("Saudi Arabia foreign investment"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Foreign Direct Investment"},
    {"name": "GN: Saudi competition law", "url": _gnews_rss("Saudi Arabia competition law antitrust"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Competition & Antitrust"},
    {"name": "GN: Saudi data privacy", "url": _gnews_rss("Saudi Arabia data privacy PDPL"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Data Privacy"},
    {"name": "GN: Saudi AI policy", "url": _gnews_rss("Saudi Arabia artificial intelligence policy SDAIA"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "AI Governance"},
    {"name": "GN: Saudi NCC consultation", "url": _gnews_rss("Saudi Arabia NCC consultation regulation"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": "Technology Regulation"},

    # UAE
    {"name": "GN: UAE tech regulation", "url": _gnews_rss("UAE technology regulation"),
     "source_type": "rss", "country": "UAE", "default_topic": "Technology Regulation"},
    {"name": "GN: UAE labour law", "url": _gnews_rss("UAE labour law reform"),
     "source_type": "rss", "country": "UAE", "default_topic": "Labour Law"},
    {"name": "GN: UAE FDI", "url": _gnews_rss("UAE foreign direct investment"),
     "source_type": "rss", "country": "UAE", "default_topic": "Foreign Direct Investment"},
    {"name": "GN: UAE competition law", "url": _gnews_rss("UAE competition law"),
     "source_type": "rss", "country": "UAE", "default_topic": "Competition & Antitrust"},
    {"name": "GN: UAE data privacy", "url": _gnews_rss("UAE data privacy protection"),
     "source_type": "rss", "country": "UAE", "default_topic": "Data Privacy"},
    {"name": "GN: UAE AI policy", "url": _gnews_rss("UAE artificial intelligence policy"),
     "source_type": "rss", "country": "UAE", "default_topic": "AI Governance"},
    {"name": "GN: UAE digital economy", "url": _gnews_rss("UAE digital economy regulation"),
     "source_type": "rss", "country": "UAE", "default_topic": "Technology Regulation"},

    # Egypt
    {"name": "GN: Egypt tech regulation", "url": _gnews_rss("Egypt technology regulation ICT"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Technology Regulation"},
    {"name": "GN: Egypt labour law", "url": _gnews_rss("Egypt labour law reform"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Labour Law"},
    {"name": "GN: Egypt FDI", "url": _gnews_rss("Egypt foreign investment"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Foreign Direct Investment"},
    {"name": "GN: Egypt competition law", "url": _gnews_rss("Egypt competition law antitrust"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Competition & Antitrust"},
    {"name": "GN: Egypt data privacy", "url": _gnews_rss("Egypt data privacy protection law"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Data Privacy"},
    {"name": "GN: Egypt AI policy", "url": _gnews_rss("Egypt artificial intelligence policy"),
     "source_type": "rss", "country": "Egypt", "default_topic": "AI Governance"},
    {"name": "GN: Egypt ICT regulation", "url": _gnews_rss("Egypt ICT regulation NTRA"),
     "source_type": "rss", "country": "Egypt", "default_topic": "Technology Regulation"},

    # --- Tier 3: English outlets (via Google News) ---
    {"name": "Arab News via Google News", "url": _gnews_rss("site:arabnews.com Saudi regulation policy"),
     "source_type": "rss", "country": "Saudi Arabia", "default_topic": None},
    {"name": "Al-Monitor MENA", "url": _gnews_rss("site:al-monitor.com MENA policy regulation"),
     "source_type": "rss", "country": None, "default_topic": None},
]

# ---------- Country flag emoji ----------
COUNTRY_FLAGS = {
    "Saudi Arabia": "\U0001f1f8\U0001f1e6",
    "UAE": "\U0001f1e6\U0001f1ea",
    "Egypt": "\U0001f1ea\U0001f1ec",
}

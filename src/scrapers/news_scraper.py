"""
Fetches top financial news articles from free RSS feeds.
Ranks by cross-source frequency: stories appearing in multiple feeds rank higher.
Falls back to most-recent if no cross-source signal is found.
"""

import re
import feedparser
from datetime import datetime, timezone, timedelta

FINANCIAL_RSS_FEEDS = [
    ("Reuters Business", "http://feeds.reuters.com/reuters/businessNews"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Investopedia", "https://www.investopedia.com/feedbuilder/feed/getfeed?feedName=rss_headline"),
]


def _normalize(title: str) -> set:
    """Return a set of meaningful words from a title for overlap comparison."""
    stopwords = {
        "the", "a", "an", "in", "of", "to", "and", "is", "are", "for",
        "on", "at", "by", "with", "from", "as", "its", "it", "this", "that",
        "be", "was", "will", "has", "have", "had", "but", "not", "new", "says",
    }
    words = re.sub(r"[^\w\s]", "", title.lower()).split()
    return {w for w in words if w not in stopwords and len(w) > 2}


def _overlap_score(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def fetch_top_article() -> dict:
    """
    Fetches the most prominent financial news article across RSS feeds.

    Returns:
        dict with keys: title, summary, url, source_name, published
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    all_entries = []

    for source_name, feed_url in FINANCIAL_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass

                if published and published < cutoff:
                    continue

                raw_summary = getattr(entry, "summary", "") or ""
                summary = re.sub(r"<[^>]+>", "", raw_summary).strip()

                all_entries.append({
                    "title": getattr(entry, "title", "").strip(),
                    "summary": summary,
                    "url": getattr(entry, "link", ""),
                    "source_name": source_name,
                    "published": published,
                })
        except Exception:
            continue

    if not all_entries:
        # Fallback: ignore the 24h window, grab the first entry from any feed
        for source_name, feed_url in FINANCIAL_RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                if feed.entries:
                    e = feed.entries[0]
                    summary = re.sub(r"<[^>]+>", "", getattr(e, "summary", "") or "").strip()
                    return {
                        "title": getattr(e, "title", "").strip(),
                        "summary": summary,
                        "url": getattr(e, "link", ""),
                        "source_name": source_name,
                        "published": None,
                    }
            except Exception:
                continue
        raise RuntimeError("Could not fetch any news articles from any RSS feed.")

    # Prefer entries that have actual summary content — gives Ollama something to work with
    entries_with_summary = [e for e in all_entries if len(e["summary"]) > 50]
    candidates = entries_with_summary if entries_with_summary else all_entries

    # Score each candidate by Jaccard overlap with every other candidate's title
    word_sets = [(_normalize(e["title"]), e) for e in candidates]
    scored = []
    for i, (ws_i, entry_i) in enumerate(word_sets):
        cross_score = sum(
            _overlap_score(ws_i, ws_j)
            for j, (ws_j, _) in enumerate(word_sets)
            if j != i
        )
        scored.append((cross_score, entry_i))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_entry = scored[0]

    # If no meaningful cross-source signal, return the most recent entry with a summary
    if best_score < 0.1:
        entries_with_date = [e for e in candidates if e["published"]]
        if entries_with_date:
            return max(entries_with_date, key=lambda e: e["published"])
        return candidates[0]

    return best_entry

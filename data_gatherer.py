"""
data_gatherer.py — MEDIA BRIEF BUILDER
Python data gathering layer. No LLM involved. All calls are deterministic Python.

Functions:
  gather_reporter_data()    — scrapes reporter page
  gather_client_context()   — 6 direct Glean API calls
  gather_news()             — Serper news search
  gather_all()              — runs all three, returns combined payload

Validate: python3 data_gatherer.py
"""

import os
import re
import json
import httpx
from typing import Any
from dotenv import load_dotenv

load_dotenv()

GLEAN_SERVER_URL = os.environ["GLEAN_SERVER_URL"]
GLEAN_API_TOKEN  = os.environ["GLEAN_API_TOKEN"]
SERPER_API_KEY   = os.environ.get("SERPER_API_KEY", "")
GLEAN_ACT_AS     = os.environ.get("GLEAN_ACT_AS", "you@yourcompany.com")


def _glean_headers() -> dict:
    return {
        "Authorization": f"Bearer {GLEAN_API_TOKEN}",
        "X-Glean-ActAs": GLEAN_ACT_AS,
        "Content-Type": "application/json",
    }


def _glean_search(query: str, max_snippets: int = 5000, filter_terms: list = None) -> str:
    """Direct Glean search — returns raw text snippets. No agent, no LLM.

    filter_terms: if provided, a result document is only included when at least
    one term appears (case-insensitive) in its title or snippet text.
    """
    try:
        resp = httpx.post(
            f"{GLEAN_SERVER_URL}/rest/api/v1/search",
            json={
                "query": query,
                "pageSize": 10,
                "maxSnippetSize": max_snippets,
                "requestOptions": {
                    "returnLlmContentOverSnippets": True,
                    "datasourceFilter": "gdrive",
                },
            },
            headers=_glean_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return ""
        lines = []
        for r in results[:10]:
            title    = r.get("document", {}).get("title", "")
            url      = r.get("document", {}).get("url", "")
            if "/drive/folders/" in url:
                continue
            snippets = r.get("snippets", [])
            text     = " ".join(s.get("text", "") for s in snippets)[:2000]
            if not text:
                continue
            if filter_terms:
                haystack = (title + " " + text).lower()
                if not any(term.lower() in haystack for term in filter_terms if term):
                    continue
            lines.append(f"[{title}] ({url})\n{text}")
            if len(lines) >= 5:
                break
        return "\n\n".join(lines)
    except Exception as e:
        return f"[glean error: {e}]"


def gather_reporter_data(brief_request: Any) -> dict:
    """
    Scrape reporter page and return structured data with confidence score.
    For podcast/broadcast URLs, falls back to web search.
    """
    from tools import scrape_reporter_page

    reporter_url = brief_request.reporter_url
    print(f"[data_gatherer] Scraping reporter: {reporter_url}")

    podcast_platforms = [
        "podcasts.apple.com", "open.spotify.com", "podcasts.google.com",
        "overcast.fm", "pocketcasts.com",
    ]
    is_podcast_platform = any(p in reporter_url for p in podcast_platforms)
    host_name = getattr(brief_request, "host_name", None) or ""

    if is_podcast_platform and host_name:
        print(f"[data_gatherer] Podcast platform detected — using web search for host: {host_name}")
        reporter_data = _gather_podcast_host(host_name, reporter_url)
    else:
        try:
            raw = scrape_reporter_page.run(reporter_url=reporter_url)
            reporter_data = json.loads(raw)
        except Exception as e:
            print(f"[data_gatherer] Scrape failed: {e}")
            reporter_data = {}

    name     = reporter_data.get("name", "")
    bio      = reporter_data.get("bio", "")
    articles = reporter_data.get("recent_articles", [])
    headshot = reporter_data.get("headshot_base64", "")

    if name and bio and len(articles) >= 3 and headshot:
        confidence = "high"
    elif name and (bio or len(articles) >= 2):
        confidence = "medium"
    else:
        confidence = "low"

    if not reporter_data.get("outlet") and reporter_data.get("bio"):
        bio = reporter_data["bio"]
        m = re.search(r"is ([A-Z][A-Za-z0-9 &]+?)(?:'s|'s| reporter| correspondent| editor| journalist| senior| staff)", bio)
        if m:
            reporter_data["outlet"] = m.group(1).strip()
        elif reporter_data.get("url",""):
            from urllib.parse import urlparse
            domain = urlparse(reporter_data.get("url","")).netloc.lower().replace("www.","")
            outlet_map = {
                "cnbc.com": "CNBC", "wsj.com": "The Wall Street Journal",
                "bloomberg.com": "Bloomberg", "nytimes.com": "The New York Times",
                "reuters.com": "Reuters", "forbes.com": "Forbes",
                "axios.com": "Axios", "techcrunch.com": "TechCrunch",
                "ft.com": "Financial Times", "barrons.com": "Barron's",
            }
            reporter_data["outlet"] = outlet_map.get(domain, domain.split(".")[0].upper())

    if confidence == "low":
        print(f"[data_gatherer] Confidence low — running fallback chain")

        reporter_name_guess = name
        from urllib.parse import urlparse as _urlparse
        outlet_domain = _urlparse(reporter_url).netloc.lower().replace("www.", "")
        slug = reporter_url.rstrip("/").split("/")[-1]
        slug_clean = slug.replace("-", " ").replace("_", " ").strip()

        if host_name:
            reporter_name_guess = host_name
            reporter_data["name"] = host_name
            print(f"[data_gatherer] Using host_name from request: {host_name}")
        elif not reporter_name_guess or (reporter_name_guess and " " not in reporter_name_guess):
            try:
                name_resp = httpx.post(
                    "https://google.serper.dev/search",
                    json={"q": f'site:linkedin.com OR site:muckrack.com {slug_clean} journalist reporter', "num": 3},
                    headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                    timeout=10,
                )
                name_resp.raise_for_status()
                name_results = name_resp.json().get("organic", [])
                if name_results:
                    title_raw = name_results[0].get("title", "")
                    name_match = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-zA-Z\']+)+)", title_raw)
                    if name_match:
                        reporter_name_guess = name_match.group(1)
                        reporter_data["name"] = reporter_name_guess
            except Exception:
                pass
            if not reporter_name_guess:
                reporter_name_guess = slug_clean.title()
                reporter_data["name"] = reporter_name_guess

        # Glean fallback
        try:
            glean_text = _glean_search(f"{reporter_name_guess} reporter bio")
            non_bio_signals = ["MASTER", "spreadsheet", "# ", "@", "Media Brief", "Talking Points"]
            glean_is_bio = (
                glean_text and
                len(glean_text) > 100 and
                not any(s in glean_text[:300] for s in non_bio_signals)
            )
            if glean_is_bio and not reporter_data.get("bio"):
                reporter_data["bio"] = glean_text[:800]
        except Exception:
            pass

        # Serper web fallback
        try:
            if host_name:
                show_name_ctx = getattr(brief_request, "show_name", None) or ""
                f3_query = f"{reporter_name_guess} {show_name_ctx}" if show_name_ctx else f"{reporter_name_guess} podcast host"
            else:
                f3_query = f"{reporter_name_guess} journalist reporter"

            serper_resp = httpx.post(
                "https://google.serper.dev/search",
                json={"q": f3_query, "num": 10},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=15,
            )
            serper_resp.raise_for_status()
            serper_results = serper_resp.json().get("organic", [])

            if serper_results and not reporter_data.get("bio"):
                bio_signals = ["is a", "covers", "reports on", "journalist", "correspondent", "editor",
                               "founder", "ceo", "host", "author"]
                for r in serper_results[:5]:
                    snippet = r.get("snippet", "")
                    if any(w in snippet.lower() for w in bio_signals):
                        reporter_data["bio"] = snippet[:600]
                        break

            if not reporter_data.get("recent_articles"):
                skip_domains = ["linkedin.com", "muckrack.com", "twitter.com", "x.com", "facebook.com"]
                fallback_articles = []
                for r in serper_results[:8]:
                    title = r.get("title", "")
                    link  = r.get("link", "")
                    date  = r.get("date", "")
                    if title and link and not any(d in link.lower() for d in skip_domains):
                        fallback_articles.append({"title": title, "url": link, "date": date})
                if fallback_articles:
                    reporter_data["recent_articles"] = fallback_articles[:5]
        except Exception:
            pass

        # Wikipedia fallback
        if not reporter_data.get("bio"):
            try:
                wiki_name = reporter_name_guess.replace(" ", "_")
                wiki_resp = httpx.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_name}",
                    timeout=10,
                )
                if wiki_resp.status_code == 200:
                    extract = wiki_resp.json().get("extract", "")
                    if extract and len(extract) > 50:
                        reporter_data["bio"] = extract[:800]
            except Exception:
                pass

        bio      = reporter_data.get("bio", "")
        articles = reporter_data.get("recent_articles", [])
        name     = reporter_data.get("name", "")
        if name and bio and len(articles) >= 3:
            confidence = "high"
        elif name and (bio or len(articles) >= 2):
            confidence = "medium"
        else:
            confidence = "low"
        reporter_data["scrape_confidence"] = confidence
        reporter_data["used_fallback"] = True

    reporter_data["scrape_confidence"] = confidence
    print(
        f"[data_gatherer] Reporter: {name or 'unknown'} | "
        f"confidence={confidence} | "
        f"headshot={'YES' if headshot else 'NO'} | "
        f"articles={len(articles)}"
    )
    return reporter_data


def _gather_podcast_host(host_name: str, show_url: str) -> dict:
    if not SERPER_API_KEY:
        return {"name": host_name, "bio": "", "recent_articles": [], "source": "podcast_fallback"}

    try:
        resp = httpx.post(
            "https://google.serper.dev/search",
            json={"q": f"{host_name} podcast host bio", "num": 5},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("organic", [])
        bio_snippet = ""
        for r in results[:3]:
            snippet = r.get("snippet", "")
            if host_name.split()[0] in snippet and len(snippet) > 80:
                bio_snippet = snippet
                break

        ep_resp = httpx.post(
            "https://google.serper.dev/search",
            json={"q": f"{host_name} podcast recent episodes 2026", "num": 5},
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=15,
        )
        ep_resp.raise_for_status()
        ep_results = ep_resp.json().get("organic", [])
        episodes = [
            {"title": r.get("title",""), "url": r.get("link",""), "date": r.get("date","")}
            for r in ep_results[:5]
            if r.get("title") and len(r.get("title","")) > 20
        ]

        return {
            "name": host_name, "bio": bio_snippet,
            "recent_articles": episodes, "headshot_url": "",
            "headshot_base64": "", "headshot_mime_type": "",
            "linkedin_url": "", "twitter_url": "", "outlet": "",
            "source": "podcast_web_search",
        }
    except Exception as e:
        return {"name": host_name, "bio": "", "recent_articles": [], "source": f"podcast_fallback_error: {e}"}


def gather_client_context(brief_request: Any) -> dict:
    client = brief_request.client_name
    exec_  = brief_request.exec_name
    rules  = brief_request.brief_type_rules
    needs_transcripts = "previous_transcripts" in rules["extra_sections"]

    print(f"[data_gatherer] Gathering client context for: {client} / {exec_}")

    topic   = brief_request.topic
    queries = {
        "media_briefs":   f"{client} media brief",
        "talking_points": f"{exec_} {topic} talking points",
        "pitchbook":      f"{client} pitchbook",
        "faq_messaging":  f"{client} messaging FAQ",
        "commentary":     f"{exec_} commentary",
        "about":          f"{client} about company description",
    }
    if needs_transcripts:
        queries["transcripts"] = f"{exec_} transcript broadcast podcast"

    filter_terms = [t for t in [client, exec_] if len(t) >= 3]
    results = {}
    for key, query in queries.items():
        print(f"[data_gatherer]   Glean: '{query}'")
        results[key] = _glean_search(query, filter_terms=filter_terms)

    if not results.get("faq_messaging"):
        for fallback_q in [f"{client} key messages", f"{client} positioning messaging", f"{exec_} key messages"]:
            print(f"[data_gatherer]   faq_messaging fallback: '{fallback_q}'")
            fallback_result = _glean_search(fallback_q, filter_terms=filter_terms)
            if fallback_result:
                results["faq_messaging"] = fallback_result
                break

    found = [k for k, v in results.items() if v and not v.startswith("[glean error")]
    print(f"[data_gatherer] Client context: {len(found)}/{len(queries)} queries returned results")

    return {"client_name": client, "exec_name": exec_, "glean_results": results, "queries_with_results": found}


def gather_news(brief_request: Any) -> list:
    if not SERPER_API_KEY:
        print("[data_gatherer] No SERPER_API_KEY — skipping news")
        return []

    topic  = brief_request.topic
    client = brief_request.client_name
    print(f"[data_gatherer] Searching news for: {topic}")

    queries = [
        f"{topic} news this week",
        f"{topic} 2026",
        f"{client} {topic}",
    ]

    all_results = []
    seen_urls   = set()

    for query in queries:
        try:
            resp = httpx.post(
                "https://google.serper.dev/news",
                json={"q": query, "num": 5, "tbs": "qdr:m"},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("news", resp.json().get("organic", []))
            for item in items:
                url = item.get("link", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append({
                        "title":   item.get("title", ""),
                        "url":     url,
                        "source":  item.get("source", ""),
                        "date":    item.get("date", ""),
                        "snippet": item.get("snippet", ""),
                    })
        except Exception as e:
            print(f"[data_gatherer]   News search error for '{query}': {e}")

    blocked  = ["prnewswire", "businesswire", "globenewswire", "accesswire"]
    filtered = [r for r in all_results if not any(b in r["url"].lower() for b in blocked)]
    top3     = filtered[:3]
    print(f"[data_gatherer] News: {len(top3)} articles found")
    return top3


def gather_all(brief_request: Any) -> dict:
    print(f"\n[data_gatherer] Starting data gather for: {brief_request.doc_title}")
    print(f"[data_gatherer] Brief type: {brief_request.brief_type}\n")

    reporter_data  = gather_reporter_data(brief_request)
    client_context = gather_client_context(brief_request)
    news_articles  = gather_news(brief_request)

    print(f"\n[data_gatherer] ✅ Data gather complete")
    print(f"[data_gatherer]   Reporter confidence: {reporter_data.get('scrape_confidence', 'unknown')}")
    print(f"[data_gatherer]   Client context queries: {len(client_context.get('queries_with_results', []))}")
    print(f"[data_gatherer]   News articles: {len(news_articles)}")

    return {"reporter_data": reporter_data, "client_context": client_context, "news_articles": news_articles}


if __name__ == "__main__":
    from config import BriefRequest

    test = BriefRequest(
        client_name="Acme Corp",
        exec_name="Jane Smith",
        reporter_url="https://www.cnbc.com/arjun-kharpal/",
        brief_type="Intro",
        interview_date="May 20, 2026",
        interview_time="8:30 AM ET",
        virtual_or_inperson="Virtual",
        topic="enterprise AI and cloud infrastructure",
        on_record="On Record",
        staffed="Yes",
        submitter_email="you@yourcompany.com",
        location_or_link="https://meet.google.com/test-link",
        staffer_name="Account Manager",
    )

    print("Testing data_gatherer.py...\n")
    payload = gather_all(test)

    rd = payload["reporter_data"]
    print(f"\nReporter:")
    print(f"  Name:       {rd.get('name', 'MISSING')}")
    print(f"  Bio:        {rd.get('bio', '')[:80] or 'MISSING'}")
    print(f"  Headshot:   {'✅' if rd.get('headshot_base64') else '❌'}")
    print(f"  Articles:   {len(rd.get('recent_articles', []))}")
    print(f"  Confidence: {rd.get('scrape_confidence', 'unknown')}")

    cc = payload["client_context"]
    print(f"\nClient Context:")
    for key, val in cc["glean_results"].items():
        status = "✅" if val and not val.startswith("[glean error") else "❌"
        print(f"  {status} {key}: {len(val)} chars")

    news = payload["news_articles"]
    print(f"\nNews Articles: {len(news)}")

    print(f"\n✅ data_gatherer.py validation complete")

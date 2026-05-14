"""
tools.py — MEDIA BRIEF BUILDER
All @tool functions the agents call.

Tools:
  1. scrape_reporter_page   — Playwright scrapes reporter/host page + downloads headshot
  2. glean_search           — Search Glean knowledge graph
  3. glean_read_document    — Read a specific doc from Glean by title
  4. web_search             — Serper API for recent news articles
  5. post_to_slack          — Post message to Slack

Validate: python3 tools.py
"""

import os
import re
import json
import httpx
import base64
from bs4 import BeautifulSoup
from crewai.tools import tool
from dotenv import load_dotenv

load_dotenv()

GLEAN_SERVER_URL = os.environ["GLEAN_SERVER_URL"]
GLEAN_API_TOKEN  = os.environ["GLEAN_API_TOKEN"]
SLACK_BOT_TOKEN  = os.environ["SLACK_BOT_TOKEN"]
SERPER_API_KEY   = os.environ.get("SERPER_API_KEY", "")
GLEAN_ACT_AS     = os.environ.get("GLEAN_ACT_AS", "you@yourcompany.com")
GLEAN_TIMEOUT    = 30


def _glean_headers() -> dict:
    return {
        "Authorization": f"Bearer {GLEAN_API_TOKEN}",
        "X-Glean-ActAs": GLEAN_ACT_AS,
        "Content-Type": "application/json",
    }


def _download_image_as_base64(url: str) -> dict:
    """
    Download an image from a URL and return base64 encoded bytes + mime type.
    Used to properly embed headshots in Google Docs.
    Returns: {base64_data, mime_type, success}
    """
    if not url or url == "null":
        return {"success": False, "base64_data": "", "mime_type": ""}

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": origin,
        }
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "image/jpeg")
        mime_type = content_type.split(";")[0].strip()

        # Only accept valid image types
        if not mime_type.startswith("image/"):
            return {"success": False, "base64_data": "", "mime_type": ""}

        b64 = base64.b64encode(resp.content).decode("utf-8")
        return {"success": True, "base64_data": b64, "mime_type": mime_type}

    except Exception as e:
        return {"success": False, "base64_data": "", "mime_type": "", "error": str(e)}


def _fetch_headshot_from_meta(url: str) -> dict:
    """
    Fetch headshot URL from Open Graph / JSON-LD meta tags using plain httpx.
    Works on every major outlet without Playwright or API keys.
    Returns {headshot_url, headshot_base64, headshot_mime_type, linkedin_url, twitter_url}
    """
    result = {"headshot_url": "", "headshot_base64": "", "headshot_mime_type": "", "linkedin_url": "", "twitter_url": ""}

    # Full browser headers — datacenter IPs (Railway/AWS) are blocked by media CDNs
    # when the request looks like a bot. These headers match Chrome 124 on macOS exactly.
    _browser_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        resp = httpx.get(
            url,
            headers=_browser_headers,
            timeout=15,
            follow_redirects=True,
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        # Headshot — try OG image first, then twitter:image
        for attr in [("property", "og:image"), ("name", "twitter:image")]:
            tag = soup.find("meta", {attr[0]: attr[1]})
            if tag and tag.get("content"):
                result["headshot_url"] = tag["content"]
                break

        # Social links — try JSON-LD first
        import json as _json
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(script.string or "")
                entity = data.get("mainEntity", data)
                same_as = entity.get("sameAs", [])
                for link in same_as:
"""
qa_checker.py — MEDIA BRIEF BUILDER
Deterministic Python QA. Replaces Agent 5 (QA Assassin).
No LLM. No timeouts. Instant. Never hallucinates a QA result.

Validate: python3 qa_checker.py
"""

from typing import Any


def qa_check(brief_data: dict, brief_request: Any) -> list[str]:
    """
    Run all QA checks against the assembled brief_data.
    Returns list of issues. Empty list = QA_APPROVED.
    """
    issues = []
    warnings = []
    rules  = brief_request.brief_type_rules

    # ─────────────────────────────────────────────────────────────
    # SECTION 1 — STRUCTURE (required for every brief type)
    # ─────────────────────────────────────────────────────────────

    # Title
    if not brief_data.get("title"):
        issues.append("Title is missing")

    # Logistics
    logistics = brief_data.get("logistics", {})
    if not logistics.get("date_time"):
        issues.append("Logistics: date_time is missing")
    if not logistics.get("location"):
        issues.append("Logistics: location is missing")
    if not logistics.get("attendees"):
        issues.append("Logistics: attendees list is missing")

    # Opportunity
    opp = brief_data.get("opportunity", {})
    p1  = opp.get("paragraph_1", "")
    p2  = opp.get("paragraph_2", "")
    p3  = opp.get("paragraph_3", "")
    if not p1:
        issues.append("Opportunity: paragraph_1 is missing")
    if not p2:
        issues.append("Opportunity: paragraph_2 is missing")
    if not p3:
        issues.append("Opportunity: paragraph_3 is missing")
    if p1 and "**" not in p1:
        issues.append("Opportunity P1: missing bold format descriptor (e.g. **on-record, virtual**)")

    # Reporter section
    rs = brief_data.get("reporter_section", {})
    if not rs.get("name"):
        issues.append("Reporter section: name is missing")
    if not rs.get("bio_paragraph_1") or len(rs.get("bio_paragraph_1", "")) < 50:
        issues.append("Reporter section: bio_paragraph_1 is missing or too short")
    if not rs.get("bio_paragraph_2") or len(rs.get("bio_paragraph_2", "")) < 30:
        if brief_data.get("scrape_confidence") == "fallback":
            warnings.append("Reporter section: bio_paragraph_2 short (fallback source — verify before sending)")
        else:
            issues.append("Reporter section: bio_paragraph_2 is missing or too short")

    coverage = rs.get("recent_coverage", [])
    if len(coverage) < 4:
        issues.append(f"Reporter section: need 4-5 coverage items, got {len(coverage)}")
    for i, item in enumerate(coverage):
        if not item.get("date"):
            if brief_data.get("scrape_confidence") == "fallback":
                warnings.append(f"Reporter section: coverage item {i+1} missing date (fallback source — verify before sending)")
            else:
                issues.append(f"Reporter section: coverage item {i+1} is missing date (M/DD format)")
        if not item.get("url"):
            issues.append(f"Reporter section: coverage item {i+1} is missing URL")
        if not item.get("headline"):
            issues.append(f"Reporter section: coverage item {i+1} is missing headline")

    # Q&A section
    qa = brief_data.get("qa_section", {})
    items = qa.get("items", [])
    q_count = len(items)

    if brief_request.brief_type == "Intro":
        if not (4 <= q_count <= 5):
            issues.append(f"Q&A: Intro requires exactly 4-5 questions, got {q_count}")
    elif brief_request.brief_type == "Interview":
        if q_count < 5:
            issues.append(f"Q&A: Interview requires 5-7 questions, got {q_count}")
    elif brief_request.brief_type == "Podcast":
        # Podcast spec: 0 Q&A items — Expected Topics replaces Q&A entirely
        if q_count > 0:
            issues.append(f"Q&A: Podcast should have 0 Q&A items (Expected Topics replaces Q&A), got {q_count}")
    elif brief_request.brief_type == "Broadcast":
        if q_count < 7:
            issues.append(f"Q&A: Broadcast requires at least 7 Q&A items with drafted answers, got {q_count}")
        # Check drafted answers exist for Broadcast
        if rules.get("qa_has_answers"):
            for i, item in enumerate(items):
                if not item.get("answer_bullets"):
                    issues.append(f"Q&A: item {i+1} is missing drafted answer bullets (required for Broadcast)")

    # Talking points
    tps = brief_data.get("talking_points", [])
    if not tps:
        issues.append("Talking points section is missing or empty")
    else:
        for i, tp in enumerate(tps):
            if not tp.get("topic_label"):
                issues.append(f"Talking points: item {i+1} missing topic_label")
            points = tp.get("points", [])
            if not points:
                issues.append(f"Talking points: '{tp.get('topic_label', i+1)}' has no bullet points")

    # Relevant News
    news = brief_data.get("relevant_news", [])
    if rules.get("news_required") and len(news) < 3:
        issues.append(f"Relevant News: need exactly 3 articles, got {len(news)}")
    for i, article in enumerate(news):
        if not article.get("headline"):
            issues.append(f"Relevant News: article {i+1} missing headline")
        if not article.get("url"):
            issues.append(f"Relevant News: article {i+1} missing URL")
        bullets = article.get("bullets", [])
        if len(bullets) < 2:
            issues.append(f"Relevant News: article {i+1} needs at least 2 summary bullets, got {len(bullets)}")

    # Key Messaging
    km = brief_data.get("key_messaging", {})
    if not km.get("about_company") or len(km.get("about_company", "")) < 30:
        issues.append("Key Messaging: about_company boilerplate is missing or too short")
    if km.get("mission") and len(km.get("mission", "")) > 0:
        issues.append("Key Messaging: 'mission' field should be stripped (boilerplate only)")
    if km.get("faq_items") and len(km.get("faq_items", [])) > 0:
        issues.append("Key Messaging: 'faq_items' should be stripped (boilerplate only)")

    # Interview Tips & Tricks
    tips = brief_data.get("interview_tips", {})
    if not tips:
        issues.append("Interview Tips & Tricks section is missing entirely")
    else:
        if not tips.get("dos"):
            issues.append("Interview Tips: DOs list is missing")
        if not tips.get("donts"):
            issues.append("Interview Tips: DON'Ts list is missing")
        if not tips.get("bridging_phrases"):
            issues.append("Interview Tips: bridging phrases are missing")

    # No placeholder text
    import json as _json
    brief_str = _json.dumps(brief_data)
    placeholders = ["[INSERT", "[TBD]", "[DRAFT", "TODO:", "PLACEHOLDER"]
    for ph in placeholders:
        if ph in brief_str:
            issues.append(f"Brief contains placeholder text: '{ph}' — must be removed before sending")
            break

    # ─────────────────────────────────────────────────────────────
    # SECTION 2 — BRIEF TYPE SPECIFIC CHECKS
    # ─────────────────────────────────────────────────────────────

    if brief_request.brief_type == "In-Person":
        location = logistics.get("location", "")
        # Check for street address pattern — must have a number and street name
        has_address = bool(
            location and
            any(char.isdigit() for char in location) and
            len(location) > 15
        )
        if not has_address:
            issues.append("In-Person: logistics location must include full street address")
        if brief_request.is_staffed and not brief_request.staffer_name:
            issues.append("In-Person: staffed meeting requires staffer_name")

    if brief_request.brief_type in ("Broadcast", "Podcast"):
        # Check section labels
        section_label = rs.get("section_label", "")
        expected_label = rules.get("reporter_section_label", "")
        if section_label and expected_label and section_label != expected_label:
            issues.append(f"{brief_request.brief_type}: reporter section label should be '{expected_label}', got '{section_label}'")

        coverage_label = rs.get("coverage_label", "")
        expected_coverage = rules.get("coverage_label", "")
        if coverage_label and expected_coverage and coverage_label != expected_coverage:
            issues.append(f"{brief_request.brief_type}: coverage label should be '{expected_coverage}', got '{coverage_label}'")

    if brief_request.brief_type == "Broadcast":
        # Arrival and hit time
        if not logistics.get("arrival_time"):
            issues.append("Broadcast: logistics missing arrival_time")
        if not logistics.get("hit_time"):
            issues.append("Broadcast: logistics missing hit_time")

    return issues


def format_qa_result(issues: list[str]) -> tuple[bool, str]:
    """
    Convert issues list to (approved, message) tuple.
    approved=True means QA_APPROVED.
    """
    if not issues:
        return True, "QA_APPROVED"

    lines = ["QA_FAILED"]
    for i, issue in enumerate(issues, 1):
        lines.append(f"{i}. {issue}")
    return False, "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from config import BriefRequest

    test_request = BriefRequest(
        client_name="Acme Corp",
        exec_name="Jane Smith",
        reporter_url="https://example.com/alex-reporter/",
        brief_type="Intro",
        interview_date="May 20, 2026",
        interview_time="8:30 AM ET",
        virtual_or_inperson="Virtual",
        topic="crypto venture capital",
        on_record="On Record",
        staffed="Yes",
        submitter_email="you@yourcompany.com",
        staffer_name="PR Staffer",
    )

    # Test 1: Complete brief — should pass
    complete_brief = {
        "title": "Jane Smith, Acme Corp | Intro Media Brief",
        "brief_type": "Intro",
        "client_name": "Acme Corp",
        "exec_name": "Jane Smith",
        "logistics": {
            "date_time": "May 20, 2026 at 8:30 AM ET",
            "location": "https://meet.google.com/test",
            "location_display": "Google Meet",
            "attendees": ["Jane Smith, Acme Corp", "Alex Reporter, TechNews", "PR Staffer, the agency"],
        },
        "opportunity": {
            "paragraph_1": "This is an **on-record, virtual** intro with Arjun Kharpal.",
            "paragraph_2": "Be prepared to discuss crypto VC trends and deep tech.",
            "paragraph_3": "Rebecca Gathercole from Avenue Z will join to staff.",
        },
        "reporter_section": {
            "name": "Alex Reporter",
            "outlet": "TechNews",
            "bio_paragraph_1": "Alex Reporter is TechNews's Senior Technology Correspondent based in New York.",
            "bio_paragraph_2": "They have covered major tech stories globally for over a decade.",
            "recent_coverage": [
                {"date": "4/17", "headline": "TSMC posts record revenue", "url": "https://example.com/1"},
                {"date": "4/15", "headline": "ASML raises guidance", "url": "https://example.com/2"},
                {"date": "4/10", "headline": "AMD backs Wayve", "url": "https://example.com/3"},
                {"date": "4/5",  "headline": "Uber raises stake in Delivery Hero", "url": "https://example.com/4"},
            ],
        },
        "qa_section": {
            "has_answers": False,
            "items": [
                {"question": "What trends are you most excited about in enterprise tech?", "answer_bullets": []},
                {"question": "How is Acme Corp adapting to market changes?", "answer_bullets": []},
                {"question": "What technology intersections look most promising?", "answer_bullets": []},
                {"question": "What advice do you have for early-stage companies?", "answer_bullets": []},
            ],
        },
        "talking_points": [
            {
                "topic_label": "Enterprise Tech Trends (May 2026)",
                "points": [{"header": None, "bullets": ["Institutional interest is at an all-time high.", "AI integration is a key trend."]}],
            }
        ],
        "relevant_news": [
            {"date": "1/16", "headline": "Tech Investment Surges in 2025", "url": "https://example.com/1", "source": "Foley", "bullets": ["Exits up 40%", "Institutional adoption accelerating", "Relevant to Innovating Capital's strategy"]},
            {"date": "12/23", "headline": "5 tech predictions for 2026", "url": "https://example.com/2", "source": "SVB", "bullets": ["Cloud adoption continues to grow", "AI governance frameworks emerging", "Key context for interview"]},
            {"date": "7/22", "headline": "McKinsey Tech Trends 2025", "url": "https://example.com/3", "source": "McKinsey", "bullets": ["AI + cloud convergence", "Enterprise AI investment rising", "Frames the interview topic"]},
        ],
        "key_messaging": {
            "about_company": "Acme Corp is a leading technology company dedicated to empowering businesses through innovative AI-driven solutions.",
        },
        "interview_tips": {
            "best_practices": ["Take the interview from a quiet location."],
            "dos": ["Control the interview."],
            "donts": ["Attempt humor or criticisms."],
            "bridging_phrases": ["Yes, and let me tell you where that will lead..."],
            "flagging_phrases": ["The top priority is..."],
        },
    }

    print("Test 1: Complete brief (should pass)")
    issues = qa_check(complete_brief, test_request)
    approved, msg = format_qa_result(issues)
    print(f"  Result: {'✅ QA_APPROVED' if approved else '❌ QA_FAILED'}")
    if not approved:
        print(f"  Issues: {issues}")

    # Test 2: Brief with known issues — should catch them all
    bad_brief = {
        "title": "Jane Smith, Acme Corp | Intro Media Brief",
        "brief_type": "Intro",
        "logistics": {"date_time": "May 20, 2026", "location": "Google Meet", "attendees": []},
        "opportunity": {"paragraph_1": "This is a virtual intro.", "paragraph_2": "Prepare.", "paragraph_3": "Staffed."},
        "reporter_section": {
            "name": "Alex Reporter",
            "bio_paragraph_1": "Arjun covers tech.",
            "bio_paragraph_2": "",
            "recent_coverage": [
                {"date": "", "headline": "Article 1", "url": ""},
                {"date": "4/15", "headline": "Article 2", "url": "https://example.com/2"},
            ],
        },
        "qa_section": {"has_answers": False, "items": [
            {"question": "Q1?", "answer_bullets": []},
            {"question": "Q2?", "answer_bullets": []},
            {"question": "Q3?", "answer_bullets": []},
            {"question": "Q4?", "answer_bullets": []},
            {"question": "Q5?", "answer_bullets": []},
            {"question": "Q6?", "answer_bullets": []},  # too many for Intro
        ]},
        "talking_points": [],
        "relevant_news": [
            {"date": "1/16", "headline": "Article", "url": "https://x.com", "source": "X", "bullets": ["One bullet only"]},
        ],
        "key_messaging": {"about_company": "Short.", "mission": "We exist.", "faq_items": [{"question": "Q", "answer": "A"}]},
        "interview_tips": {},
    }

    print("\nTest 2: Brief with issues (should fail with specific items)")
    issues = qa_check(bad_brief, test_request)
    approved, msg = format_qa_result(issues)
    print(f"  Result: {'✅ QA_APPROVED' if approved else '❌ QA_FAILED'}")
    print(f"  Issues found: {len(issues)}")
    for issue in issues:
        print(f"    - {issue}")

    print("\n✅ qa_checker.py validation complete")

=== tools.py ===
"""
tools.py — AVENUE Z MEDIA BRIEF BUILDER
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
GLEAN_ACT_AS     = "thomas.chang@avenuez.com"
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
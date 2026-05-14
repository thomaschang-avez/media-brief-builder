"""
crew.py — MEDIA BRIEF BUILDER
5 small focused Gemini calls. No CrewAI. No agents. No tasks.

Call 1 — Opportunity section      (~15s)
Call 2 — Q&A questions            (~15s)
Call 3 — Talking points           (~15s)
Call 4 — News bullets             (~10s)
Call 5 — About boilerplate        (~5s)

Python assembles all outputs into brief JSON → brief_builder.py → Slack

Validate: python3 crew.py
"""

import os
import re
import json
import time
import traceback
import concurrent.futures
from dotenv import load_dotenv
from slack_sdk import WebClient
from google import genai
from google.oauth2 import service_account

from config import (
    BriefRequest,
    SLACK_BOT_TOKEN,
    TEST_CHANNEL,
    ERROR_CHANNEL,
    ADMIN_SLACK_ID,
    USE_TEST_CHANNEL,
    PR_TEAM_EMAIL_TO_SLACK,
    FALLBACK_SLACK_USER_ID,
    GEMINI_PROJECT,
    GEMINI_LOCATION,
    INTERVIEW_TIPS_AND_TRICKS,
    BROADCAST_TECH_REQUIREMENTS,
)
from brief_standards import (
    OPPORTUNITY_BOLD_DESCRIPTORS,
    NEWS_SPEC,
    QA_SPEC,
    TIPS_TABLE,
)
from data_gatherer import gather_all
from qa_checker import qa_check, format_qa_result
from brief_builder import create_brief_doc

load_dotenv()

GEMINI_TIMEOUT = 90
ADMIN_EMAIL    = os.environ.get("ADMIN_EMAIL", "admin@yourcompany.com")


# ─────────────────────────────────────────────────────────────────
# GEMINI CLIENT + CALL
# ─────────────────────────────────────────────────────────────────

def _get_gemini_client():
    service_account_json = os.environ.get("GEMINI_SERVICE_ACCOUNT")
    if service_account_json:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(service_account_json),
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return genai.Client(
            vertexai=True,
            project=GEMINI_PROJECT,
            location=GEMINI_LOCATION,
            credentials=creds,
        )
    return genai.Client(
        vertexai=True,
        project=GEMINI_PROJECT,
        location=GEMINI_LOCATION,
    )


def _call_gemini(prompt: str, call_name: str = "") -> str:
    client = _get_gemini_client()

    def _do_call():
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_call)
            response = future.result(timeout=GEMINI_TIMEOUT)
        return response.text
    except concurrent.futures.TimeoutError:
        raise TimeoutError(f"Gemini call '{call_name}' timed out after {GEMINI_TIMEOUT}s")
    except Exception as e:
        raise RuntimeError(f"Gemini call '{call_name}' failed: {e}")


def _extract_json(text: str):
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        start = text.index("{")
        end   = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass
    return None


def _extract_json_array(text: str):
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and "items" in result:
            return result["items"]
    except json.JSONDecodeError:
        pass
    try:
        start = text.index("[")
        end   = text.rindex("]") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        pass
    return None


# ─────────────────────────────────────────────────────────────────
# BOLD DESCRIPTOR BUILDER
# ─────────────────────────────────────────────────────────────────

def _build_bold_descriptor(brief_request: BriefRequest) -> str:
    bt   = brief_request.brief_type
    spec = OPPORTUNITY_BOLD_DESCRIPTORS.get(bt, {})

    if bt == "Interview":
        location = "virtual" if brief_request.virtual_or_inperson == "Virtual" else "in-person"
        record   = brief_request.on_record.lower().replace(" ", "-")
        return f"**{location}, {record}**"
    elif bt == "Intro":
        record   = brief_request.on_record.lower().replace(" ", "-")
        location = "virtual" if brief_request.virtual_or_inperson == "Virtual" else "in-person"
        return f"**{record}, {location}**"
    elif bt == "In-Person":
        record = brief_request.on_record.lower().replace(" ", "-")
        return f"**{record}, in-person**"
    elif bt == "Broadcast":
        live_or_recorded = "live" if not brief_request.additional_context or "recorded" not in (brief_request.additional_context or "").lower() else "recorded"
        return f"**{live_or_recorded} broadcast**"
    elif bt == "Podcast":
        audio_video = "audio only" if brief_request.additional_context and "audio only" in (brief_request.additional_context or "").lower() else "audio and video"
        return f"**{audio_video}**"
    return spec.get("real_example", f"**{bt.lower()}**")


# ─────────────────────────────────────────────────────────────────
# CALL 1 — OPPORTUNITY SECTION
# ─────────────────────────────────────────────────────────────────

def _call_opportunity(brief_request: BriefRequest, reporter_name: str, reporter_outlet: str) -> dict:
    print("[crew] Gemini Call 1: Opportunity section...")

    staffing_note = (
        f"{brief_request.staffer_name} from the agency will join to staff and assist with follow-up."
        if brief_request.is_staffed
        else f"This meeting is NOT staffed. Remind {brief_request.exec_name} to clarify on-record status at the top of the meeting."
    )

    type_guidance = {
        "Intro":      "Frame as relationship-building. Remind exec to ask reporter what they are currently working on. This is NOT a story interview.",
        "Interview":  "This is a specific story interview. Frame the stakes clearly. Be thorough about what the reporter wants.",
        "In-Person":  "Note this is in-person. Include the location context naturally.",
        "Broadcast":  (
            "Note whether live or recorded, audio or video. "
            + (f"The segment is approximately {brief_request.segment_length}. " if getattr(brief_request, "segment_length", None) else "")
            + "Include the segment length in the Opportunity paragraph naturally."
        ),
        "Podcast":    "Note whether live or recorded, audio or video. Describe the show format briefly.",
    }.get(brief_request.brief_type, "")

    bold_descriptor = _build_bold_descriptor(brief_request)

    prompt = f"""Write the Opportunity section for a professional PR media brief.

BRIEF DETAILS:
- Executive: {brief_request.exec_name}, {brief_request.client_name}
- Reporter: {reporter_name}, {reporter_outlet}
- Brief Type: {brief_request.brief_type}
- Date/Time: {brief_request.interview_date} at {brief_request.interview_time}
- Location: {brief_request.location_or_link or "TBD"}
- On Record: {brief_request.on_record}
- Topic: {brief_request.topic}
- Additional context: {brief_request.additional_context or "None"}

GUIDANCE: {type_guidance}

Write EXACTLY 3 paragraphs:
P1: Start with EXACTLY "This is {'an' if bold_descriptor[2].lower() in 'aeiou' else 'a'} {bold_descriptor}" — use these exact asterisks, no variation.
Then describe the reporter, their title, outlet, and beat. State what the meeting is about.
P2: What {brief_request.exec_name} should prepare. What topics will come up. Why this matters.
P3: Use this exactly: "{staffing_note}"

Return JSON only:
{{"paragraph_1": "...", "paragraph_2": "...", "paragraph_3": "..."}}"""

    raw    = _call_gemini(prompt, "opportunity")
    result = _extract_json(raw)
    if not result:
        result = {
            "paragraph_1": f"This is {'an' if bold_descriptor[2].lower() in 'aeiou' else 'a'} {bold_descriptor} with {reporter_name}, {reporter_outlet}.",
            "paragraph_2": f"Be prepared to discuss {brief_request.topic}.",
            "paragraph_3": staffing_note,
        }

    p1 = result.get("paragraph_1", "")
    if bold_descriptor not in p1:
        p1_stripped = re.sub(r"(?i)^this is an?\s+\*\*[^*]+\*\*\s*", "", p1).strip()
        p1_stripped = re.sub(r"(?i)^this is an?\s+[^.]+?(?=\b(?:with|for)\b)", "", p1_stripped).strip()
        if p1_stripped and p1_stripped[0].islower():
            p1_stripped = p1_stripped[0].upper() + p1_stripped[1:]
        article = "an" if bold_descriptor[2].lower() in "aeiou" else "a"
        result["paragraph_1"] = f"This is {article} {bold_descriptor} with {reporter_name}, {reporter_outlet}. {p1_stripped}".strip()

    return result


# ─────────────────────────────────────────────────────────────────
# CALL 2 — Q&A SECTION
# ─────────────────────────────────────────────────────────────────

def _call_qa(brief_request: BriefRequest, reporter_data: dict, talking_points_raw: str) -> list:
    print("[crew] Gemini Call 2: Q&A section...")

    bt             = brief_request.brief_type
    qa_spec        = QA_SPEC.get(bt, QA_SPEC["Interview"])
    qa_has_answers = qa_spec["answers"]
    qa_count       = qa_spec["count"]

    if bt == "Podcast":
        print("[crew]   Podcast: skipping Q&A — using expected topics pattern")
        return []

    coverage = reporter_data.get("recent_articles", [])
    coverage_text = "\n".join([
        f"- {a.get('date','')} {a.get('title', a.get('headline',''))}"
        for a in coverage[:5]
    ])

    min_count = int(str(qa_count).split("-")[0]) if qa_count else 3

    if bt == "Intro":
        q_instructions = f"Write EXACTLY {qa_count} questions. General and conversational. NO drafted answers."
    elif bt == "Interview":
        q_instructions = (
            f"Write EXACTLY {qa_count} questions (minimum {min_count}). "
            f"Tie each question to the reporter's actual recent coverage above. NO drafted answers."
        )
    elif bt == "In-Person":
        q_instructions = f"Write {qa_count} questions. NO drafted answers. Conversational, relationship-building tone."
    else:
        q_instructions = f"Write {qa_count} questions WITH full drafted answers (3-5 bullet points each)."

    answer_bullets_example = '["drafted answer bullet 1", "bullet 2", "bullet 3"]' if qa_has_answers else "[]"
    prompt = f"""Write the Potential Questions section for a {bt} media brief.

These are questions that {reporter_data.get('name', 'the reporter')} is likely to ask {brief_request.exec_name}.
Do NOT address the questions to the reporter. Write them as questions {brief_request.exec_name} should be prepared to answer.

REPORTER: {reporter_data.get('name', '')} at {reporter_data.get('outlet', '')}
REPORTER BEAT/COVERAGE: {coverage_text}
TOPIC: {brief_request.topic}
CLIENT: {brief_request.exec_name}, {brief_request.client_name}

CLIENT TALKING POINTS (use to anticipate what the reporter will ask):
{talking_points_raw[:1500]}

INSTRUCTIONS: {q_instructions}

Return a JSON array only:
[
  {{
    "question": "Question text?",
    "answer_bullets": {answer_bullets_example}
  }}
]"""

    raw    = _call_gemini(prompt, "qa")
    result = _extract_json_array(raw)
    if not result:
        return [
            {"question": f"Can you share your perspective on {brief_request.topic}?", "answer_bullets": []},
            {"question": f"What trends are you seeing at {brief_request.client_name}?", "answer_bullets": []},
            {"question": "What opportunities do you see ahead?", "answer_bullets": []},
            {"question": "What would you want our audience to know?", "answer_bullets": []},
        ]

    if len(result) < min_count:
        needed = min_count - len(result)
        existing_qs = [item.get("question", "") for item in result]
        extra_prompt = (
            f"The media brief needs at least {min_count} questions but only {len(result)} were generated.\n"
            f"Write {needed} more questions that {reporter_data.get('name', 'the reporter')} might ask "
            f"{brief_request.exec_name} about: {brief_request.topic}\n"
            f"Do NOT repeat any of these existing questions:\n"
            + "\n".join(f"- {q}" for q in existing_qs)
            + '\nReturn JSON array only: [{"question": "...", "answer_bullets": []}]'
        )
        extra_raw = _call_gemini(extra_prompt, "qa_extra")
        extra = _extract_json_array(extra_raw)
        if extra:
            result.extend(extra[:needed])

    return result


# ─────────────────────────────────────────────────────────────────
# CALL 3 — TALKING POINTS
# ─────────────────────────────────────────────────────────────────

def _call_talking_points(brief_request: BriefRequest, glean: dict) -> list:
    print("[crew] Gemini Call 3: Talking points...")

    raw_tp     = glean.get("talking_points", "")[:4000]
    raw_comm   = glean.get("commentary", "")[:3000]
    raw_briefs = glean.get("media_briefs", "")[:2000]
    combined   = "\n\n".join(filter(None, [raw_tp, raw_comm, raw_briefs]))

    if not combined.strip():
        return [{"topic_label": f"{brief_request.client_name} Key Messages", "points": [{"header": None, "bullets": ["No talking points found in Glean — add manually"]}]}]

    prompt = f"""You are building the Talking Points section of a professional PR media brief.

CLIENT: {brief_request.exec_name}, {brief_request.client_name}
INTERVIEW TOPIC: {brief_request.topic}

GLEAN SOURCE MATERIAL (past commentary, talking points, media briefs):
{combined}

INSTRUCTIONS:
- Extract 3-5 topic clusters from the source material above
- Label each cluster with the topic and date if present, e.g. "Crypto VC (February 2026)"
- PRESERVE the client's actual language and phrasing — do NOT paraphrase or summarize into generic sentences
- Each bullet should be a complete thought in the client's own words
- Pull the most substantive, quotable commentary
- If a topic has a bold sub-header in the source, preserve that as the header field
- CRITICAL: Only include clusters directly relevant to the interview topic above
- Do NOT invent or generalize — only use what is in the source material

Return JSON array only:
[
  {{
    "topic_label": "Topic Name (Month Year)",
    "points": [
      {{
        "header": "Sub-header if present, or null",
        "bullets": [
          "Full preserved quote or commentary from the client.",
          "Another substantive point in the client's own words."
        ]
      }}
    ]
  }}
]"""

    raw    = _call_gemini(prompt, "talking_points")
    result = _extract_json_array(raw)
    if not result:
        return [{"topic_label": f"{brief_request.client_name} Key Messages", "points": [{"header": None, "bullets": [combined[:300]]}]}]
    return result


# ─────────────────────────────────────────────────────────────────
# DATE NORMALIZATION
# ─────────────────────────────────────────────────────────────────

def _normalize_date(raw: str) -> str:
    import datetime
    if not raw:
        return ""
    raw = raw.strip()
    if re.match(r"^\d{1,2}/\d{1,2}$", raw):
        today = datetime.datetime.today()
        m, d = map(int, raw.split("/"))
        try:
            candidate = datetime.datetime(today.year, m, d)
            if candidate > today:
                candidate = datetime.datetime(today.year - 1, m, d)
            return f"{candidate.month}/{candidate.day}/{str(candidate.year)[2:]}"
        except ValueError:
            return raw
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            dt = datetime.datetime.strptime(raw, fmt)
            return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"
        except ValueError:
            pass
    try:
        dt = datetime.datetime.strptime(raw, "%Y-%m-%d")
        return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"
    except ValueError:
        pass
    today = datetime.datetime.today()
    m = re.match(r"(\d+)\s+(day|week|month)s?\s+ago", raw.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == "day":
            dt = today - datetime.timedelta(days=n)
        elif unit == "week":
            dt = today - datetime.timedelta(weeks=n)
        elif unit == "month":
            dt = today - datetime.timedelta(days=n*30)
        return f"{dt.month}/{dt.day}/{str(dt.year)[2:]}"
    return raw


# ─────────────────────────────────────────────────────────────────
# CALL 4 — NEWS BULLETS
# ─────────────────────────────────────────────────────────────────

def _call_news_bullets(brief_request: BriefRequest, news_articles: list) -> list:
    print("[crew] Gemini Call 4: News article bullets...")
    rules = brief_request.brief_type_rules

    if rules.get("news_excluded"):
        print(f"[crew]   {brief_request.brief_type}: news excluded — skipping")
        return []
    if not news_articles:
        return []

    news_spec  = NEWS_SPEC.get(brief_request.brief_type, {})
    max_count  = news_spec.get("count", 3)
    articles   = news_articles[:max_count]

    articles_text = "\n\n".join([
        f"Article {i+1}:\nTitle: {a.get('title','')}\nSource: {a.get('source','')}\nDate: {a.get('date','')}\nSnippet: {a.get('snippet','')}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""Write 3-bullet summaries for these news articles.
Context: {brief_request.exec_name} at {brief_request.client_name} preparing for a {brief_request.brief_type} about {brief_request.topic}.

{articles_text}

For each article write exactly 3 bullets:
- Bullet 1: Key stat or specific data point
- Bullet 2: Main thesis in one sentence
- Bullet 3: Why relevant to the interview topic

Return JSON array only:
[
  {{
    "date": "from article",
    "headline": "exact title",
    "url": "exact URL",
    "source": "publication",
    "bullets": ["stat", "thesis", "relevance"]
  }}
]"""

    raw    = _call_gemini(prompt, "news_bullets")
    result = _extract_json_array(raw)
    if not result:
        result = [{"date": a.get("date",""), "headline": a.get("title",""), "url": a.get("url",""), "source": a.get("source",""), "bullets": [a.get("snippet","")[:150]]} for a in articles]

    for i, article in enumerate(articles):
        if i < len(result):
            result[i]["date"]     = _normalize_date(article.get("date", result[i].get("date", "")))
            result[i]["headline"] = article.get("title", result[i].get("headline", ""))
            result[i]["url"]      = article.get("url", result[i].get("url", ""))
            result[i]["source"]   = article.get("source", result[i].get("source", ""))
    return result


# ─────────────────────────────────────────────────────────────────
# CALL 5 — ABOUT BOILERPLATE
# ─────────────────────────────────────────────────────────────────

def _call_about_boilerplate(brief_request: BriefRequest, glean: dict) -> str:
    print("[crew] Gemini Call 5: About boilerplate...")

    raw_about     = glean.get("about", "")[:2000]
    raw_pitchbook = glean.get("pitchbook", "")[:2000]
    raw_faq       = glean.get("faq_messaging", "")[:3000]
    combined      = "\n\n".join(filter(None, [raw_faq, raw_about, raw_pitchbook]))

    if not combined.strip():
        return f"{brief_request.client_name} is a leading company in its industry."

    client = brief_request.client_name
    prompt = f"""You are building the Key Messaging section of a professional PR media brief for {client}.

SOURCE MATERIAL FROM GLEAN (pitchbook, FAQ, messaging docs):
{combined[:6000]}

INSTRUCTIONS:
- Extract the full company description, investment strategy, mission, vision, and FAQ if present
- Format as a structured block with labeled sections
- PRESERVE the exact language from the source — do not paraphrase or summarize
- Include specific stats and achievements if present
- Do NOT invent anything not present in the source material
- Return plain text only, no JSON, no markdown headers with #

Return plain text."""

    raw = _call_gemini(prompt, "about_boilerplate")
    raw = raw.strip().strip('"').strip("'")
    raw = re.sub(r"```.*?```", "", raw, flags=re.DOTALL).strip()

    if not raw or len(raw) < 30 or any(phrase in raw.lower() for phrase in ["i am sorry", "i cannot", "not present", "does not contain", "unable to"]):
        return f"{client} is a leading company in its industry."
    return raw


def _assemble_brief(brief_request, reporter_data, opportunity, qa_items, talking_points, news_articles, about_boilerplate) -> dict:
    rules          = brief_request.brief_type_rules
    reporter_label = rules["reporter_section_label"]
    coverage_label = rules["coverage_label"]
    qa_has_answers = rules["qa_has_answers"]

    coverage = [
        {
            "date": _normalize_date(a.get("date", "")),
            "headline": a.get("title", a.get("headline", "")),
            "url": a.get("url", "")
        }
        for a in reporter_data.get("recent_articles", [])[:5]
    ]

    bio_full = reporter_data.get("bio", "")
    if bio_full:
        bio_full = bio_full.rstrip(".")
        if bio_full.endswith("..") or bio_full.endswith(" …"):
            bio_full = bio_full.rstrip(". …")
        if bio_full and bio_full[-1] not in '.!?"\'':
            last_end = max(bio_full.rfind('.'), bio_full.rfind('!'), bio_full.rfind('?'))
            if last_end > len(bio_full) // 3:
                bio_full = bio_full[:last_end + 1]

        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", bio_full)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        outlet    = reporter_data.get("outlet", "")
        name      = reporter_data.get("name", "the reporter")

        if len(sentences) >= 4:
            mid    = max(1, len(sentences) // 2)
            bio_p1 = " ".join(sentences[:mid]).strip()
            bio_p2 = " ".join(sentences[mid:]).strip()
        elif len(sentences) >= 2:
            bio_p1 = sentences[0].strip()
            bio_p2 = " ".join(sentences[1:]).strip()
        else:
            bio_p1 = bio_full.strip()
            bio_p2 = ""

        if len(bio_p1) < 50:
            bio_p1 = bio_full.strip()
            bio_p2 = ""
        if not bio_p2 and outlet:
            bio_p2 = f"{name} is a key media contact at {outlet}, covering topics that intersect with {brief_request.client_name}'s work in {brief_request.topic}."
        elif not bio_p2:
            bio_p2 = f"{name} covers topics relevant to {brief_request.client_name} and is an important contact for this media opportunity."
    else:
        bio_p1 = bio_p2 = ""

    from brief_standards import TITLE_PATTERNS
    bt      = brief_request.brief_type
    pattern = TITLE_PATTERNS.get(bt, "{exec_name}, {client} | {outlet} Media Brief")

    outlet_for_title       = reporter_data.get("outlet", "") or ""
    reporter_name_for_title = reporter_data.get("name", "") or ""

    bad_name_signals = ("post", "template", "job description", "linkedin", "profile")
    name_is_bad = (
        not reporter_name_for_title
        or any(sig in reporter_name_for_title.lower() for sig in bad_name_signals)
    )
    if getattr(brief_request, "host_name", None) and name_is_bad:
        reporter_name_for_title = brief_request.host_name

    show_name_for_title = (
        getattr(brief_request, "show_name", None)
        or outlet_for_title
        or ""
    )
    if show_name_for_title and bt in ("Podcast", "Broadcast"):
        for suffix in (" Podcast", " Broadcast", " Show", " The Podcast"):
            if show_name_for_title.lower().endswith(suffix.lower()):
                show_name_for_title = show_name_for_title[:-len(suffix)].rstrip()
                break

    doc_title = pattern.format(
        exec_name=brief_request.exec_name,
        client=brief_request.client_name,
        outlet=show_name_for_title,
        show_name=show_name_for_title,
        reporter_name=reporter_name_for_title,
    )
    while "  " in doc_title:
        doc_title = doc_title.replace("  ", " ")
    doc_title = doc_title.strip(" |,")

    _reporter_att_name   = reporter_data.get("name", "Reporter")
    _reporter_att_outlet = reporter_data.get("outlet", "")
    _reporter_att_line   = (
        f"{_reporter_att_name}, {_reporter_att_outlet}"
        if _reporter_att_outlet
        else _reporter_att_name
    )

    if brief_request.is_staffed:
        _staffer_line = (
            f"{brief_request.staffer_name}, Agency (will be staffing)"
            if brief_request.staffer_name
            else "Agency (will be staffing)"
        )
    else:
        _staffer_line = "Agency (not staffed)"

    logistics = {
        "date_time":        f"{brief_request.interview_date} at {brief_request.interview_time}",
        "location":         brief_request.location_or_link or "TBD",
        "location_display": "Google Meet" if brief_request.virtual_or_inperson == "Virtual" else brief_request.location_or_link or "TBD",
        "attendees": [
            f"{brief_request.exec_name}, {brief_request.client_name}",
            _reporter_att_line,
            _staffer_line,
        ],
    }
    if bt == "Broadcast":
        logistics["arrival_time"] = getattr(brief_request, "arrival_time", None) or "TBD — confirm with producer"
        logistics["hit_time"]     = getattr(brief_request, "hit_time", None)     or "TBD — confirm with producer"

    tips_rows = TIPS_TABLE.get(bt, TIPS_TABLE["Interview"])

    return {
        "title":       doc_title,
        "brief_type":  bt,
        "client_name": brief_request.client_name,
        "exec_name":   brief_request.exec_name,
        "logistics":   logistics,
        "opportunity": opportunity,
        "reporter_section": {
            "section_label":      reporter_label,
            "name":               (
                brief_request.host_name
                if (getattr(brief_request, "host_name", None)
                    and any(sig in (reporter_data.get("name","") or "").lower()
                            for sig in ("post", "template", "job description", "linkedin", "profile")))
                else reporter_data.get("name","")
            ),
            "outlet":             reporter_data.get("outlet",""),
            "author_page_url":    brief_request.reporter_url,
            "headshot_url":       reporter_data.get("headshot_url",""),
            "headshot_base64":    reporter_data.get("headshot_base64",""),
            "headshot_mime_type": reporter_data.get("headshot_mime_type","image/jpeg"),
            "linkedin_url":       reporter_data.get("linkedin_url",""),
            "twitter_url":        reporter_data.get("twitter_url",""),
            "show_links":         reporter_data.get("show_links", {}),
            "show_name":          getattr(brief_request, "show_name", "") or "",
            "bio_paragraph_1":    bio_p1,
            "bio_paragraph_2":    bio_p2,
            "coverage_label":     coverage_label,
            "recent_coverage":    coverage,
        },
        "scrape_confidence": "fallback" if reporter_data.get("used_fallback") else "scraped",
        "qa_section":      {"has_answers": qa_has_answers, "items": qa_items},
        "talking_points":  talking_points,
        "relevant_news":   news_articles,
        "key_messaging":   {"about_company": about_boilerplate},
        "expected_topics": brief_request.expected_topics or [],
        "interview_tips": {
            "best_practices":   INTERVIEW_TIPS_AND_TRICKS["best_practices"],
            "bridging_phrases": INTERVIEW_TIPS_AND_TRICKS["bridging_phrases"],
            "flagging_phrases": INTERVIEW_TIPS_AND_TRICKS["flagging_phrases"],
            "dos":   [row["do"]   for row in tips_rows],
            "donts": [row["dont"] for row in tips_rows],
        },
    }


# ─────────────────────────────────────────────────────────────────
# SLACK
# ─────────────────────────────────────────────────────────────────

def _slack() -> WebClient:
    return WebClient(token=SLACK_BOT_TOKEN)

def _dm(user_id, text):
    try:
        _slack().chat_postMessage(channel=user_id, text=text, mrkdwn=True)
    except Exception as e:
        print(f"[crew] Slack DM error: {e}")

def _post(channel, text):
    try:
        _slack().chat_postMessage(channel=channel, text=text, mrkdwn=True)
    except Exception as e:
        print(f"[crew] Slack post error: {e}")

def _resolve_slack_id(email: str) -> str:
    uid = PR_TEAM_EMAIL_TO_SLACK.get(email.lower(), "")
    if uid and not uid.startswith("U_"):
        return uid
    try:
        resp = _slack().users_lookupByEmail(email=email)
        return resp["user"]["id"]
    except Exception as e:
        print(f"[crew] Slack email lookup failed for {email}: {e} — falling back")
        return FALLBACK_SLACK_USER_ID

def _notify_success(brief_request, doc_url):
    uid = TEST_CHANNEL if USE_TEST_CHANNEL else _resolve_slack_id(brief_request.submitter_email)
    _dm(uid, f"✅ *Media Brief Ready*\n*{brief_request.doc_title}*\n\n📄 <{doc_url}|View Google Doc>\n\n*Next steps:*\n• Review and make any edits\n• Copy doc → rename with *(External)* in title\n• Set permissions → Anyone with link → Editor\n• Download PDF\n• Send client both Doc link and PDF")

def _notify_qa_failed(brief_request, doc_url, verdict):
    verdict    = verdict.replace("QA_FAILED","").strip()
    fix_lines  = [l.strip() for l in verdict.split("\n") if l.strip() and l.strip()[0].isdigit()][:8]
    fixes      = "\n".join(fix_lines) if fix_lines else "Please review the brief before sending to client."
    uid        = TEST_CHANNEL if USE_TEST_CHANNEL else _resolve_slack_id(brief_request.submitter_email)
    _dm(uid, f"⚠️ *Media Brief Draft Ready — Needs Review*\n*{brief_request.doc_title}*\n\n📄 <{doc_url}|View Google Doc>\n\n*Before sending to client, please review:*\n{fixes}")

def _notify_error(brief_request, error):
    msg = f"🔴 *Media Brief Pipeline Error*\n<@{ADMIN_SLACK_ID}> — failed for: *{brief_request.doc_title}*\n\n```{error[:500]}```"
    _post(ERROR_CHANNEL, msg)
    _dm(ADMIN_SLACK_ID, msg)

def _notify_admin(brief_request, doc_url, status: str, duration: float):
    if brief_request.submitter_email.lower() == ADMIN_EMAIL.lower():
        return
    status_line = "✅ Approved" if status == "success" else "⚠️ Needs Review"
    msg = (
        f"📋 *Brief generated*\n"
        f"Requested by: *{brief_request.submitter_email}*\n"
        f"*{brief_request.doc_title}*\n"
        f"📄 <{doc_url}|View Google Doc>\n"
        f"Status: {status_line} | Duration: {duration}s"
    )
    _dm(ADMIN_SLACK_ID, msg)


# ─────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────

def run_brief(brief_request: BriefRequest) -> dict:
    print(f"\n{'='*60}")
    print(f"  MEDIA BRIEF PIPELINE")
    print(f"  {brief_request.doc_title}")
    print(f"  Type: {brief_request.brief_type}")
    print(f"{'='*60}\n")

    t_start = time.time()

    if brief_request.brief_type in ("Podcast", "Broadcast"):
        if not (brief_request.host_name and brief_request.host_name.strip()):
            error_msg = (
                f"[crew] VALIDATION FAILURE: {brief_request.brief_type} brief requires host_name.\n"
                f"       Client: {brief_request.client_name}, Exec: {brief_request.exec_name}\n"
                f"       Reporter URL: {brief_request.reporter_url}"
            )
            print(error_msg)
            _notify_error(brief_request, error_msg)
            return {
                "status": "validation_failed",
                "error": "host_name required for Podcast/Broadcast briefs",
                "doc_url": None,
                "brief_data": None,
                "elapsed_seconds": round(time.time() - t_start, 1),
            }

    try:
        print("[crew] Layer 1: Gathering data...")
        t1       = time.time()
        gathered = gather_all(brief_request)
        reporter_data = gathered["reporter_data"]
        if brief_request.show_links:
            reporter_data["show_links"] = brief_request.show_links
        news_articles = gathered["news_articles"]
        glean         = gathered["client_context"]["glean_results"]
        print(f"[crew] ✅ Layer 1 complete in {round(time.time()-t1,1)}s\n")

        print("[crew] Layer 2: Running 5 Gemini calls...")
        t2 = time.time()

        opportunity       = _call_opportunity(brief_request, reporter_data.get("name",""), reporter_data.get("outlet",""))
        qa_items          = _call_qa(brief_request, reporter_data, glean.get("talking_points",""))
        talking_points    = _call_talking_points(brief_request, glean)
        news_with_bullets = _call_news_bullets(brief_request, news_articles)
        about_boilerplate = _call_about_boilerplate(brief_request, glean)

        print(f"[crew] ✅ Layer 2 complete in {round(time.time()-t2,1)}s\n")

        print("[crew] Assembling brief...")
        brief_data = _assemble_brief(
            brief_request, reporter_data, opportunity,
            qa_items, talking_points, news_with_bullets, about_boilerplate
        )
        print("[crew] ✅ Brief assembled\n")

        print("[crew] Layer 3: Running QA checks...")
        issues            = qa_check(brief_data, brief_request)
        approved, verdict = format_qa_result(issues)
        print(f"[crew] QA: {'✅ APPROVED' if approved else f'⚠️  FAILED ({len(issues)} issues)'}")

        print("\n[crew] Creating Google Doc...")
        doc_result = create_brief_doc(brief_data)
        doc_url    = doc_result["doc_url"]
        print(f"[crew] ✅ Google Doc: {doc_url}")

        total  = round(time.time()-t_start, 1)
        status = "success" if approved else "qa_failed"

        if approved:
            _notify_success(brief_request, doc_url)
        else:
            _notify_qa_failed(brief_request, doc_url, verdict)

        _notify_admin(brief_request, doc_url, status, total)

        print(f"\n[crew] ✅ Pipeline complete in {total}s")
        return {"status": status, "doc_url": doc_url, "brief_data": brief_data, "qa_issues": issues}

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        print(f"[crew] ❌ ERROR: {error_msg[:400]}")
        _notify_error(brief_request, error_msg)
        return {"status": "error", "error": error_msg}


if __name__ == "__main__":
    from config import BriefRequest

    print("Testing bold descriptor builder:\n")
    test_cases = [
        ("Interview",  "Virtual",    "On Record"),
        ("Intro",      "Virtual",    "On Record"),
        ("In-Person",  "In-Person",  "On Record"),
        ("Broadcast",  "In-Person",  "On Record"),
        ("Podcast",    "Virtual",    "On Record"),
    ]
    for bt, vip, rec in test_cases:
        req = BriefRequest(
            client_name="Test Client", exec_name="Test Exec",
            reporter_url="https://example.com", brief_type=bt,
            interview_date="May 20, 2026", interview_time="10:00 AM ET",
            virtual_or_inperson=vip, topic="test topic", on_record=rec,
            staffed="Yes", submitter_email="you@yourcompany.com",
        )
        descriptor = _build_bold_descriptor(req)
        print(f"  {bt:<12} → {descriptor}")

    print("\n✅ crew.py validation complete")

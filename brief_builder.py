"""
brief_builder.py — MEDIA BRIEF BUILDER
Takes the JSON payload from crew.py and creates a styled Google Doc.
Returns the doc URL.

Changes from v1:
  - TOC only renders for brief types where TOC_RULES["include"] is True
    (Interview + Broadcast only — not Intro, In-Person, Podcast)
  - DOs/DON'Ts table uses the correct row count per brief type
    (2 rows for Interview/Intro/In-Person, 3 rows for Broadcast/Podcast)
  - Both sourced from brief_standards — no hardcoding

Validate: python3 brief_builder.py
"""

import os
import json
import html
from datetime import datetime
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build as gdrive_build
from googleapiclient.http import MediaInMemoryUpload

from brief_standards import TOC_RULES, TIPS_TABLE, DOS_DONTS_SHORT, DOS_DONTS_LONG

load_dotenv()

ADC_PATH         = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
SCOPES           = ["https://www.googleapis.com/auth/drive.file"]
OUTPUT_FOLDER_ID = os.environ.get("PR_BRIEFS_FOLDER_ID", "")


def _get_drive_service():
    b64 = os.environ.get("DRIVE_ADC_BASE64")
    if b64:
        import base64 as _b64, json as _json
        adc = _json.loads(_b64.b64decode(b64).decode())
        creds = Credentials.from_authorized_user_info(adc, scopes=SCOPES)
    else:
        creds = Credentials.from_authorized_user_file(ADC_PATH, scopes=SCOPES)
    return gdrive_build("drive", "v3", credentials=creds)


def _e(text: str) -> str:
    return html.escape(str(text)) if text else ""


def _hyperlink(text: str, url: str) -> str:
    if url and url != "null" and url is not None:
        return f'<a href="{_e(url)}">{_e(text)}</a>'
    return _e(text)


def _bold(text: str) -> str:
    return f"<strong>{_e(text)}</strong>"


def _section_divider() -> str:
    return "<hr/>"


def build_html_brief(data: dict) -> str:
    """
    Convert brief JSON into HTML that Google Drive renders as a native Google Doc.
    Matches the exact format of real Avenue Z media briefs.
    """
    import re
    parts = []

    brief_type   = data.get("brief_type", "Interview")
    client_name  = data.get("client_name", "")
    exec_name    = data.get("exec_name", "")
    title        = data.get("title", f"{exec_name}, {client_name} Media Brief")
    logistics    = data.get("logistics", {})
    opportunity  = data.get("opportunity", {})
    reporter     = data.get("reporter_section", {})
    qa           = data.get("qa_section", {})
    talking_pts  = data.get("talking_points", [])
    rel_news     = data.get("relevant_news", [])
    rel_stats    = data.get("relevant_statistics", [])
    key_msg      = data.get("key_messaging", {})
    transcripts  = data.get("previous_transcripts", [])
    tips         = data.get("interview_tips", {})
    client_logo_url = data.get("client_logo_url", "")

    parts.append("<html><body style='font-family: Arial, sans-serif; font-size: 11pt; color: #000000;'>")

    # ── HEADER: logo top-right + title ──
    # Matches real Avenue Z brief format: logo floated to top-right, bold title below
    if client_logo_url:
        parts.append(
            f"<table style='width:100%; border:none; border-collapse:collapse;'><tbody><tr>"
            f"<td style='border:none; vertical-align:bottom;'></td>"
            f"<td style='border:none; text-align:right; vertical-align:top; width:160px;'>"
            f"<img src='{_e(client_logo_url)}' style='max-height:60px; max-width:150px;'/>"
            f"</td></tr></tbody></table>"
        )
    parts.append(f"<p><strong>{_e(title)}</strong></p>")
    parts.append(_section_divider())

    # ── TABLE OF CONTENTS
    # Only rendered for Interview and Broadcast — sourced from brief_standards.TOC_RULES
    toc_rule = TOC_RULES.get(brief_type, {"include": False})
    if toc_rule.get("include"):
        toc_label = toc_rule.get("label", "Contents:")
        toc_items = [reporter.get("section_label", "Reporter Information")]
        if qa.get("items"):
            toc_items.append("Potential Q&amp;A" if qa.get("has_answers") else "Potential Questions")
        if talking_pts:
            toc_items.append("Talking Points")
        if rel_stats:
            toc_items.append("Relevant Statistics")
        if rel_news:
            toc_items.append("Relevant News")
        if key_msg:
            toc_items.append("Key Messaging")
        if transcripts:
            toc_items.append("Previous Broadcast Q&amp;As" if "Broadcast" in brief_type else "Previous Podcast Q&amp;As")
        toc_items.append("Interview Tips &amp; Tricks")

        parts.append(f"<p><strong>{_e(toc_label)}</strong></p><ul>")
        for item in toc_items:
            parts.append(f"<li>{item}</li>")
        parts.append("</ul>")
        parts.append(_section_divider())

    # ── LOGISTICS ──
    date_time     = logistics.get("date_time", "")
    arrival_time  = logistics.get("arrival_time", "")
    hit_time      = logistics.get("hit_time", "")
    location      = logistics.get("location", "")
    location_disp = logistics.get("location_display", location)
    attendees     = logistics.get("attendees", [])

    parts.append("<table style='border-collapse: collapse; width: 100%;'><tbody>")
    parts.append(f"<tr><td style='padding: 4px 8px; width: 120px;'><strong>Date/Time:</strong></td>"
                 f"<td style='padding: 4px 8px;'>{_e(date_time)}</td></tr>")
    if arrival_time:
        parts.append(f"<tr><td style='padding: 4px 8px;'><strong>Arrival Time:</strong></td>"
                     f"<td style='padding: 4px 8px;'><strong>{_e(arrival_time)}</strong></td></tr>")
    if hit_time:
        parts.append(f"<tr><td style='padding: 4px 8px;'><strong>Hit Time:</strong></td>"
                     f"<td style='padding: 4px 8px;'><strong>{_e(hit_time)}</strong></td></tr>")

    if location and (location.startswith("http") or "meet." in location or "zoom." in location):
        loc_html = _hyperlink(location_disp or location, location)
    else:
        loc_html = _e(location_disp or location)
    parts.append(f"<tr><td style='padding: 4px 8px;'><strong>Location:</strong></td>"
                 f"<td style='padding: 4px 8px;'>{loc_html}</td></tr>")

    if attendees:
        parts.append(f"<tr><td style='padding: 4px 8px; vertical-align: top;'><strong>Attendees:</strong></td>"
                     f"<td style='padding: 4px 8px;'>{'<br/>'.join(_e(a) for a in attendees)}</td></tr>")
    parts.append("</tbody></table>")
    parts.append(_section_divider())

    # ── OPPORTUNITY ──
    parts.append(f"<p><strong>Opportunity:</strong></p>")
    for key in ["paragraph_1", "paragraph_2", "paragraph_3"]:
        para = opportunity.get(key, "")
        if para:
            para_converted = re.sub(r'\*\*(.+?)\*\*', r'<BOLD>\1</BOLD>', para)
            para_html = _e(para_converted).replace('&lt;BOLD&gt;', '<span style="font-weight:bold">').replace('&lt;/BOLD&gt;', '</span>')
            parts.append(f'<p style="margin-bottom: 12px;">{para_html}</p>')
    parts.append(_section_divider())

    # ── REPORTER / HOST SECTION ──
    section_label  = reporter.get("section_label", "Reporter Information")
    reporter_name  = reporter.get("name", "")
    reporter_url   = reporter.get("author_page_url", "")
    outlet         = reporter.get("outlet", "")
    linkedin_url   = reporter.get("linkedin_url", "")
    twitter_url    = reporter.get("twitter_url", "")
    bio_1          = reporter.get("bio_paragraph_1", "")
    bio_2          = reporter.get("bio_paragraph_2", "")
    coverage_label = reporter.get("coverage_label", "Recent Coverage")
    recent_items   = reporter.get("recent_coverage", [])

    name_link = _hyperlink(reporter_name, reporter_url) if reporter_url else _e(reporter_name)
    social_parts = []
    if linkedin_url and linkedin_url != "null":
        social_parts.append(_hyperlink("LinkedIn", linkedin_url))
    if twitter_url and twitter_url != "null":
        social_parts.append(_hyperlink("X", twitter_url))
    social_str = " | ".join(social_parts)

    # Broadcast: social on separate line
    if brief_type == "Broadcast":
        parts.append(f"<p><strong>{name_link}, {_e(outlet)}</strong></p>")
        if social_str:
            parts.append(f"<p><strong>Social Media: {social_str}</strong></p>")
    else:
        social_html = f" | Social Media: {social_str}" if social_str else ""
        parts.append(f"<p><strong>{name_link}, {_e(outlet)}{social_html}</strong></p>")

    # Headshot + bio
    headshot_b64  = reporter.get("headshot_base64", "")
    headshot_url  = reporter.get("reporter_headshot_url", "") or reporter.get("headshot_url", "")
    headshot_mime = reporter.get("headshot_mime_type", "image/jpeg")

    if headshot_b64:
        img_src = f"data:{headshot_mime};base64,{headshot_b64}"
        parts.append("<table style='border-collapse: collapse; width: 100%; margin-bottom: 8px;'><tbody><tr>")
        parts.append(f"<td style='width: 180px; vertical-align: top; padding-right: 16px;'>"
                     f"<img src='{img_src}' style='width: 160px;'/></td>")
        parts.append(f"<td style='vertical-align: top;'>"
                     f"<p>{_e(bio_1)}</p>"
                     f"{'<p>' + _e(bio_2) + '</p>' if bio_2 else ''}"
                     f"</td>")
        parts.append("</tr></tbody></table>")
    elif headshot_url and headshot_url != "null":
        parts.append("<table style='border-collapse: collapse; width: 100%; margin-bottom: 8px;'><tbody><tr>")
        parts.append(f"<td style='width: 180px; vertical-align: top; padding-right: 16px;'>"
                     f"<img src='{_e(headshot_url)}' style='width: 160px;'/></td>")
        parts.append(f"<td style='vertical-align: top;'>"
                     f"<p>{_e(bio_1)}</p>"
                     f"{'<p>' + _e(bio_2) + '</p>' if bio_2 else ''}"
                     f"</td>")
        parts.append("</tr></tbody></table>")
    else:
        if bio_1:
            parts.append(f"<p>{_e(bio_1)}</p>")
        if bio_2:
            parts.append(f"<p>{_e(bio_2)}</p>")

    # Podcast: show distribution links
    if brief_type == "Podcast":
        show_links = reporter.get("show_links", {})
        if show_links:
            link_parts = []
            for label, url in show_links.items():
                if url:
                    link_parts.append(_hyperlink(label, url))
            if link_parts:
                show_name = reporter.get("show_name", outlet)
                parts.append(f"<p><strong>The {_e(show_name)}:</strong> {' | '.join(link_parts)}</p>")

    if recent_items:
        parts.append(f"<p><strong>{_e(coverage_label)}:</strong></p><ul>")
        for item in recent_items:
            date     = item.get("date", "")
            headline = item.get("headline", "")
            url      = item.get("url", "")
            hl_link  = _hyperlink(headline, url) if url and url != "null" else _e(headline)
            parts.append(f"<li><strong>{_e(date)}</strong> - {hl_link}</li>")
        parts.append("</ul>")
    parts.append(_section_divider())

    # ── Q&A SECTION ──
    qa_items    = qa.get("items", [])
    has_answers = qa.get("has_answers", False)
    qa_label    = "Potential Q&amp;A:" if has_answers else "Potential Questions:"

    if qa_items:
        parts.append(f"<p><strong>{qa_label}</strong></p>")
        if has_answers:
            # Broadcast format: bold question + italic "Drafted response:" + bullets
            for item in qa_items:
                q       = item.get("question", "")
                bullets = item.get("answer_bullets", [])
                parts.append(f"<p><strong>{_e(q)}</strong></p>")
                if bullets:
                    parts.append("<p><em>Drafted response:</em></p><ul>")
                    for b in bullets:
                        parts.append(f"<li>{_e(b)}</li>")
                    parts.append("</ul>")
        else:
            # Interview/Intro/In-Person: questions only as bullet list
            parts.append("<ul>")
            for item in qa_items:
                q = item.get("question", "")
                parts.append(f"<li>{_e(q)}</li>")
            parts.append("</ul>")
        parts.append(_section_divider())

    # ── EXPECTED TOPICS (Podcast only) ──
    expected_topics = data.get("expected_topics", [])
    if brief_type == "Podcast" and expected_topics:
        parts.append("<p><strong>Expected Topics (shared by host):</strong></p><ul>")
        for topic in expected_topics:
            parts.append(f"<li>{_e(topic)}</li>")
        parts.append("</ul>")
        parts.append(_section_divider())

    # ── TALKING POINTS ──
    if talking_pts:
        tp_label = "Talking Points (shared with producer):" if brief_type == "Broadcast" else "Talking Points:"
        parts.append(f"<p><strong>{tp_label}</strong></p>")
        for cluster in talking_pts:
            topic_label = cluster.get("topic_label", "")
            points      = cluster.get("points", [])
            if topic_label:
                parts.append(f"<p><strong>{_e(topic_label)}</strong></p>")
            for point in points:
                header  = point.get("header", "")
                bullets = point.get("bullets", [])
                if header:
                    parts.append(f"<ul><li><strong>{_e(header)}</strong></li></ul>")
                if bullets:
                    parts.append("<ul style='margin-left: 40px;'>")
                    for b in bullets:
                        parts.append(f"<li>{_e(b)}</li>")
                    parts.append("</ul>")
        parts.append(_section_divider())

    # ── RELEVANT STATISTICS ──
    if rel_stats:
        parts.append("<p><strong>Relevant Statistics:</strong></p>")
        for stat_block in rel_stats:
            source = stat_block.get("source", "")
            stats  = stat_block.get("stats", [])
            if source:
                parts.append(f"<p><em>{_e(source)}</em></p>")
            if stats:
                parts.append("<ul>")
                for s in stats:
                    parts.append(f"<li>{_e(s)}</li>")
                parts.append("</ul>")
        parts.append(_section_divider())

    # ── RELEVANT NEWS ──
    if rel_news:
        parts.append("<p><strong>Relevant News:</strong></p><ul>")
        for article in rel_news:
            date     = article.get("date", "")
            headline = article.get("headline", "")
            url      = article.get("url", "")
            source   = article.get("source", "")
            bullets  = article.get("bullets", [])
            hl_link  = _hyperlink(headline, url) if url and url != "null" else _e(headline)
            source_str = f" ({_e(source)})" if source else ""
            parts.append(f"<li><strong>{_e(date)}</strong> - {hl_link}{source_str}</li>")
            if bullets:
                parts.append("<ul>")
                for b in bullets:
                    parts.append(f"<li>{_e(b)}</li>")
                parts.append("</ul>")
        parts.append("</ul>")
        parts.append(_section_divider())

    # ── KEY MESSAGING ──
    about     = key_msg.get("about_company", "")
    mission   = key_msg.get("mission", "")
    faq_items = key_msg.get("faq_items", [])

    # In-Person briefs have no Key Messaging section (confirmed: Lynq x FT)
    if brief_type != "In-Person" and (about or mission or faq_items):
        parts.append("<p><strong>Key Messaging:</strong></p>")
        if about:
            about_clean = about.strip()
            # Strip leading "About {client_name}:" that Gemini sometimes includes
            _about_prefix = f"about {client_name}:"
            if about_clean.lower().startswith(_about_prefix.lower()):
                about_clean = about_clean[len(_about_prefix):].strip()
            parts.append(f"<p><strong>About {_e(client_name)}:</strong> {_e(about_clean)}</p>")
        if mission:
            parts.append(f"<p><strong>Mission:</strong> {_e(mission)}</p>")
        if faq_items:
            parts.append("<p><strong>FAQ</strong></p>")
            for faq in faq_items:
                q = faq.get("question", "")
                a = faq.get("answer", "")
                parts.append(f"<p><strong>{_e(q)}</strong></p>")
                parts.append(f"<p>{_e(a)}</p>")
        parts.append(_section_divider())

    # ── PREVIOUS BROADCAST/PODCAST Q&As ──
    if transcripts:
        label = "Previous Broadcast Q&amp;As:" if "Broadcast" in brief_type else "Previous Podcast Q&amp;As:"
        parts.append(f"<p><strong>{label}</strong></p>")
        for transcript in transcripts:
            show = transcript.get("show_name", "")
            date = transcript.get("date", "")
            exchanges = transcript.get("exchanges", [])
            parts.append(f"<p><strong>{_e(show)} Q&amp;A ({_e(date)}):</strong></p>")
            for ex in exchanges:
                hi = ex.get("host_initials", "")
                hq = ex.get("host_question", "")
                gi = ex.get("guest_initials", "")
                ga = ex.get("guest_answer", "")
                parts.append(f"<p><strong>{_e(hi)}:</strong> {_e(hq)}</p>")
                parts.append(f"<p><strong>{_e(gi)}:</strong> {_e(ga)}</p>")
        parts.append(_section_divider())

    # ── INTERVIEW TIPS & TRICKS ──
    # Tips bullets are identical across all types.
    # DOs/DON'Ts table is 2-row for Interview/Intro/In-Person, 3-row for Broadcast/Podcast.
    # Sourced from brief_standards.TIPS_TABLE.
    parts.append("<p><strong>Interview Tips &amp; Tricks</strong></p>")

    parts.append("<p><strong>Be proactive.</strong> Because your time is limited, your goal is to be "
                 "message-driven rather than question-driven. It is important to use the time effectively.</p><ul>")
    parts.append("<li>Know your messages and deliver these consistently and assertively.</li>")
    parts.append("<li>Use proof points. Stats and anecdotes bring life to a story and create images.</li>")
    parts.append("<li>Keep answers short and sweet.</li>")
    parts.append("</ul>")

    parts.append("<p><strong>Use &quot;bridging&quot; to keep the interview on track.</strong> "
                 "This technique involves giving a brief response to the issue in question, "
                 "then returning seamlessly to your own agenda.</p><ul>")
    bridging = tips.get("bridging_phrases", [
        '"Yes, and let me tell you where that will lead…"',
        '"No, actually, the way we see the situation is…"',
    ])
    for phrase in bridging:
        parts.append(f"<li><em>{_e(phrase)}</em></li>")
    parts.append("</ul>")

    parts.append("<p><strong>Use &quot;flags.&quot;</strong> Certain opening phrases work well "
                 "to capture the attention of a reporter.</p><ul>")
    flagging = tips.get("flagging_phrases", [
        '"The top priority is…"',
        '"The biggest concern in today\'s environment is…"',
    ])
    for phrase in flagging:
        parts.append(f"<li><em>{_e(phrase)}</em></li>")
    parts.append("</ul>")

    parts.append("<p><strong>Remember your audience.</strong> Avoid technical jargon or terms that only "
                 "industry professionals would understand. Even if the reporters speak in jargon, "
                 "assume nothing and explain everything.</p>")

    parts.append("<p><strong>Be quotable.</strong> Use interesting and understandable language to deliver "
                 "your key messages. Analogies work particularly well and help make your remarks memorable.</p>")

    parts.append("<p><em>Interview Best Practices: Take the interview from a quiet location, "
                 "with good lighting, a clean background, and an eye-level camera.</em></p>")

    # Pick the correct DOs/DON'Ts table rows for this brief type
    table_rows = TIPS_TABLE.get(brief_type, DOS_DONTS_SHORT)

    dos_list   = tips.get("dos",   [row["do"]   for row in table_rows])
    donts_list = tips.get("donts", [row["dont"] for row in table_rows])

    # Trim to match the correct row count for this brief type
    expected_rows = len(table_rows)
    dos_list   = dos_list[:expected_rows]
    donts_list = donts_list[:expected_rows]

    parts.append(
        "<table style='border-collapse: collapse; width: 100%;'>"
        "<thead><tr>"
        "<th style='background-color: #00AA00; color: white; padding: 8px; text-align: left; width: 50%;'>Media Interview DOs</th>"
        "<th style='background-color: #CC0000; color: white; padding: 8px; text-align: left; width: 50%;'>Media Interview DON&apos;Ts</th>"
        "</tr></thead><tbody>"
    )
    for i in range(expected_rows):
        do_text   = dos_list[i]   if i < len(dos_list)   else ""
        dont_text = donts_list[i] if i < len(donts_list) else ""
        # Convert **bold** markers in table cells
        do_html   = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', _e(do_text))
        dont_html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', _e(dont_text))
        parts.append(
            f"<tr>"
            f"<td style='border: 1px solid #cccccc; padding: 8px; vertical-align: top;'>{do_html}</td>"
            f"<td style='border: 1px solid #cccccc; padding: 8px; vertical-align: top;'>{dont_html}</td>"
            f"</tr>"
        )
    parts.append("</tbody></table>")

    parts.append("</body></html>")
    return "\n".join(parts)


def create_brief_doc(brief_data: dict) -> dict:
    """
    Create a Google Doc from the brief JSON payload.
    Saves to PR_BRIEFS_FOLDER_ID.
    Returns: {doc_url, doc_id, doc_title}
    """
    title     = brief_data.get("title", "Media Brief")
    today     = datetime.now().strftime("%m/%d/%Y")
    doc_title = f"{title} — {today}"

    html_content = build_html_brief(brief_data)

    drive = _get_drive_service()
    media = MediaInMemoryUpload(
        html_content.encode("utf-8"),
        mimetype="text/html",
        resumable=False,
    )
    metadata = {
        "name": doc_title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [OUTPUT_FOLDER_ID],
    }
    result = drive.files().create(
        body=metadata,
        media_body=media,
        fields="id,webViewLink",
    ).execute()

    doc_id  = result.get("id", "")
    doc_url = result.get("webViewLink", "")
    print(f"[brief_builder] ✅ Google Doc created: {doc_url}")

    return {"doc_url": doc_url, "doc_id": doc_id, "doc_title": doc_title}


# ─────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing brief_builder.py — creating test Google Doc...\n")

    test_data = {
        "title": "Jane Smith, Acme Corp | Broadcast Media Brief",
        "brief_type": "Broadcast",
        "client_name": "Acme Corp",
        "exec_name": "Jane Smith",
        "logistics": {
            "date_time": "May 15, 2026 at 2:00 PM ET",
            "arrival_time": "1:40 PM ET",
            "hit_time": "2:00 PM ET",
            "location": "https://meet.google.com/abc-defg-hij",
            "location_display": "Google Meet",
            "attendees": [
                "Jane Smith, Acme Corp",
                "Alex Reporter, TechNews",
                "PR Staffer, the agency (will be staffing)",
            ],
        },
        "opportunity": {
            "paragraph_1": "This is a **live broadcast** with Alex Reporter, Senior Technology Correspondent at CNBC. Arjun covers the companies, trends, and technologies shaping the future, with particular interest in AI and healthcare innovation.",
            "paragraph_2": "You should be prepared to discuss how Acme Corp is integrating AI tools into the concierge medicine model, the outcomes data you have seen, and your perspective on where AI fits in the doctor-patient relationship.",
            "paragraph_3": "A PR Staffer from the agency will join the call to staff and assist with any follow-up.",
        },
        "reporter_section": {
            "section_label": "About the Host",
            "name": "Alex Reporter",
            "outlet": "TechNews",
            "author_page_url": "https://example.com/alex-reporter/",
            "headshot_b64": None,
            "linkedin_url": "https://linkedin.com/in/example",
            "twitter_url": "https://x.com/example",
            "bio_paragraph_1": "Alex Reporter is CNBC's Senior Technology Correspondent, based in London.",
            "bio_paragraph_2": "Since joining CNBC in 2013, Arjun has reported from the world's major innovation hubs.",
            "coverage_label": "Recent Clips",
            "recent_coverage": [
                {"date": "5/5", "headline": "How AI is reshaping the doctor's office", "url": "https://cnbc.com/example1"},
                {"date": "5/3", "headline": "Concierge medicine boom", "url": "https://cnbc.com/example2"},
                {"date": "4/30", "headline": "Tech giants race to build AI health assistants", "url": "https://cnbc.com/example3"},
                {"date": "4/28", "headline": "What the Apple Health study means for your doctor", "url": "https://cnbc.com/example4"},
            ],
        },
        "qa_section": {
            "has_answers": True,
            "items": [
                {"question": "How is Acme Corp using AI in your concierge medicine model today?",
                 "answer_bullets": ["We integrate AI as a clinical support tool.", "Our physicians use AI-assisted diagnostics.", "The result is more proactive care."]},
                {"question": "What outcomes data do you have from your technology integration?",
                 "answer_bullets": ["Acme Corp members have 79% fewer hospital admissions.", "Our AI tools have measurably improved efficiency by 30%."]},
            ],
        },
        "talking_points": [
            {"topic_label": "AI in Concierge Medicine (April 2026)",
             "points": [{"header": "On AI as a clinical partner", "bullets": ["AI works best when it amplifies physician judgment.", "In concierge medicine, we have the time to use AI properly."]}]},
        ],
        "relevant_news": [
            {"date": "5/5", "headline": "AI reduces diagnostic errors by 40%", "url": "https://example.com", "source": "Healthcare IT News",
             "bullets": ["AI-assisted diagnosis reduced errors by 40%.", "Study tracked 50,000 patient encounters.", "Relevant to Arjun's AI healthcare angle."]},
        ],
        "key_messaging": {
            "about_company": "Acme Corp is the nation's leading concierge medicine network with more than 1,100 affiliated physicians.",
        },
        "previous_transcripts": [],
        "interview_tips": {
            "bridging_phrases": ['"Yes, and let me tell you where that will lead…"', '"No, actually, the way we see the situation is…"'],
            "flagging_phrases": ['"The top priority is…"', '"The biggest concern in today\'s environment is…"'],
            "dos":   [row["do"]   for row in DOS_DONTS_LONG],
            "donts": [row["dont"] for row in DOS_DONTS_LONG],
        },
    }

    result = create_brief_doc(test_data)
    print(f"\n✅ Test doc created!")
    print(f"   Title: {result['doc_title']}")
    print(f"   URL:   {result['doc_url']}")
    print(f"\nCheck: https://drive.google.com/drive/folders/1LhPQ8Royx15nrgc9BBa9RYiiS6sfo4Pm")

=== data_gatherer.py ===
"""
data_gatherer.py — AVENUE Z MEDIA BRIEF BUILDER
Python data gathering layer. Replaces Agents 1, 2, and 3.
No LLM involved. All calls are deterministic Python.

Functions:
  gather_reporter_data()    — scrapes reporter page (replaces Agent 1)
  gather_client_context()   — 6 direct Glean API calls (replaces Agent 2)
  gather_news()             — Serper news search (replaces Agent 3)
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
GLEAN_ACT_AS     = "thomas.chang@avenuez.com"


def _glean_headers() -> dict:
    return {
        "Authorization": f"Bearer {GLEAN_API_TOKEN}",
        "X-Glean-ActAs": GLEAN_ACT_AS,
        "Content-Type": "application/json",
    }


def _glean_search(query: str, max_snippets: int = 5000, filter_terms: list = None) -> str:
    """Direct Glean search — returns raw text snippets. No agent, no LLM.

    filter_terms: if provided, a result document is only included when at least
    one term appears (case-insensitive) in its title or snippet text. Prevents
    cross-client contamination when searching for client-specific documents.
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
            # Skip Drive folder containers — they have 0 snippets and contain no
            # searchable text. They displace real documents in the top results.
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


# ─────────────────────────────────────────────────────────────────
# LAYER 1A — REPORTER DATA
# Calls the existing scrape_reporter_page tool.
# Adds scrape_confidence field so Gemini knows data quality.
# ─────────────────────────────────────────────────────────────────

def gather_reporter_data(brief_request: Any) -> dict:
    """
    Scrape reporter page and return structured data with confidence score.
    For podcast/broadcast URLs (Apple, Spotify), falls back to web search.
    Returns dict with all reporter fields + scrape_confidence.
    """
    from tools import scrape_reporter_page

    reporter_url = brief_request.reporter_url
    print(f"[data_gatherer] Scraping reporter: {reporter_url}")

    # Detect podcast/broadcast platform URLs — httpx can't scrape these
    podcast_platforms = [
        "podcasts.apple.com",
        "open.spotify.com",
        "podcasts.google.com",
        "overcast.fm",
        "pocketcasts.com",
    ]
    is_podcast_platform = any(p in reporter_url for p in podcast_platforms)

    # Get host_name from BriefRequest if provided (form field for Podcast/Broadcast)
    host_name = getattr(brief_request, "host_name", None) or ""

    if is_podcast_platform and host_name:
        # Podcast platform URL — scraper won't work, use web search for host bio
        print(f"[data_gatherer] Podcast platform detected — using web search for host: {host_name}")
        reporter_data = _gather_podcast_host(host_name, reporter_url)
    else:
        # Standard outlet URL — use existing scraper
        try:
            raw = scrape_reporter_page.run(reporter_url=reporter_url)
            reporter_data = json.loads(raw)
        except Exception as e:
            print(f"[data_gatherer] Scrape failed: {e}")
            reporter_data = {}

    # Add scrape_confidence — Gemini uses this to know how hard to work
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

    # Extract outlet from bio if scraper didn't return it
    if not reporter_data.get("outlet") and reporter_data.get("bio"):
        bio = reporter_data["bio"]
        # Pattern: "Name is [Outlet]'s ..." or "Name is a reporter at [Outlet]"
        m = re.search(r"is ([A-Z][A-Za-z0-9 &]+?)(?:'s|'s| reporter| correspondent| editor| journalist| senior| staff)", bio)
        if m:
            reporter_data["outlet"] = m.group(1).strip()
        elif reporter_data.get("url",""):
            # Derive from URL domain e.g. cnbc.com -> CNBC, wsj.com -> WSJ
            from urllib.parse import urlparse
            domain = urlparse(reporter_data.get("url","")).netloc.lower().replace("www.","")
            outlet_map = {
                "cnbc.com": "TechNews", "wsj.com": "The Wall Street Journal",
                "bloomberg.com": "Bloomberg", "nytimes.com": "The New York Times",
                "reuters.com": "Reuters", "forbes.com": "Forbes",
                "axios.com": "Axios", "techcrunch.com": "TechCrunch",
                "ft.com": "Financial Times", "barrons.com": "Barron's",
                "pitchbook.com": "PitchBook", "theblock.co": "The Block",
                "coindesk.com": "CoinDesk", "benefitnews.com": "Employee Benefit News",
            }
            reporter_data["outlet"] = outlet_map.get(domain, domain.split(".")[0].upper())

    # ── FALLBACK CHAIN — fires when scraper returns confidence=low ──
    # Sources: Glean → Serper web → LinkedIn via Serper → Wikipedia API
    # Covers sites that block scraping (FT, Blockworks, WSJ, etc.)
    if confidence == "low":
        print(f"[data_gatherer] Confidence low — running full fallback chain")

        # ── STEP 0: Resolve real reporter name universally ──
        reporter_name_guess = name
        from urllib.parse import urlparse as _urlparse
        outlet_domain = _urlparse(reporter_url).netloc.lower().replace("www.", "")
        slug = reporter_url.rstrip("/").split("/")[-1]
        slug_clean = slug.replace("-", " ").replace("_", " ").strip()

        # If host_name was explicitly provided on the request (Podcast/Broadcast),
        # skip slug-based name resolution entirely. Slug resolution returns garbage
        # for show URLs like /pevaluecreation, /value-creation, /show-name, etc.
        # because Google indexes the slug, not a person.
        if host_name:
            reporter_name_guess = host_name
            reporter_data["name"] = host_name
            print(f"[data_gatherer] Step 0 skipped — using host_name from request: {host_name}")
        elif not reporter_name_guess or (reporter_name_guess and " " not in reporter_name_guess):
            # No host_name provided — try LinkedIn/Muck Rack to resolve from slug
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
                        print(f"[data_gatherer] Name resolved: {reporter_name_guess}")
            except Exception:
                pass
            if not reporter_name_guess:
                reporter_name_guess = slug_clean.title()
                reporter_data["name"] = reporter_name_guess

        # ── FALLBACK 1: Glean — skip spreadsheets and lists, bio only ──
        try:
            glean_text = _glean_search(f"{reporter_name_guess} reporter bio")
            non_bio_signals = ["MASTER", "spreadsheet", "# ", "@", "Co-Host", "LIST",
                               "email", "phone", "extension", "SELECT", "INSERT",
                               "Media Brief", "media brief", "Talking Points", "talking points",
                               "Potential Questions", "Interview Tips"]
            glean_is_bio = (
                glean_text and
                len(glean_text) > 100 and
                not any(s in glean_text[:300] for s in non_bio_signals)
            )
            if glean_is_bio:
                if not reporter_data.get("bio"):
                    reporter_data["bio"] = glean_text[:800]
                if not reporter_data.get("name"):
                    reporter_data["name"] = reporter_name_guess
                print(f"[data_gatherer] Fallback 1 (Glean): {len(glean_text)} chars")
            else:
                print(f"[data_gatherer] Fallback 1 (Glean): skipped (non-bio content)")
        except Exception as e:
            print(f"[data_gatherer] Fallback 1 (Glean) error: {e}")

        # ── FALLBACK 2: Outlet byline search — universally reliable for articles ──
        # site:{outlet} "{reporter_name}" — works for any outlet that allows Google indexing
        try:
            byline_resp = httpx.post(
                "https://google.serper.dev/search",
                json={"q": f'site:{outlet_domain} "{reporter_name_guess}"', "num": 8},
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                timeout=15,
            )
            byline_resp.raise_for_status()
            byline_results = byline_resp.json().get("organic", [])
            skip_title_words = ["profile", "biography", "alumni", "about", "contact",
                                "speaker", "convention", "conference", "meet the", "author page",
                                "posts of", "articles by", "all articles", "author:", "written by"]
            byline_articles = []
            for r in byline_results[:8]:
                title = r.get("title", "")
                link  = r.get("link", "")
                date  = r.get("date", "")
                if not title or not link:
                    continue
                if any(w in title.lower() for w in skip_title_words):
                    continue
                byline_articles.append({"title": title, "url": link, "date": date})
            if byline_articles:
                reporter_data["recent_articles"] = byline_articles[:5]
                print(f"[data_gatherer] Fallback 2 (outlet byline): {len(byline_articles[:5])} articles")
        except Exception as e:
            print(f"[data_gatherer] Fallback 2 (outlet byline) error: {e}")

        # ── FALLBACK 3: Serper general search — bio + articles if still missing ──
        try:
            # Query construction — context-aware by brief type.
            # For Podcast/Broadcast (host_name set): seed with show_name or "podcast host".
            # For standard journalists: keep the "journalist reporter" seed unchanged.
            # This is the core fix for wrong-person disambiguation — the right query
            # eliminates wrong-person results at the source, not by post-filtering.
            if host_name:
                show_name_ctx = getattr(brief_request, "show_name", None) or ""
                if show_name_ctx:
                    f3_query = f"{reporter_name_guess} {show_name_ctx}"
                else:
                    f3_query = f"{reporter_name_guess} podcast host"
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
                # Bio-signal words — expanded for podcast/broadcast hosts.
                # Hosts use "founder", "ceo", "host", "author" rather than journalist vocabulary.
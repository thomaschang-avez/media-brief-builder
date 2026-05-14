"""
tasks.py — MEDIA BRIEF BUILDER
5 tasks mapping 1:1 to the 5 agents.
Context chaining is set in crew.py AFTER building all tasks.

CRITICAL: Task 4 (brief assembler) output JSON schema MUST match
what brief_builder.py expects to parse. Do not change field names.
"""

from crewai import Task
from typing import Any, List


# ─────────────────────────────────────────────────────────────────
# TASK 1 — REPORTER PROFILE
# Input: reporter URL from BriefRequest
# Output: complete reporter profile JSON
# ─────────────────────────────────────────────────────────────────

def build_task_reporter(agent: Any, brief_request: Any) -> Task:
    rules = brief_request.brief_type_rules
    coverage_label = rules["coverage_label"]
    reporter_label = rules["reporter_section_label"]

    return Task(
        description=(
            f"Scrape and build a complete profile for the reporter/host at: {brief_request.reporter_url}\n\n"
            f"This is for a {brief_request.brief_type} media brief.\n"
            f"The profile will become the '{reporter_label}' section.\n\n"
            "STEPS:\n"
            "1. Extract the reporter name from the URL itself first.\n"
            f"   The URL is: {brief_request.reporter_url}\n"
            "   Example: cnbc.com/arjun-kharpal/ = Arjun Kharpal, wsj.com/ben-cohen/ = Ben Cohen\n"
            "2. Use scrape_reporter_page tool with the URL above\n"
            "3. CRITICAL VALIDATION: Check the name in the scrape result against the URL-extracted name.\n"
            "   If they do not match, DISCARD the scrape result and use the URL-extracted name.\n"
            "4. If scrape raw_text is under 300 characters OR name does not match URL: search Glean for the reporter\n"
            f"   Use query: reporter name from URL + outlet name\n"
            "5. NEVER fabricate a reporter name, bio, outlet, or coverage items. Ever.\n"
            "6. Return structured JSON — use null for genuinely unavailable fields\n\n"
            f"The '{coverage_label}' list must have 4-5 items with dates in M/DD format."
        ),
        expected_output=(
            f"""Valid JSON matching this schema exactly:
{{
  "name": "Reporter full name",
  "outlet": "Publication or show name",
  "author_page_url": "{brief_request.reporter_url}",
  "headshot_url": "Direct image URL or null",
  "headshot_base64": "base64 encoded image string from scrape_reporter_page tool",
  "headshot_mime_type": "image/jpeg or image/png",
  "linkedin_url": "LinkedIn profile URL or null",
  "twitter_url": "X/Twitter profile URL or null",
  "bio_paragraph_1": "Current role, location, and main beat — what they cover",
  "bio_paragraph_2": "Career background, previous outlets, education if available",
  "coverage_label": "{coverage_label}",
  "recent_coverage": [
    {{"date": "M/DD", "headline": "Article or episode title", "url": "URL or null"}},
    {{"date": "M/DD", "headline": "Article or episode title", "url": "URL or null"}},
    {{"date": "M/DD", "headline": "Article or episode title", "url": "URL or null"}},
    {{"date": "M/DD", "headline": "Article or episode title", "url": "URL or null"}},
    {{"date": "M/DD", "headline": "Article or episode title", "url": "URL or null"}}
  ],
  "beat_summary": "One sentence describing what this reporter covers and their style",
  "source": "reporter_page or linkedin_fallback or glean"
}}"""
        ),
        agent=agent,
    )


# ─────────────────────────────────────────────────────────────────
# TASK 2 — CLIENT CONTEXT
# Input: client name + exec name from BriefRequest
# Output: all internal knowledge on this client
# ─────────────────────────────────────────────────────────────────

def build_task_client_context(agent: Any, brief_request: Any) -> Task:
    rules = brief_request.brief_type_rules
    needs_transcripts = "previous_transcripts" in rules["extra_sections"]

    return Task(
        description=(
            f"Search Glean for ALL internal Avenue Z knowledge about:\n"
            f"Client: {brief_request.client_name}\n"
            f"Executive: {brief_request.exec_name}\n"
            f"Interview topic: {brief_request.topic}\n\n"
            "Run these searches IN ORDER — each is a separate glean_search call:\n"
            f"1. '{brief_request.client_name} media brief'\n"
            f"2. '{brief_request.exec_name} talking points'\n"
            f"3. '{brief_request.client_name} pitchbook'\n"
            f"4. '{brief_request.client_name} messaging FAQ'\n"
            f"5. '{brief_request.exec_name} commentary'\n"
            f"6. '{brief_request.client_name} about boilerplate'\n"
            + (f"7. '{brief_request.exec_name} transcript broadcast podcast'\n" if needs_transcripts else "") +
            "\nFor talking points: extract VERBATIM — the exact words, not a summary.\n"
            "Label each talking point cluster with topic and date (e.g. 'AI Strategy (March 2026)').\n"
            "For boilerplate: find the standard 'About [Company]' paragraph used across all briefs.\n"
            + ("For transcripts: extract full verbatim Q&A exchanges — do not summarize.\n" if needs_transcripts else "")
        ),
        expected_output=(
            f"""Valid JSON matching this schema exactly:
{{
  "client_name": "{brief_request.client_name}",
  "exec_name": "{brief_request.exec_name}",
  "talking_points": [
    {{
      "topic_label": "Topic Name (Month Year)",
      "points": [
        {{
          "header": "Bold sub-topic header or null",
          "bullets": ["verbatim bullet 1", "verbatim bullet 2", "verbatim bullet 3"]
        }}
      ]
    }}
  ],
  "about_boilerplate": "The standard About [Company] paragraph, verbatim",
  "mission_statement": "Company mission statement or null",
  "faq_items": [
    {{"question": "Q text", "answer": "A text"}}
  ],
  "past_brief_qa": [
    {{"question": "Q", "answer": "Past answer verbatim"}}
  ],
  "previous_transcripts": [
    {{
      "show_name": "Show name",
      "date": "Date",
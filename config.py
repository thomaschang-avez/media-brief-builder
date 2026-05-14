"""
config.py — MEDIA BRIEF BUILDER
Validate: python3 config.py
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()

GLEAN_SERVER_URL    = os.environ["GLEAN_SERVER_URL"]
GLEAN_API_TOKEN     = os.environ["GLEAN_API_TOKEN"]
SLACK_BOT_TOKEN     = os.environ["SLACK_BOT_TOKEN"]
SERPER_API_KEY      = os.environ.get("SERPER_API_KEY", "")
GEMINI_PROJECT      = os.environ.get("GEMINI_PROJECT", "your-gcp-project-id")
GEMINI_LOCATION     = os.environ.get("GEMINI_LOCATION", "us-central1")
GLEAN_ACT_AS        = os.environ.get("GLEAN_ACT_AS", "you@yourcompany.com")

PR_BRIEFS_FOLDER_ID         = os.environ.get("PR_BRIEFS_FOLDER_ID", "")
MEDIA_BRIEF_EXAMPLES_FOLDER = os.environ.get("MEDIA_BRIEF_EXAMPLES_FOLDER", "YOUR_GDRIVE_FOLDER_ID")

BRIEF_TYPES = ["Interview", "Intro", "In-Person", "Broadcast", "Podcast"]

# ─────────────────────────────────────────────────────────────────
# BRIEF TYPE RULES
# Source of truth is brief_standards.py — these are derived from it.
# Do NOT hardcode labels or flags here — update brief_standards.py instead.
# ─────────────────────────────────────────────────────────────────

from brief_standards import (
    QA_SPEC,
    NEWS_SPEC,
    REPORTER_SECTION,
    TOC_RULES,
    OPPORTUNITY_BOLD_DESCRIPTORS,
    TALKING_POINTS_SPEC,
    DOS_DONTS_SHORT,
    DOS_DONTS_LONG,
    TIPS_BULLETS,
    BEST_PRACTICES_LINE,
    TIPS_TABLE,
    get_tips_table,
)

BRIEF_TYPE_RULES = {
    "Interview": {
        "reporter_depth":         "deep",
        "qa_has_answers":         QA_SPEC["Interview"]["answers"],
        "qa_label":               QA_SPEC["Interview"]["label"],
        "qa_count":               QA_SPEC["Interview"]["count"],
        "news_required":          NEWS_SPEC["Interview"]["include"] == "required",
        "news_excluded":          NEWS_SPEC["Interview"]["include"] == "excluded",
        "news_count":             NEWS_SPEC["Interview"]["count"],
        "stats_section":          True,
        "has_toc":                TOC_RULES["Interview"]["include"],
        "toc_label":              TOC_RULES["Interview"].get("label", "Contents:"),
        "reporter_section_label": "Reporter Information",
        "coverage_label":         REPORTER_SECTION["Interview"]["coverage_label"].rstrip(":"),
        "tips_table":             DOS_DONTS_SHORT,
        "bold_descriptor":        OPPORTUNITY_BOLD_DESCRIPTORS["Interview"]["real_example"],
        "talking_points_label":   TALKING_POINTS_SPEC["Interview"]["label"],
        "extra_sections":         [],
    },
    "Intro": {
        "reporter_depth":         "standard",
        "qa_has_answers":         QA_SPEC["Intro"]["answers"],
        "qa_label":               QA_SPEC["Intro"]["label"],
        "qa_count":               QA_SPEC["Intro"]["count"],
        "news_required":          False,
        "news_excluded":          False,
        "news_count":             NEWS_SPEC["Intro"]["count"],
        "stats_section":          False,
        "has_toc":                TOC_RULES["Intro"]["include"],
        "toc_label":              TOC_RULES["Intro"].get("label", ""),
        "reporter_section_label": "Reporter Information",
        "coverage_label":         REPORTER_SECTION["Intro"]["coverage_label"].rstrip(":"),
        "tips_table":             DOS_DONTS_SHORT,
        "bold_descriptor":        OPPORTUNITY_BOLD_DESCRIPTORS["Intro"]["real_example"],
        "talking_points_label":   TALKING_POINTS_SPEC["Intro"]["label"],
        "extra_sections":         [],
    },
    "In-Person": {
        "reporter_depth":         "standard",
        "qa_has_answers":         QA_SPEC["In-Person"]["answers"],
        "qa_label":               QA_SPEC["In-Person"]["label"],
        "qa_count":               QA_SPEC["In-Person"]["count"],
        "news_required":          NEWS_SPEC["In-Person"]["include"] == "required",
        "news_excluded":          False,
        "news_count":             NEWS_SPEC["In-Person"]["count"],
        "stats_section":          False,
        "has_toc":                TOC_RULES["In-Person"]["include"],
        "toc_label":              TOC_RULES["In-Person"].get("label", ""),
        "reporter_section_label": "Reporter Information",
        "coverage_label":         REPORTER_SECTION["In-Person"]["coverage_label"].rstrip(":"),
        "tips_table":             DOS_DONTS_SHORT,
        "bold_descriptor":        OPPORTUNITY_BOLD_DESCRIPTORS["In-Person"]["real_example"],
        "talking_points_label":   TALKING_POINTS_SPEC["In-Person"]["label"],
        "extra_sections":         ["staffing_note", "location_details"],
    },
    "Broadcast": {
        "reporter_depth":         "standard",
        "qa_has_answers":         QA_SPEC["Broadcast"]["answers"],
        "qa_label":               QA_SPEC["Broadcast"]["label"],
        "qa_count":               QA_SPEC["Broadcast"]["count"],
        "news_required":          NEWS_SPEC["Broadcast"]["include"] == "required",
        "news_excluded":          False,
        "news_count":             NEWS_SPEC["Broadcast"]["count"],
        "stats_section":          False,
        "has_toc":                TOC_RULES["Broadcast"]["include"],
        "toc_label":              TOC_RULES["Broadcast"].get("label", "Table of Contents:"),
        "reporter_section_label": "About the Host",
        "coverage_label":         REPORTER_SECTION["Broadcast"]["coverage_label"].rstrip(":"),
        "tips_table":             DOS_DONTS_LONG,
        "bold_descriptor":        OPPORTUNITY_BOLD_DESCRIPTORS["Broadcast"]["real_example"],
        "talking_points_label":   TALKING_POINTS_SPEC["Broadcast"]["label"],
        "extra_sections":         ["live_or_recorded", "tech_requirements", "arrival_hit_time", "previous_transcripts"],
    },
    "Podcast": {
        "reporter_depth":         "standard",
        "qa_has_answers":         QA_SPEC["Podcast"]["answers"],
        "qa_label":               QA_SPEC["Podcast"]["label"],
        "qa_count":               QA_SPEC["Podcast"]["count"],
        "news_required":          False,
        "news_excluded":          True,
        "news_count":             0,
        "stats_section":          False,
        "has_toc":                TOC_RULES["Podcast"]["include"],
        "toc_label":              TOC_RULES["Podcast"].get("label", ""),
        "reporter_section_label": "About the Host",
        "coverage_label":         REPORTER_SECTION["Podcast"]["coverage_label"].rstrip(":"),
        "tips_table":             DOS_DONTS_LONG,
        "bold_descriptor":        OPPORTUNITY_BOLD_DESCRIPTORS["Podcast"]["real_example"],
        "talking_points_label":   TALKING_POINTS_SPEC["Podcast"]["label"],
        "extra_sections":         ["live_or_recorded", "tech_requirements", "expected_topics", "previous_transcripts"],
    },
}

# Map PR team emails to Slack user IDs.
# Populate with your team's emails and Slack IDs (from Slack profile → Member ID).
# Live lookup via users.lookupByEmail fires as fallback for any unrecognized email.
PR_TEAM_EMAIL_TO_SLACK: dict[str, str] = {
    # "name@yourcompany.com": "UXXXXXXXXXX",
}

FALLBACK_SLACK_USER_ID = os.environ.get("SLACK_FALLBACK_USER_ID", "YOUR_FALLBACK_SLACK_USER_ID")
ERROR_CHANNEL          = os.environ.get("SLACK_ERROR_CHANNEL", "YOUR_ERROR_CHANNEL_ID")
TEST_CHANNEL           = os.environ.get("SLACK_TEST_CHANNEL", "YOUR_TEST_CHANNEL_ID")
ADMIN_SLACK_ID         = os.environ.get("SLACK_ADMIN_USER_ID", "YOUR_ADMIN_SLACK_USER_ID")
USE_TEST_CHANNEL       = False


@dataclass
class BriefRequest:
    client_name: str
    exec_name: str
    reporter_url: str
    brief_type: str
    interview_date: str
    interview_time: str
    virtual_or_inperson: str
    topic: str
    on_record: str
    staffed: str
    submitter_email: str
    location_or_link: Optional[str] = None
    staffer_name: Optional[str] = None
    additional_context: Optional[str] = None

    # ── Podcast / Broadcast specific fields ──
    host_name: Optional[str] = None
    show_links: Optional[Dict[str, str]] = None
    expected_topics: Optional[List[str]] = None
    show_name: Optional[str] = None
    recent_episodes_url: Optional[str] = None

    # ── Broadcast-specific fields ──
    arrival_time: Optional[str] = None
    hit_time: Optional[str] = None
    segment_length: Optional[str] = None
    prior_appearance_urls: Optional[List[str]] = None

    # ── Form upload fields ──
    client_logo_url: Optional[str] = None
    reporter_headshot_url: Optional[str] = None

    @property
    def submitter_slack_id(self) -> str:
        return PR_TEAM_EMAIL_TO_SLACK.get(self.submitter_email.lower(), FALLBACK_SLACK_USER_ID)

    @property
    def brief_type_rules(self) -> dict:
        return BRIEF_TYPE_RULES.get(self.brief_type, BRIEF_TYPE_RULES["Interview"])

    @property
    def doc_title(self) -> str:
        from brief_standards import TITLE_PATTERNS
        pattern = TITLE_PATTERNS.get(self.brief_type, "{exec_name}, {client} | {outlet} Media Brief")
        return pattern.format(
            exec_name=self.exec_name,
            client=self.client_name,
            outlet="",
            show_name="",
            reporter_name="",
        ).strip(" |,")

    @property
    def is_broadcast_or_podcast(self) -> bool:
        return self.brief_type in ("Broadcast", "Podcast")

    @property
    def is_inperson(self) -> bool:
        return self.virtual_or_inperson == "In-Person"

    @property
    def is_staffed(self) -> bool:
        return self.staffed == "Yes"


INTERVIEW_TIPS_AND_TRICKS = {
    "best_practices": [b["subs"] for b in TIPS_BULLETS if "subs" in b][0],
    "dos":   [row["do"]   for row in DOS_DONTS_LONG],
    "donts": [row["dont"] for row in DOS_DONTS_LONG],
    "bridging_phrases": [
        '"Yes, and let me tell you where that will lead..."',
        '"No, actually, the way we see the situation is..."',
    ],
    "flagging_phrases": [
        '"The top priority is..."',
        '"The biggest concern in today’s environment is..."',
    ],
}

BROADCAST_TECH_REQUIREMENTS = (
    "Business casual attire. Quiet, well-lit space. Neat, plain background. "
    "Headphones with a mic. Avoid virtual backgrounds."
)


if __name__ == "__main__":
    print("config.py loaded\n")
    print(f"Brief types: {BRIEF_TYPES}")
    print(f"Gemini project: {GEMINI_PROJECT}")

    for bt in BRIEF_TYPES:
        rules = BRIEF_TYPE_RULES[bt]
        print(f"\n  {bt}:")
        print(f"    bold_descriptor:  {rules['bold_descriptor']}")
        print(f"    qa_label:         {rules['qa_label']}")
        print(f"    qa_count:         {rules['qa_count']}")
        print(f"    qa_has_answers:   {rules['qa_has_answers']}")
        print(f"    news_required:    {rules['news_required']}")
        print(f"    news_excluded:    {rules['news_excluded']}")
        print(f"    has_toc:          {rules['has_toc']}")
        print(f"    tips_rows:        {len(rules['tips_table'])}")
        print(f"    reporter_label:   {rules['reporter_section_label']}")

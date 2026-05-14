"""
brief_standards.py — MEDIA BRIEF PIPELINE
The single source of truth for all 5 brief types.

Sourced from:
  1. PR Training materials — the authority
  2. Real brief examples across all 5 types
     (Intro, In-Person, Interview, Broadcast, Podcast)

Every formatting decision, every label, every section order, every bold pattern,
every Q&A count, every bullet count — traced to a specific real brief.

Hierarchy:
  PR training materials > Real brief examples > This file
  If this file contradicts a real brief, the real brief wins. Update this file.

Every other file in the pipeline imports from here. Nothing hardcoded elsewhere.

Validate: python3 brief_standards.py
"""

from typing import Dict, List, Optional, Tuple


VALID_BRIEF_TYPES = ["Interview", "Intro", "In-Person", "Broadcast", "Podcast"]


# ═══════════════════════════════════════════════════════════════════════
# TITLE FORMAT
#
# Pattern: "{Exec}, {Client} | {Reporter/Host}, {Outlet} Media Brief"
# Broadcast adds: "Broadcast Media Brief"
# Podcast uses: "Podcast Brief"
# ═══════════════════════════════════════════════════════════════════════

TITLE_PATTERNS = {
    "Interview": "{exec_name}, {client} | {reporter_name}, {outlet} Media Brief",
    "Intro":     "{client} | {outlet} Media Brief",
    "In-Person": "{client} | {outlet} Media Brief",
    "Broadcast": "{exec_name}, {client} | {show_name} Broadcast Media Brief",
    "Podcast":   "{exec_name}, {client} | {show_name} Podcast Brief",
}


# ═══════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ═══════════════════════════════════════════════════════════════════════

TOC_RULES = {
    "Interview": {"include": True, "label": "Contents:"},
    "Intro":     {"include": False},
    "In-Person": {"include": False},
    "Broadcast": {"include": True, "label": "Table of Contents:"},
    "Podcast":   {"include": False},
}


# ═══════════════════════════════════════════════════════════════════════
# LOGISTICS FORMAT
# ═══════════════════════════════════════════════════════════════════════

LOGISTICS_FIELDS = {
    "Interview": {
        "fields": ["Date/Time:", "Location:", "Attendees:"],
        "attendee_format": [
            "{exec_name}, *{client}*",
            "{reporter_name}, *{outlet}*",
            "{staffer_name}, *Avenue Z (will be staffing)*",
        ],
    },
    "Intro": {
        "fields": ["Date/Time:", "Location:", "Attendees:"],
        "attendee_format": [
            "{exec_name}, *{client}*",
            "{reporter_name}, *{outlet}*",
            "{staffer_name}, *Avenue Z*",
        ],
    },
    "In-Person": {
        "fields": ["Date/Time:", "Location:", "Attendees:"],
        "location_note": "Full address in italics: Venue *(street address)*",
        "attendee_format": [
            "{exec_name}, *{client}*",
            "{reporter_name}, *{outlet}*",
            "{staffer_name}, *Avenue Z (will be staffing)*",
        ],
    },
    "Broadcast": {
        "fields": ["Date:", "Arrival Time:", "Hit Time:", "Location:", "Attendees:"],
        "arrival_time_bold": True,
        "hit_time_bold": True,
        "attendee_format": [
            "{exec_name}, *{client}*",
            "{reporter_name}, *{show_name}*",
            "{staffer_name}, *Avenue Z (will be staffing)*",
        ],
    },
    "Podcast": {
        "fields": ["Date:", "Location:", "Attendees:"],
        "location_note": "Recording platform link (e.g. Riverside)",
        "attendee_format": [
            "{exec_name}, *{client}*",
            "{host_name}, *{show_name}*",
            "{producer_name}, *{show_name}*",
            "{staffer_name}, *Avenue Z (will be staffing)*",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════
# OPPORTUNITY SECTION — BOLD DESCRIPTOR + PARAGRAPH STRUCTURE
# ═══════════════════════════════════════════════════════════════════════

OPPORTUNITY_BOLD_DESCRIPTORS = {
    "Interview": {
        "pattern": "**{virtual_or_inperson}, {record_status}**",
        "real_example": "**virtual, on-the-record**",
        "paragraph_count": 3,
    },
    "Intro": {
        "pattern": "**{record_status}, {virtual_or_inperson}**",
        "real_example": "**on-record, virtual**",
        "paragraph_count": 2,
    },
    "In-Person": {
        "pattern": "**{record_status}, in-person**",
        "real_example": "**on-record, in-person**",
        "paragraph_count": 3,
    },
    "Broadcast": {
        "pattern": "**{live_or_recorded} broadcast**",
        "real_example": "**live broadcast**",
        "paragraph_count": 2,
    },
    "Podcast": {
        "pattern": "**{audio_or_video}**",
        "real_example": "**audio and video**",
        "paragraph_count": 2,
    },
}

OPPORTUNITY_CHECKLIST = {
    "Interview": [
        "bold_descriptor", "reporter name+title+outlet+beat",
        "what story/topic", "meeting length", "what to prepare",
        "why valuable", "comfort language", "staffing note", "on-record reminder",
    ],
    "Intro": [
        "bold_descriptor", "reporter name+title+outlet+beat",
        "reporter interests", "relationship-building framing",
        "'ask what they're currently working on'", "staffing note", "on-record reminder",
    ],
    "In-Person": [
        "bold_descriptor", "reporter name+title+outlet+beat",
        "full venue address", "relationship-building framing",
        "'ask what she's currently working on'", "staffing note", "on-record reminder",
    ],
    "Broadcast": [
        "bold_descriptor", "show name+host name", "segment length",
        "specific topic", "arrival+hit time+entry instructions",
        "attire guidance", "staffing note",
    ],
    "Podcast": [
        "bold_descriptor", "show name+host name", "episode length",
        "prior meeting context", "tech requirements", "staffing note",
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# REPORTER / HOST SECTION
# ═══════════════════════════════════════════════════════════════════════

REPORTER_HEADER_FORMAT = {
    "Interview": '[{name}]({url}), {outlet} | Social Media: [LinkedIn]({linkedin}) | [X]({twitter})',
    "Intro":     '{name}, {outlet} | Social Media: [LinkedIn]({linkedin}) | [X]({twitter})',
    "In-Person": '{name}, {outlet} | Social Media: [LinkedIn]({linkedin}) | [X]({twitter})',
    "Broadcast": '{name}, {show_name}\nSocial Media: [LinkedIn]({linkedin})',
    "Podcast":   '{name} | Social Media: [LinkedIn]({linkedin})',
}

REPORTER_SECTION = {
    "Interview": {"coverage_label": "Recent Coverage:", "min": 4, "max": 5, "bio_paras": 2, "headshot": True},
    "Intro":     {"coverage_label": "Recent Coverage:", "min": 4, "max": 4, "bio_paras": 2, "headshot": True},
    "In-Person": {"coverage_label": "Recent Coverage:", "min": 4, "max": 4, "bio_paras": 1, "headshot": True},
    "Broadcast": {"coverage_label": "Recent Clips:", "min": 4, "max": 5, "bio_paras": 1, "headshot": False,
                  "social_separate_line": True},
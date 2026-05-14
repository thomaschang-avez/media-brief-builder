"""
agents.py — MEDIA BRIEF BUILDER
5 specialist agents. All running gemini-2.5-flash.

Agent 1 — Reporter Intelligence Officer  (gemini-2.5-flash)
Agent 2 — Client Memory Bank             (gemini-2.5-flash)
Agent 3 — News Desk                      (gemini-2.5-flash)
Agent 4 — Senior PR Strategist           (gemini-2.5-flash)
Agent 5 — QA Assassin                    (gemini-2.5-flash)
"""

from __future__ import annotations
import os
import json
import concurrent.futures
from typing import Any
from dotenv import load_dotenv
from crewai import Agent
from crewai.llm import BaseLLM
from pydantic import Field, PrivateAttr
from google import genai
from google.oauth2 import service_account
from tools import (
    scrape_reporter_page,
    glean_search,
    glean_read_document,
    web_search,
)
from config import (
    GEMINI_PROJECT,
    GEMINI_LOCATION,
    MEDIA_BRIEF_EXAMPLES_FOLDER,
    BROADCAST_TECH_REQUIREMENTS,
)

load_dotenv()


class GeminiLLM(BaseLLM):
    model: str = Field(default="gemini-2.5-flash")
    _client: Any = PrivateAttr()

    def model_post_init(self, __context: Any) -> None:
        service_account_json = os.environ.get("GEMINI_SERVICE_ACCOUNT")
        if service_account_json:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(service_account_json),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self._client = genai.Client(
                vertexai=True,
                project=GEMINI_PROJECT,
                location=GEMINI_LOCATION,
                credentials=creds,
            )
        else:
            self._client = genai.Client(
                vertexai=True,
                project=GEMINI_PROJECT,
                location=GEMINI_LOCATION,
            )

    def call(
        self,
        messages: str | list[dict],
        tools: list | None = None,
        callbacks: list | None = None,
        available_functions: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        system_instruction = None
        content_parts: list[str] = []

        for msg in messages:
            role    = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_instruction = content
            elif role == "assistant":
                content_parts.append(f"[ASSISTANT]\n{content}")
            else:
                content_parts.append(content)

        if tools:
            tool_descriptions = []
            for t in tools:
                if isinstance(t, dict):
                    func   = t.get("function", t)
                    name   = func.get("name", "unknown")
                    desc   = func.get("description", "")
                    params = func.get("parameters", {})
                    tool_descriptions.append(f"- {name}: {desc}\n  Parameters: {params}")
            if tool_descriptions:
                content_parts.append(
                    "\n[AVAILABLE TOOLS]\n" + "\n".join(tool_descriptions) + "\n\n"
                    "To use a tool, respond with:\n"
                    "Action: <tool_name>\nAction Input: <json arguments>\n"
                )

        full_content = "\n\n".join(content_parts)
        config: dict = {}
        if system_instruction:
            config["system_instruction"] = system_instruction

        def _call_gemini():
            return self._client.models.generate_content(
                model=self.model,
                contents=full_content,
                config=config if config else None,
            )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_call_gemini)
                response = future.result(timeout=150)
            return response.text
        except concurrent.futures.TimeoutError:
            return "Error: Gemini API call timed out after 150 seconds."
        except Exception as e:
            return f"Error: Gemini API call failed: {e}"

    def get_context_window_size(self) -> int:
        return 1_000_000


def create_gemini_llm() -> GeminiLLM:
    """All agents use gemini-2.5-flash."""
    return GeminiLLM(model="gemini-2.5-flash")


def build_reporter_agent(brief_request: Any) -> Agent:
    rules          = brief_request.brief_type_rules
    reporter_label = rules["reporter_section_label"]
    coverage_label = rules["coverage_label"]
    is_bc_pod      = brief_request.is_broadcast_or_podcast

    return Agent(
        role="Reporter Intelligence Officer",
        goal=(
            f"Build a complete, accurate profile of the reporter or host at {brief_request.reporter_url}. "
            f"This profile will become the '{reporter_label}' section of a professional media brief. "
            f"You must extract: full name, outlet, bio (2 paragraphs), headshot image (as base64), "
            f"LinkedIn URL, X/Twitter URL, and {coverage_label} (4-5 most recent headlines with dates and URLs). "
            f"{'For a broadcast/podcast host, note segment length, tone, and style.' if is_bc_pod else 'For a reporter, identify their specific beat and coverage style.'} "
            f"\n\nSTEP 1 — NAME GROUND TRUTH:\n"
            f"The reporter URL is: {brief_request.reporter_url}\n"
            f"Extract the name from the URL slug RIGHT NOW before doing anything else. "
            f"Example: cnbc.com/arjun-kharpal/ = Arjun Kharpal. wsj.com/authors/ben-cohen/ = Ben Cohen. "
            f"This URL-extracted name is your ground truth. "
            f"The final name in your output MUST match this unless a source explicitly contradicts it.\n\n"
            "STEP 2 — SCRAPE:\n"
            "Use scrape_reporter_page tool. When you get the result, immediately check: "
            "does the returned name start with the same first name as your URL-extracted name? "
            "If NO — discard the scrape name and use your URL-extracted name instead.\n\n"
            "STEP 3 — MANDATORY FALLBACK (run if ANY of these are true):\n"
            "- scrape raw_text is under 300 characters\n"
            "- scrape name is empty or does not match URL-extracted name\n"
            "- scrape bio is empty\n"
            "- scrape recent_articles has fewer than 3 items\n"
            "If any condition above is true, you MUST run BOTH:\n"
            "  web_search: '{url_extracted_name} journalist reporter bio recent articles'\n"
            "  glean_search: '{url_extracted_name} reporter'\n"
            "Use bio and coverage from these searches to fill the gaps.\n\n"
            "STEP 4 — HARD RULES:\n"
            "NEVER fabricate a reporter name, outlet, bio, or coverage items. "
            "NEVER output a name that does not match the URL slug. "
            "A brief with a real URL and empty bio is better than a brief with an invented reporter. "
            "Pass headshot_base64 and headshot_mime_type through in your output — they are required."
        ),
        backstory=(
            "You are the agency's best researcher. You have built reporter profiles for Financial Times, CNBC, "
            "Bloomberg, and every major outlet. Senior PR staff trust your profiles completely — "
            "they have never had to correct one. You always find the headshot. You always find the social links. "
            "You always find the recent coverage. Your profiles make clients feel like they already "
            "know the reporter before the meeting."
        ),
        tools=[scrape_reporter_page, glean_search, web_search],
        llm=create_gemini_llm(),
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )


def build_client_context_agent(brief_request: Any) -> Agent:
    rules            = brief_request.brief_type_rules
    needs_transcripts = "previous_transcripts" in rules["extra_sections"]

    return Agent(
        role="Client Memory Bank",
        goal=(
            f"Retrieve ALL internal knowledge about {brief_request.client_name} "
            f"and {brief_request.exec_name} from Glean. "
            "Run SEPARATE searches for each of these:\n"
            f"1. '{brief_request.client_name} media brief'\n"
            f"2. '{brief_request.exec_name} talking points'\n"
            f"3. '{brief_request.client_name} pitchbook'\n"
            f"4. '{brief_request.client_name} messaging FAQ'\n"
            f"5. '{brief_request.exec_name} commentary'\n"
            f"6. '{brief_request.client_name} about'\n"
            + (f"7. '{brief_request.exec_name} transcript'\n" if needs_transcripts else "") +
            "Extract talking points VERBATIM — the client's exact words, not a paraphrase. "
            "Label each cluster with topic and date. "
            "IMPORTANT: Each talking point bullet must be ONE concise sentence — not a paragraph. "
            "If source material is paragraph-style, break it into individual bullet sentences. "
            "Extract the standard 'About [Company]' boilerplate paragraph exactly as written."
        ),
        backstory=(
            "You are the agency's institutional memory. You have read every brief, every pitchbook, "
            "every piece of client commentary ever produced. "
            "When you retrieve talking points, you get the EXACT words — not a summary. "
            "Senior strategists rely on you to make sure no client ever repeats themselves "
            "when the answer already exists in the agency's files."
        ),
        tools=[glean_search, glean_read_document],
        llm=create_gemini_llm(),
        verbose=False,
        allow_delegation=False,
        max_iter=5,
    )


def build_news_agent(brief_request: Any) -> Agent:
    return Agent(
        role="News Desk Researcher",
        goal=(
            f"Find exactly 3 relevant news articles from the past 7 days about: {brief_request.topic}. "
            f"For {brief_request.exec_name} at {brief_request.client_name} ahead of their "
            f"{brief_request.brief_type}. "
            "Select articles with specific stats or data points from credible outlets. "
            "For each: headline, URL, source, date, and 3-bullet summary: "
            "bullet 1 = key stat, bullet 2 = main thesis, bullet 3 = relevance to interview. "
            "No wire service press releases. No fabricated articles."
        ),
        backstory=(
            "You find the exact articles that make a client walk into an interview with confidence. "
            "You always find articles with hard numbers. A great Relevant News section "
            "changes the whole tone of a client conversation."
        ),
        tools=[web_search],
        llm=create_gemini_llm(),
        verbose=False,
        allow_delegation=False,
        max_iter=3,
    )


def build_brief_assembler_agent(brief_request: Any, reporter_data: dict = {}) -> Agent:
    rules            = brief_request.brief_type_rules
    reporter_label   = rules["reporter_section_label"]
    coverage_label   = rules["coverage_label"]
    qa_has_answers   = rules["qa_has_answers"]
    needs_transcripts = "previous_transcripts" in rules["extra_sections"]
    needs_stats      = rules["stats_section"]
    needs_arrival    = "arrival_hit_time" in rules["extra_sections"]
    is_inperson      = brief_request.is_inperson
    is_staffed       = brief_request.is_staffed

    type_specific = ""
    if brief_request.brief_type == "Broadcast":
        type_specific = (
            "BROADCAST: Logistics must include Arrival Time and Hit Time. "
            "Opportunity must note: live or recorded, audio or video, segment length. "
            f"Tech/attire note: '{BROADCAST_TECH_REQUIREMENTS}'. "
            "Reporter label: 'About the Host'. Coverage label: 'Recent Clips'. "
            "Q&A MUST have full drafted answers. "
            "Include Previous Broadcast Q&As section with verbatim transcripts. "
            "Label talking points 'Talking Points (shared with producer)'."
        )
    elif brief_request.brief_type == "Podcast":
        type_specific = (
            "PODCAST: Opportunity must note: live or recorded, audio or video. "
            "Reporter label: 'About the Host'. Coverage label: 'Recent Episodes'. "
            "Q&A MUST have full drafted answers. "
            "Include Expected Topics section if producer shared topics. "
            "Include Previous Podcast Q&As section with verbatim transcripts."
        )
    elif brief_request.brief_type == "In-Person":
        type_specific = (
            "IN-PERSON: Location MUST include full street address. "
            + (f"Staffed by {brief_request.staffer_name} — include their phone number in Opportunity. "
               if is_staffed else
               "NOT staffed — include reporter phone and email. "
               "Add note: client must clarify on-record status at top of meeting.")
        )
    elif brief_request.brief_type == "Interview":
        type_specific = (
            "INTERVIEW: Deep reporter diligence. "
            "Questions ONLY in Q&A — NO drafted answers. "
            "Include Relevant Statistics section. 5-7 questions minimum."
        )
    elif brief_request.brief_type == "Intro":
        type_specific = (
            "INTRO: Lighter Q&A — 4-5 general questions, NO drafted answers. "
            "Emphasize talking points and key messaging over deep reporter diligence. "
            "Frame opportunity as relationship-building, not a story interview. "
            "Remind client to ask reporter what they are currently working on."
        )

    return Agent(
        role="Senior PR Strategist",
        goal=(
            f"Assemble a complete, production-ready {brief_request.brief_type} media brief for "
            f"{brief_request.exec_name} at {brief_request.client_name}.\n\n"
            f"Date/Time: {brief_request.interview_date} at {brief_request.interview_time}\n"
            f"Location: {brief_request.location_or_link or 'TBD'}\n"
            f"Topic: {brief_request.topic}\n"
            f"On Record: {brief_request.on_record}\n"
            f"Staffed: {brief_request.staffed}"
            + (f" by {brief_request.staffer_name}" if brief_request.staffer_name else "") + "\n\n"
            f"CRITICAL — REPORTER SECTION: Use ONLY these exact pre-scraped values. "
            f"Do NOT rewrite, research, or replace any of these fields:\n"
            f"  name: {reporter_data.get('name', 'unknown')}\n"
            f"  linkedin_url: {reporter_data.get('linkedin_url') or 'null'}\n"
            f"  twitter_url: {reporter_data.get('twitter_url') or 'null'}\n"
            f"  headshot_url: {reporter_data.get('headshot_url') or 'null'}\n"
            f"  headshot_base64: {'PRESENT' if reporter_data.get('headshot_base64') else 'null'}\n"
            f"  headshot_mime_type: {reporter_data.get('headshot_mime_type') or 'image/jpeg'}\n"
            f"  bio_paragraph_1: {reporter_data.get('bio', '')[:300] or 'null'}\n"
            f"  recent_coverage articles: {str([a.get('title','') for a in reporter_data.get('recent_articles', [])])[:400]}\n"
            f"Copy these into reporter_section exactly. Never substitute with other content.\n\n"
            f"{type_specific}\n\n"
            "HARD RULES before returning JSON:\n"
            "- Q&A for Intro: EXACTLY 4-5 questions maximum\n"
            "- Key Messaging about_company field: boilerplate paragraph ONLY — no mission, no FAQ\n"
            "- FAQ items belong in key_messaging.faq_items only\n"
            f"- reporter_section.name MUST match the URL slug from {brief_request.reporter_url}\n"
            "Return ONLY valid JSON. No preamble. No explanation. No markdown fences."
        ),
        backstory=(
            "You are a Senior PR Strategist. You have written hundreds of media briefs. "
            "You know exactly what every brief type needs. "
            "You know the Interview Tips & Tricks section is sacred — it never changes, never gets cut. "
            "You have reviewed real media brief examples and you produce "
            "output that matches that standard exactly. "
            "You never use placeholder text. Every brief you produce is client-ready from the first draft."
        ),
        tools=[glean_search, glean_read_document],
        llm=create_gemini_llm(),
        verbose=False,
        allow_delegation=False,
        max_iter=3,
    )


def build_qa_agent(brief_request: Any) -> Agent:
    rules            = brief_request.brief_type_rules
    qa_has_answers   = rules["qa_has_answers"]
    needs_transcripts = "previous_transcripts" in rules["extra_sections"]

    checklist = (
        "MEDIA BRIEF QA SCORECARD\n\n"
        "SECTION 1 — STRUCTURE (required for every brief type):\n"
        f"- Title: [Exec Name], [Client] | {brief_request.brief_type} Media Brief\n"
        "- Logistics: Date/Time, Location (hyperlinked if virtual, full address if in-person), Attendees\n"
        "- Opportunity: 2-3 paragraphs — type, on/off-record, topic, purpose, why it matters, staffing\n"
        "- Opportunity P1 opens with bold format descriptor e.g. **on-record, virtual**\n"
        "- Reporter section: name hyperlinked, social links, 2-paragraph bio, 4-5 coverage items M/DD format\n"
        "- All coverage items hyperlinked — no raw URLs\n"
        "- Talking points: verbatim client commentary labeled by topic and date\n"
        "- Talking points are tight standalone bullets — not paragraph blocks\n"
        "- Relevant News: exactly 3 articles, each with 2-3 bullet summary including a specific stat\n"
        "- Key Messaging: standard About [Company] boilerplate only — not expanded or rewritten\n"
        "- Interview Tips & Tricks present and completely unmodified including DOs/DON'Ts table\n"
        "- No placeholder text, [INSERT:] tags, or [TBD] anywhere\n"
        "- No fabricated quotes, stats, or facts\n\n"
        f"SECTION 2 — BRIEF TYPE REQUIREMENTS: {brief_request.brief_type.upper()}\n"
        + (
        "- Questions ONLY — no drafted answers\n"
        "- 4-5 questions, general and conversational\n"
        "- Opportunity framed as relationship-building not a story interview\n"
        "- Client reminded to ask reporter what they are currently working on\n"
        if brief_request.brief_type == "Intro" else ""
        ) + (
        "- Questions ONLY — no drafted answers\n"
        "- 5-7 questions minimum tied to reporter's actual recent coverage\n"
        "- Deep reporter diligence on tone, past work, angles\n"
        "- Relevant Statistics section present with current data\n"
        if brief_request.brief_type == "Interview" else ""
        ) + (
        "- Full street address in logistics\n"
        + ("- Staffer name and phone number in opportunity section\n"
           if brief_request.is_staffed else
           "- NOT STAFFED clearly stated in opportunity\n"
           "- Reporter phone and email included\n")
        if brief_request.brief_type == "In-Person" else ""
        ) + (
        "- Arrival Time AND Hit Time in logistics\n"
        "- Live/recorded, audio/video, and segment length noted\n"
        "- Tech/attire requirements included\n"
        "- Section label: About the Host\n"
        "- Coverage label: Recent Clips\n"
        "- Q&A has FULL drafted answers\n"
        "- Drafted answers prefixed with Drafted response:\n"
        if brief_request.brief_type == "Broadcast" else ""
        ) + (
        "- Section label: About the Host\n"
        "- Coverage label: Recent Episodes\n"
        "- Q&A has FULL drafted answers\n"
        "- Drafted answers prefixed with Drafted response:\n"
        "- Expected topics from producer included if available\n"
        if brief_request.brief_type == "Podcast" else ""
        ) +
        "\nSECTION 3 — QUALITY STANDARDS:\n"
        "- Opportunity explains WHY this matters — make the case not just describe\n"
        "- Q&A answers are 3-5 bullets max — concise and message-driven not essays\n"
        "- New drafted content marked [DRAFT - NEEDS CLIENT REVIEW]\n"
        "- Brief length 1500-3000 words excluding Previous Q&As\n"
        "\n"
        "OUTPUT: Your final response MUST start with QA_APPROVED or QA_FAILED — nothing before those words.\n"
        "If QA_FAILED: numbered list of specific fixes only. No reasoning. No preamble.\n"
    )

    return Agent(
        role="QA Assassin",
        goal=(
            f"Review the assembled {brief_request.brief_type} media brief.\n\n"
            f"STEP 1: Search Glean for real examples: 'media brief {brief_request.brief_type}'\n"
            f"STEP 2: Apply this checklist:\n{checklist}\n"
            "STEP 3: Return ONLY one of these two outputs:\n"
            "If ALL checks pass: return the single word QA_APPROVED\n"
            "If ANY check fails: return QA_FAILED followed by numbered specific fixes\n\n"
            "IMPORTANT: Your FINAL response must start with either QA_APPROVED or QA_FAILED. "
            "Do not include any other text before those words."
        ),
        backstory=(
            "You are the last line of defense before a media brief reaches a client. "
            "You have read every media brief ever produced at this agency. "
            "You are specific, blunt, and actionable. "
            "Your final answer always starts with QA_APPROVED or QA_FAILED — nothing else comes first."
        ),
        tools=[glean_search, glean_read_document],
        llm=create_gemini_llm(),
        verbose=False,
        allow_delegation=False,
        max_iter=3,
    )


if __name__ == "__main__":
    from config import BriefRequest

    test = BriefRequest(
        client_name="Acme Corp",
        exec_name="Jane Smith",
        reporter_url="https://www.cnbc.com/arjun-kharpal/",
        brief_type="Broadcast",
        interview_date="May 15, 2026",
        interview_time="2:00 PM ET",
        virtual_or_inperson="Virtual",
        topic="AI in enterprise technology",
        on_record="On Record",
        staffed="Yes",
        submitter_email="you@yourcompany.com",
        staffer_name="Account Manager",
    )

    print("Building agents...\n")
    a1 = build_reporter_agent(test)
    print(f"✅ Agent 1 — {a1.role}")
    a2 = build_client_context_agent(test)
    print(f"✅ Agent 2 — {a2.role}")
    a3 = build_news_agent(test)
    print(f"✅ Agent 3 — {a3.role}")
    a4 = build_brief_assembler_agent(test)
    print(f"✅ Agent 4 — {a4.role}")
    a5 = build_qa_agent(test)
    print(f"✅ Agent 5 — {a5.role}")
    print("\n✅ agents.py validation passed — all gemini-2.5-flash")

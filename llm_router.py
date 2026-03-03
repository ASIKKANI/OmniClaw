"""
llm_router.py — NVIDIA NIM API integration for OmniClaw.

Uses meta/llama-3.1-70b-instruct.
  - split_goals:     Breaks compound input into individual tasks.
  - get_next_action:  Picks next agent action.
  - verify_action:    Checks expected state.
"""

import json
import os
import re

from openai import OpenAI


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_NAME = "meta/llama-3.1-70b-instruct"
MAX_RETRIES = 3

# ==========================================================================
# THE BRAIN
# ==========================================================================
AGENT_SYSTEM_PROMPT = """You are OmniClaw, an expert Android UI automation agent for Samsung M52 (1080x2400).

IMPORTANT: You are a UI NAVIGATOR, not an app launcher. The correct app is ALREADY OPEN.
Your job is to interact with the CURRENT screen by tapping buttons, typing text, and navigating.

You receive: GOAL, ACTION HISTORY, CONTEXT (optional), and CURRENT UI elements.
UI elements include: id, type (input/button/icon/text/toggle/view), text, desc, hint, res_id, focused.

RETURN ONLY a raw JSON object (no markdown). ONE action per response.

ACTIONS:
  {"action": "tap", "target_id": <int>, "expected_state": "..."}
  {"action": "type", "text": "<text>", "expected_state": "..."}
  {"action": "back", "expected_state": "..."}
  {"action": "enter", "expected_state": "..."}
  {"action": "research", "query": "<search query>", "expected_state": "gathering info"}
  {"status": "DONE", "summary": "..."}

═══════════════════════════════════════════
CRITICAL RULES:
═══════════════════════════════════════════
1. NEVER use "launch", "call", or "open_url". These are FORBIDDEN.
   If you need a different app, return DONE and let the orchestrator handle it.
2. If an input field has focused=true, just "type" directly — do NOT tap it first.
3. NEVER repeat any action from HISTORY. Try DIFFERENT elements.
4. If stuck (2+ fails), return DONE with explanation. Do NOT loop.

SEARCH PATTERN (very common — follow this precisely):
  If the goal involves SEARCHING or FINDING something in an app:
  Step 1: Look for an input/text element with hint containing "Search" or "search"
          OR an element with res_id containing "search" (e.g. "search_bar", "search_plate_title")
          OR an icon with desc "Search"
  Step 2: TAP that search element to focus it.
  Step 3: TYPE the search query.
  Step 4: Use "enter" to submit the search.
  Step 5: Find and tap the correct result.
  If you cannot find a search bar, look for a magnifying glass icon (🔍) or any element with "Search" in text/desc/hint.

TYPING PATTERN:
  - If an element has focused=true, just TYPE directly.
  - If you need to type in a specific field, TAP it first (look for hint text to identify the right field).
  - Use "enter" after typing in search fields.

NAVIGATION:
  - "back" = go to previous screen, close popups/keyboards.
  - Prefer tapping buttons with descriptive text over generic ones.
  - Look at res_id to understand what an element does (e.g. "install_button", "search_bar").
  - If an element has hint text, that tells you what to type there."""


VERIFY_SYSTEM_PROMPT = """Verify if an Android action succeeded. Given expected state and current UI, return ONLY raw JSON:
{"verified": true, "observation": "<brief>"} or {"verified": false, "observation": "<brief>"}
Be lenient — roughly correct = true."""


# ==========================================================================
# DECISION INTELLIGENCE LAYER
# ==========================================================================
EVALUATE_SYSTEM_PROMPT = """You are a strategic evaluator for an Android automation agent.

Given the user's GOAL, the ACTION HISTORY so far, and the CURRENT UI state, you must evaluate:

1. Is the agent making progress toward the goal?
2. Is the current approach correct or is it going in the wrong direction?
3. What should the agent do differently if it's off-track?

RETURN ONLY a raw JSON object:
{
  "on_track": true/false,
  "confidence": 1-10,
  "assessment": "<1-2 sentence analysis of progress>",
  "suggestion": "<if off-track: specific alternative approach to achieve the goal>",
  "correction": "<if off-track: specific next action the agent should take instead>"
}

RULES:
- confidence 8-10: clearly making good progress toward the goal
- confidence 5-7: some progress but could be better
- confidence 1-4: off track, wrong app, wrong screen, or repeating useless actions
- If on_track is false, you MUST provide a concrete suggestion and correction
- Be specific in corrections: mention exact UI elements, packages, or steps
- Consider if the agent opened the right app, is on the right screen, and taking logical steps
- If the agent keeps failing on the same thing, suggest a completely different approach"""


SPLIT_SYSTEM_PROMPT = """You are a task splitter. Given a user's compound request, break it into individual independent tasks.

RULES:
1. Split at natural boundaries (and, then, also, after that, comma-separated tasks).
2. Keep each task self-contained with all needed context.
3. If it's already a single task, return just that one.
4. Maintain the original order — some tasks depend on prior ones.

RETURN ONLY a raw JSON array of strings. No explanation.

Examples:
  Input: "call bharani and then open youtube"
  Output: ["call bharani", "open youtube"]

  Input: "send 100rs to yeswanth on fampay"
  Output: ["send 100rs to yeswanth on fampay"]

  Input: "draft an email about the latest spacex launch and send it to mom, then call bharani"
  Output: ["draft an email about the latest spacex launch and send it to mom", "call bharani"]"""


# ---------------------------------------------------------------------------
# Client (lazy)
# ---------------------------------------------------------------------------

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.environ.get("NVIDIA_API_KEY"),
        )
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_json(text: str):
    return json.loads(_strip_markdown_fences(text))


def _format_ui_for_llm(ui_elements: list) -> str:
    compact = []
    for e in ui_elements:
        entry = {"id": e["id"], "type": e["type"]}
        if e.get("text"):
            entry["text"] = e["text"]
        if e.get("desc"):
            entry["desc"] = e["desc"]
        if e.get("hint"):
            entry["hint"] = e["hint"]
        if e.get("res_id"):
            entry["res_id"] = e["res_id"]
        if e.get("focused"):
            entry["focused"] = True
        entry["cx"] = e["cx"]
        entry["cy"] = e["cy"]
        compact.append(entry)
    return json.dumps(compact)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

VALID_ACTIONS = {"tap", "type", "back", "enter", "research"}


def split_goals(user_input: str) -> list[str]:
    """Break compound user input into individual task strings."""
    try:
        print(f"  📋 Splitting goals...")
        response = _get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        raw = response.choices[0].message.content
        result = _parse_json(raw)
        if isinstance(result, list) and all(isinstance(x, str) for x in result):
            return result
    except Exception as e:
        print(f"  ⚠️  Split failed: {e}")

    # Fallback: return as single task
    return [user_input]


def get_next_action(goal: str, ui_elements: list, history: list[str] = None,
                    context: str = "") -> dict:
    """Decide the single most efficient next action."""
    ui_json = _format_ui_for_llm(ui_elements)

    history_str = ""
    if history:
        history_str = "\nHISTORY (do NOT repeat):\n"
        for i, h in enumerate(history, 1):
            history_str += f"  {i}. {h}\n"

    context_str = ""
    if context:
        context_str = f"\nCONTEXT (from web research):\n{context}\n"

    user_prompt = (
        f"GOAL: {goal}\n"
        f"{history_str}"
        f"{context_str}\n"
        f"UI:\n{ui_json}\n\n"
        f"Next action?"
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  🧠 Thinking (attempt {attempt}/{MAX_RETRIES})...")

            response = _get_client().chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=512,
            )

            raw_text = response.choices[0].message.content
            result = _parse_json(raw_text)

            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object.")

            if result.get("status") == "DONE":
                return result

            action = result.get("action")
            if action not in VALID_ACTIONS:
                raise ValueError(f"Unknown action: {action}")

            # Validate tap target_id
            if action == "tap":
                target_id = result.get("target_id")
                if target_id is None:
                    raise ValueError("Tap missing 'target_id'.")
                target_id = int(target_id)
                valid_ids = [e["id"] for e in ui_elements]
                if target_id not in valid_ids:
                    raise ValueError(f"target_id {target_id} invalid. Valid: {valid_ids}")
                result["target_id"] = target_id

            # Validate call has actual digits
            if action == "call":
                phone = result.get("phone", "")
                digits = re.sub(r"[^\d+]", "", phone)
                if len(digits) < 5:
                    raise ValueError(
                        f"call phone '{phone}' is not a valid number. "
                        f"Extract the ACTUAL phone number digits from the UI elements."
                    )
                result["phone"] = digits

            return result

        except (json.JSONDecodeError, ValueError) as e:
            print(f"  ⚠️  Invalid response (attempt {attempt}): {e}")
            user_prompt = (
                f"ERROR: {e}\n\n"
                f"GOAL: {goal}\n{history_str}{context_str}\n"
                f"UI:\n{ui_json}\n\n"
                f"Fix your response. Output ONLY valid raw JSON."
            )

    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts.")


def verify_action(expected_state: str, ui_elements: list) -> dict:
    """Lightweight verification."""
    ui_json = _format_ui_for_llm(ui_elements)
    try:
        response = _get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                {"role": "user", "content": f"EXPECTED: {expected_state}\nUI:\n{ui_json}\nVerified?"},
            ],
            temperature=0.1,
            max_tokens=128,
        )
        result = _parse_json(response.choices[0].message.content)
        if isinstance(result, dict) and "verified" in result:
            return result
    except Exception as e:
        print(f"  ⚠️  Verify error: {e}")
    return {"verified": True, "observation": "Proceeding."}


def evaluate_progress(goal: str, history: list[str], ui_elements: list,
                      context: str = "") -> dict:
    """Evaluate if the agent is making progress toward the goal.

    Returns dict with: on_track, confidence, assessment, suggestion, correction.
    """
    ui_json = _format_ui_for_llm(ui_elements)

    history_str = ""
    if history:
        history_str = "ACTION HISTORY:\n"
        for i, h in enumerate(history, 1):
            history_str += f"  {i}. {h}\n"

    context_str = ""
    if context:
        context_str = f"\nCONTEXT: {context}\n"

    user_prompt = (
        f"GOAL: {goal}\n\n"
        f"{history_str}"
        f"{context_str}\n"
        f"CURRENT UI:\n{ui_json}\n\n"
        f"Is the agent on track? Evaluate progress."
    )

    try:
        print("  🔎 Evaluating progress...")
        response = _get_client().chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": EVALUATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=512,
        )
        result = _parse_json(response.choices[0].message.content)
        if isinstance(result, dict) and "on_track" in result:
            return result
    except Exception as e:
        print(f"  ⚠️  Evaluate error: {e}")

    return {"on_track": True, "confidence": 7, "assessment": "Unable to evaluate.", "suggestion": "", "correction": ""}

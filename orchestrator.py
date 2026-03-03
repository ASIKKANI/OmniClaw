"""
orchestrator.py — The Llama Brain of OmniClaw.

Implements a ReAct (Reason + Act) loop:
  1. Send user goal to Llama.
  2. Llama responds with a JSON action (thought + tool + arguments).
  3. Dispatch the tool, collect result.
  4. Feed result back to Llama.
  5. Repeat until Llama outputs DONE.

Supports both streaming (for web UI) and blocking (for CLI) modes.
"""

import json
import os
import re
import traceback

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOL_REGISTRY, dispatch_tool


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 15

load_dotenv()


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

def _build_system_prompt() -> str:
    """Build the system prompt dynamically from the tool registry."""
    tool_descriptions = []
    for name, info in TOOL_REGISTRY.items():
        tool_descriptions.append(f"  - {name}: {info['description']}")
    tools_block = "\n".join(tool_descriptions)

    return f"""You are OmniClaw, an autonomous General Intelligence agent controlling an Android phone.
You solve tasks logically, step-by-step. You call tools one at a time and wait for each result.

AVAILABLE TOOLS:
{tools_block}

OUTPUT FORMAT — For EACH step, output ONLY a single raw JSON object (no markdown):
{{
  "thought": "<step-by-step reasoning about what to do next and WHY>",
  "tool": "<tool_name>",
  "arguments": {{"<arg1>": "<val1>"}}
}}

When fully complete, output:
{{
  "thought": "<final reasoning>",
  "tool": "DONE",
  "message": "<clear summary of what was accomplished>"
}}

═══════════════════════════════════════════════════════════
CRITICAL LOGIC RULES (VIOLATING THESE = FAILURE):
═══════════════════════════════════════════════════════════

RULE 1 — NEVER GUESS PACKAGE NAMES:
  If you need to open an app and there is no specific intent for it,
  you MUST use find_and_launch_app("app_name").
  NEVER hardcode or guess package names like "com.samsung.android.dialer".
  The tool searches the phone's registry and finds the REAL package.
  Example: find_and_launch_app("clock") → finds com.sec.android.app.clockpackage → launches it.

RULE 2 — INTENT FIRST (instant, most accurate):
  For email, WhatsApp, browser, calls, SMS, or alarms:
  → You MUST use android_intent_dispatcher. It takes 0.5s vs 40s of UI tapping.
  → After the intent fills fields, if you need to tap "Send", THEN use execute_android_ui_task.
  → For alarms, the intent sets the alarm silently in the background (SKIP_UI=true).

RULE 3 — ANTI-LOOP AWARENESS:
  If execute_android_ui_task tells you "ACTION FAILED: Screen did not change":
  → DO NOT repeat the same action.
  → You MUST pivot: use press_hardware_key("BACK") to close keyboards/pop-ups,
    or try a completely different UI element.
  → If stuck after 3 attempts: use press_hardware_key("HOME") and try an alternative approach.

RULE 4 — USE HARDWARE KEYS TO ESCAPE DEAD ENDS:
  → press_hardware_key("BACK") = close dialogs, keyboards, go to previous screen
  → press_hardware_key("HOME") = escape to home screen when completely stuck
  → press_hardware_key("ENTER") = submit text fields
  Use these BEFORE declaring failure.

RULE 5 — NO GUESSING / NO HALLUCINATION:
  If the task requires web info (news, weather, prices), you MUST call search_web FIRST.
  If the task requires a local file, you MUST call search_local_file FIRST.
  You CANNOT make up data. If the tool returns nothing, say so.

RULE 6 — ATTACHMENTS WORKFLOW:
  Step 1: search_local_file to find the file on the PC.
  Step 2: adb_push_file to push it to /sdcard/Download/ on the phone.
  Step 3: android_intent_dispatcher with attachment_phone_path.

RULE 7 — APP NOT INSTALLED → ADAPT:
  Use adb_check_app to verify before trying app-specific tasks.
  If NOT installed:
    → Common tasks (weather, social, email) → android_intent_dispatcher(app="browser")
    → Custom apps → search_local_file for .apk → adb_install_app → proceed.

RULE 8 — VERIFY SUCCESS BEFORE DONE:
  Before declaring "DONE", verify that the final state matches the user's goal.
  If unsure, use execute_android_ui_task to read the current screen.

RULE 9 — UI IS THE LAST RESORT:
  Only use execute_android_ui_task when:
    - Tapping a button after an intent fills fields
    - Interacting with apps that have no intent support
    - Reading on-screen content to verify results
  Always keep max_steps low (4-6).

═══════════════════════════════════════════════════════════
FEW-SHOT EXAMPLES:
═══════════════════════════════════════════════════════════

EXAMPLE 1 — Email with Web Research:
  User: "Email alex@gmail.com about the latest SpaceX launch."
  Step 1: {{"thought": "I need SpaceX info. RULE 5: search_web first.", "tool": "search_web", "arguments": {{"query": "latest SpaceX launch news 2026"}}}}
  Result: "SpaceX launched Starship Flight 10 on Feb 28..."
  Step 2: {{"thought": "Got real data. RULE 2: use intent for email.", "tool": "android_intent_dispatcher", "arguments": {{"app": "gmail", "target": "alex@gmail.com", "subject": "SpaceX Launch Update", "body": "Hey! SpaceX launched Starship Flight 10 on Feb 28..."}}}}
  Step 3: {{"thought": "Gmail open with fields filled. Tap Send.", "tool": "execute_android_ui_task", "arguments": {{"task_description": "Tap the Send button in Gmail compose screen.", "max_steps": 4}}}}
  Step 4: {{"tool": "DONE", "message": "Email sent to alex@gmail.com with SpaceX info."}}

EXAMPLE 2 — Set an Alarm (Pure Intent):
  User: "Set an alarm for 8:00 AM."
  Step 1: {{"thought": "RULE 2: alarm is a pure intent. No UI needed.", "tool": "android_intent_dispatcher", "arguments": {{"app": "alarm", "hour": "8", "minutes": "0", "message": "Morning Alarm"}}}}
  Step 2: {{"tool": "DONE", "message": "Alarm set for 8:00 AM."}}

EXAMPLE 3 — Open an Unknown App (Dynamic Search):
  User: "Open the calculator."
  Step 1: {{"thought": "RULE 1: I MUST NOT guess the package. Use find_and_launch_app.", "tool": "find_and_launch_app", "arguments": {{"app_name": "calculator"}}}}
  Result: "Launched: com.sec.android.app.popupcalculator"
  Step 2: {{"tool": "DONE", "message": "Calculator is now open."}}

EXAMPLE 4 — Recovering from a Stuck Screen:
  User: "Type 500 times 2 in the calculator."
  Step 1: {{"thought": "Open calculator first.", "tool": "find_and_launch_app", "arguments": {{"app_name": "calculator"}}}}
  Step 2: {{"thought": "Type the calculation.", "tool": "execute_android_ui_task", "arguments": {{"task_description": "In the calculator app, tap 5, 0, 0, then the multiply button, then 2, then equals.", "max_steps": 8}}}}
  Result: "ACTION FAILED: Screen did not change."
  Step 3: {{"thought": "RULE 3: Screen stuck. Press BACK to reset, then retry.", "tool": "press_hardware_key", "arguments": {{"key": "BACK"}}}}
  Step 4: {{"thought": "Try the calculator task again.", "tool": "execute_android_ui_task", "arguments": {{"task_description": "In the calculator, tap buttons: 5, 0, 0, ×, 2, =", "max_steps": 8}}}}
  Result: "Task Complete: Result is 1000."
  Step 5: {{"tool": "DONE", "message": "500 × 2 = 1000"}}

EXAMPLE 5 — App Not Installed (Web Fallback):
  User: "Check weather on Apple Maps."
  Step 1: {{"thought": "Apple Maps doesn't exist on Android. I'll use browser instead.", "tool": "android_intent_dispatcher", "arguments": {{"app": "browser", "target": "https://www.google.com/search?q=current+weather"}}}}
  Step 2: {{"tool": "DONE", "message": "Apple Maps is not available on Android. Opened Google weather in Chrome instead."}}
═══════════════════════════════════════════════════════════"""


# ---------------------------------------------------------------------------
# LLM Client (lazy)
# ---------------------------------------------------------------------------

_client = None


def _get_client() -> OpenAI:
    """Get or create the OpenAI-compatible client for Llama."""
    global _client
    if _client is None:
        base_url = os.getenv("LLAMA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        api_key = os.getenv("LLAMA_API_KEY") or os.getenv("NVIDIA_API_KEY")

        if not api_key:
            raise RuntimeError(
                "No API key found. Set LLAMA_API_KEY or NVIDIA_API_KEY in .env"
            )

        _client = OpenAI(base_url=base_url, api_key=api_key)
    return _client


def _get_model() -> str:
    """Get the model name from env or default."""
    return os.getenv("LLAMA_MODEL", "meta/llama-3.1-70b-instruct")


# ---------------------------------------------------------------------------
# JSON Parsing
# ---------------------------------------------------------------------------

def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers if present."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _parse_llm_response(raw: str) -> dict:
    """Parse the LLM's raw text response into a JSON dict."""
    cleaned = _strip_markdown_fences(raw)

    # Try direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {cleaned[:200]}")


# ---------------------------------------------------------------------------
# FAST-PATH ROUTER — bypasses LLM entirely for known intent tasks
# ---------------------------------------------------------------------------

def _try_fast_path(goal: str):
    """Check if the goal matches a known intent pattern and execute directly.

    Returns a list of event dicts if fast-path was taken, or None to fall
    through to the LLM loop.

    This is the NUCLEAR fix: for alarm/email/call/sms/browser tasks,
    the LLM never gets a chance to hallucinate package names.
    """
    goal_lower = goal.lower().strip()

    # ─── ALARM ───
    alarm_keywords = ["alarm", "wake me", "remind me at"]
    if any(kw in goal_lower for kw in alarm_keywords) and "timer" not in goal_lower:
        time_match = re.search(r"(\d{1,2})\s*[:\.]?\s*(\d{2})?\s*(am|pm|a\.m|p\.m)?", goal, re.IGNORECASE)
        h, m = 8, 0
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3)
            if ampm and ampm.lower().startswith("p") and h < 12:
                h += 12
            elif ampm and ampm.lower().startswith("a") and h == 12:
                h = 0

        from tools import android_intent_dispatcher
        result = android_intent_dispatcher(app="alarm", hour=str(h), minutes=str(m), message="OmniClaw Alarm")

        return [
            {"type": "start", "goal": goal},
            {"type": "thought", "iteration": 1,
             "thought": f"[FAST-PATH] Alarm → {h:02d}:{m:02d}",
             "tool": "android_intent_dispatcher",
             "arguments": {"app": "alarm", "hour": str(h), "minutes": str(m)}},
            {"type": "tool_result", "tool": "android_intent_dispatcher", "result": result},
            {"type": "done", "thought": "Alarm set via fast-path.",
             "message": f"Alarm set for {h:02d}:{m:02d}."},
        ]

    # ─── TIMER ───
    if "timer" in goal_lower:
        # Extract duration: "5 minutes", "30 seconds", "10 min", "1 hour"
        dur_mins = 0
        dur_secs = 0
        hour_match = re.search(r"(\d+)\s*(?:hour|hr|h)", goal_lower)
        min_match = re.search(r"(\d+)\s*(?:minute|min|m(?!\w))", goal_lower)
        sec_match = re.search(r"(\d+)\s*(?:second|sec|s(?!\w))", goal_lower)
        if hour_match:
            dur_mins += int(hour_match.group(1)) * 60
        if min_match:
            dur_mins += int(min_match.group(1))
        if sec_match:
            dur_secs += int(sec_match.group(1))
        if dur_mins == 0 and dur_secs == 0:
            # Try bare number (assume minutes)
            bare = re.search(r"(\d+)", goal)
            if bare:
                dur_mins = int(bare.group(1))

        from tools import android_intent_dispatcher
        result = android_intent_dispatcher(
            app="timer", hour=str(dur_mins), minutes=str(dur_secs), message="OmniClaw Timer"
        )
        total = dur_mins * 60 + dur_secs
        return [
            {"type": "start", "goal": goal},
            {"type": "thought", "iteration": 1,
             "thought": f"[FAST-PATH] Timer → {total}s",
             "tool": "android_intent_dispatcher",
             "arguments": {"app": "timer", "hour": str(dur_mins), "minutes": str(dur_secs)}},
            {"type": "tool_result", "tool": "android_intent_dispatcher", "result": result},
            {"type": "done", "thought": "Timer set.",
             "message": f"Timer set for {dur_mins}m {dur_secs}s." if dur_secs else f"Timer set for {dur_mins} minutes."},
        ]

    # ─── CALENDAR / SCHEDULE / EVENT / REMINDER ───
    sched_keywords = ["calendar", "schedule", "event", "meeting", "appointment"]
    if any(kw in goal_lower for kw in sched_keywords):
        # Extract time
        time_match = re.search(r"(\d{1,2})\s*[:\.]?\s*(\d{2})?\s*(am|pm|a\.m|p\.m)?", goal, re.IGNORECASE)
        h, m = 0, 0
        if time_match:
            h = int(time_match.group(1))
            m = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3)
            if ampm and ampm.lower().startswith("p") and h < 12:
                h += 12
            elif ampm and ampm.lower().startswith("a") and h == 12:
                h = 0

        # Extract event title: everything before "at/for/on" time phrase
        title = re.sub(
            r"(?:schedule|create|add|set|make)\s*(?:a|an)?\s*(?:calendar\s*)?(?:event|meeting|appointment)?\s*",
            "", goal, flags=re.IGNORECASE
        ).strip()
        title = re.sub(r"\s*(?:at|for|on)\s+\d.*$", "", title, flags=re.IGNORECASE).strip()
        if not title or len(title) < 2:
            title = goal.strip()

        from tools import android_intent_dispatcher
        result = android_intent_dispatcher(
            app="calendar", target=title, hour=str(h) if h else "", minutes=str(m) if m else ""
        )
        time_str = f" at {h:02d}:{m:02d}" if h or m else ""
        return [
            {"type": "start", "goal": goal},
            {"type": "thought", "iteration": 1,
             "thought": f"[FAST-PATH] Calendar event: '{title}'{time_str}",
             "tool": "android_intent_dispatcher",
             "arguments": {"app": "calendar", "target": title}},
            {"type": "tool_result", "tool": "android_intent_dispatcher", "result": result},
            {"type": "done", "thought": "Calendar event created.",
             "message": f"Created calendar event: '{title}'{time_str}."},
        ]

    # ─── OPEN BROWSER / URL ───
    url_match = re.search(r"(https?://\S+)", goal)
    if url_match or any(kw in goal_lower for kw in ["open chrome", "open browser", "open the browser"]):
        url = url_match.group(1) if url_match else "https://www.google.com"
        from tools import android_intent_dispatcher
        result = android_intent_dispatcher(app="browser", target=url)
        return [
            {"type": "start", "goal": goal},
            {"type": "thought", "iteration": 1,
             "thought": f"[FAST-PATH] Browser → opening {url[:50]}",
             "tool": "android_intent_dispatcher",
             "arguments": {"app": "browser", "target": url}},
            {"type": "tool_result", "tool": "android_intent_dispatcher", "result": result},
            {"type": "done", "thought": "Browser opened.",
             "message": f"Opened {url[:80]} in the browser."},
        ]

    # ─── TEXT / WHATSAPP / SMS ───
    text_keywords = ["text ", "message ", "msg ", "whatsapp ", "send a message",
                     "send message", "tell ", "inform "]
    if any(kw in goal_lower for kw in text_keywords):
        phone_match = re.search(r"[\+]?\d[\d\s\-]{6,}", goal)

        body = ""
        body_match = re.search(r"(?:that|saying|message|msg)\s+(.+?)$", goal, re.IGNORECASE)
        if body_match:
            body = body_match.group(1).strip()

        from tools import android_intent_dispatcher, find_and_launch_app

        if phone_match:
            phone = re.sub(r"[^\d+]", "", phone_match.group())
            if "sms" in goal_lower or "text message" in goal_lower:
                result = android_intent_dispatcher(app="sms", target=phone, body=body)
                app_used = "SMS"
            else:
                result = android_intent_dispatcher(app="whatsapp", target=phone, body=body)
                app_used = "WhatsApp"
            return [
                {"type": "start", "goal": goal},
                {"type": "thought", "iteration": 1,
                 "thought": f"[FAST-PATH] {app_used} message to {phone}",
                 "tool": "android_intent_dispatcher",
                 "arguments": {"app": app_used.lower(), "target": phone, "body": body}},
                {"type": "tool_result", "tool": "android_intent_dispatcher", "result": result},
                {"type": "done", "thought": f"{app_used} opened with message.",
                 "message": f"Opened {app_used} to {phone}" + (f' with message: "{body[:50]}"' if body else "")},
            ]
        else:
            # No phone number — open WhatsApp first, then let LLM find the contact
            find_and_launch_app("whatsapp")
            # Return None so LLM loop runs, but WhatsApp is already open
            # LLM will see WhatsApp UI and can search for the contact by name
            return None

    # ─── MAKE A CALL ───
    if any(kw in goal_lower for kw in ["call ", "dial ", "ring "]):
        phone_match = re.search(r"[\+]?\d[\d\s\-]{6,}", goal)
        if phone_match:
            phone = re.sub(r"[^\d+]", "", phone_match.group())
            from tools import android_intent_dispatcher
            result = android_intent_dispatcher(app="call", target=phone)
            return [
                {"type": "start", "goal": goal},
                {"type": "thought", "iteration": 1,
                 "thought": f"[FAST-PATH] Call → dialing {phone}",
                 "tool": "android_intent_dispatcher",
                 "arguments": {"app": "call", "target": phone}},
                {"type": "tool_result", "tool": "android_intent_dispatcher", "result": result},
                {"type": "done", "thought": "Call initiated.",
                 "message": f"Calling {phone}."},
            ]

    # No fast-path match — fall through to LLM
    return None


# ---------------------------------------------------------------------------
# Intent Interceptor — CODE-LEVEL guardrail against LLM hallucination
# ---------------------------------------------------------------------------

# Keyword → auto-route map: if the GOAL matches keywords, force the right tool
_INTENT_KEYWORDS = {
    "alarm": {"app": "alarm"},
    "timer": {"app": "alarm"},
    "reminder": {"app": "alarm"},
    "wake me": {"app": "alarm"},
}

_INTENT_FULL_PHRASES = [
    # (phrase_keywords, intent_app, needs_field)
    (["send", "email"], "gmail", "target"),
    (["draft", "email"], "gmail", "target"),
    (["compose", "email"], "gmail", "target"),
    (["send", "whatsapp"], "whatsapp", "target"),
    (["message", "whatsapp"], "whatsapp", "target"),
    (["open", "browser"], "browser", "target"),
    (["open", "chrome"], "browser", "target"),
    (["call"], "dialer", "target"),
    (["send", "sms"], "sms", "target"),
    (["text message"], "sms", "target"),
]

# Package names that should NEVER be launched directly (they have intents)
_BLOCKED_PACKAGES = {
    "dialer", "phone", "incallui", "telecom",
    "clock", "alarm", "deskclock",
    "chrome", "browser",
    "gm", "gmail",
    "messaging", "mms",
}


def _intercept_and_correct(goal: str, tool_name: str, arguments: dict) -> tuple:
    """Intercept the LLM's tool choice and correct it if it's wrong.

    Returns (corrected_tool_name, corrected_arguments, correction_message or None).
    """
    goal_lower = goal.lower()

    # ─── GUARD 1: If LLM tries to LAUNCH an app that has a dedicated intent ───
    if tool_name == "execute_android_ui_task":
        task_desc = arguments.get("task_description", "").lower()

        for keyword, intent_info in _INTENT_KEYWORDS.items():
            if keyword in goal_lower or keyword in task_desc:
                app = intent_info["app"]
                new_args = {"app": app}
                if app == "alarm":
                    time_match = re.search(r"(\d{1,2})\s*[:\.]?\s*(\d{2})?\s*(am|pm|AM|PM)?", goal)
                    if time_match:
                        h = int(time_match.group(1))
                        m = int(time_match.group(2)) if time_match.group(2) else 0
                        ampm = time_match.group(3)
                        if ampm and ampm.lower() == "pm" and h < 12:
                            h += 12
                        elif ampm and ampm.lower() == "am" and h == 12:
                            h = 0
                        new_args["hour"] = str(h)
                        new_args["minutes"] = str(m)
                    new_args["message"] = "OmniClaw Alarm"

                correction = (
                    f"INTERCEPTED: Redirected to android_intent_dispatcher(app='{app}')."
                )
                print(f"  🛡️  {correction}")
                return "android_intent_dispatcher", new_args, correction

    # ─── GUARD 2: find_and_launch for intent-able apps ───
    if tool_name == "find_and_launch_app":
        app_name = arguments.get("app_name", "").lower()
        for keyword, intent_info in _INTENT_KEYWORDS.items():
            if keyword in app_name or keyword in goal_lower:
                app = intent_info["app"]
                new_args = {"app": app}
                if app == "alarm":
                    time_match = re.search(r"(\d{1,2})\s*[:\.]?\s*(\d{2})?\s*(am|pm|AM|PM)?", goal)
                    if time_match:
                        h = int(time_match.group(1))
                        m = int(time_match.group(2)) if time_match.group(2) else 0
                        ampm = time_match.group(3)
                        if ampm and ampm.lower() == "pm" and h < 12:
                            h += 12
                        elif ampm and ampm.lower() == "am" and h == 12:
                            h = 0
                        new_args["hour"] = str(h)
                        new_args["minutes"] = str(m)
                    new_args["message"] = "OmniClaw Alarm"

                correction = (
                    f"INTERCEPTED: Redirected to android_intent_dispatcher(app='{app}')."
                )
                print(f"  🛡️  {correction}")
                return "android_intent_dispatcher", new_args, correction

    # ─── GUARD 3: Block hallucinated package names ───
    if tool_name == "execute_android_ui_task":
        task_desc = arguments.get("task_description", "").lower()
        for blocked in _BLOCKED_PACKAGES:
            if "com." in task_desc and blocked in task_desc:
                correction = f"BLOCKED: UI task referenced system app '{blocked}'."
                print(f"  🛡️  {correction}")
                return "__BLOCKED__", {}, correction

    return tool_name, arguments, None


# ---------------------------------------------------------------------------
# Public API: Streaming (for web UI / SSE)
# ---------------------------------------------------------------------------

def run_stream(goal: str, should_stop=None):
    """Generator yielding event dicts for a single orchestrator run."""

    # ─── FAST-PATH: bypass LLM for known intent tasks ───
    fast_events = _try_fast_path(goal)
    if fast_events is not None:
        print(f"  ⚡ FAST-PATH triggered for: \"{goal}\"")
        for event in fast_events:
            yield event
        return

    # ─── NORMAL LLM PATH ───
    yield {"type": "start", "goal": goal}

    system_prompt = _build_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"GOAL: {goal}"},
    ]

    for iteration in range(1, MAX_ITERATIONS + 1):
        if should_stop and should_stop():
            yield {"type": "stopped", "message": "Stopped by user."}
            return

        yield {"type": "thinking", "iteration": iteration}

        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=_get_model(),
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )
            raw = response.choices[0].message.content
        except Exception as e:
            yield {"type": "error", "message": f"LLM request failed: {e}"}
            return

        try:
            parsed = _parse_llm_response(raw)
        except ValueError as e:
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": (
                    f"ERROR: {e}\n\n"
                    "Output ONLY a valid raw JSON object. No markdown, no explanation."
                ),
            })
            continue

        thought = parsed.get("thought", "")
        tool_name = parsed.get("tool", "")
        arguments = parsed.get("arguments", {})

        if tool_name == "DONE":
            final_msg = parsed.get("message", "Goal completed.")
            yield {"type": "done", "thought": thought, "message": final_msg}
            return

        # ----- INTENT INTERCEPTOR (code-level guardrail) -----
        corrected_tool, corrected_args, correction_msg = _intercept_and_correct(
            goal, tool_name, arguments
        )

        if corrected_tool == "__BLOCKED__":
            yield {
                "type": "thought", "iteration": iteration,
                "thought": thought, "tool": tool_name, "arguments": arguments,
            }
            block_result = (
                f"BLOCKED: {correction_msg} "
                "You MUST use android_intent_dispatcher or find_and_launch_app."
            )
            yield {"type": "tool_result", "tool": tool_name, "result": block_result}
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"TOOL RESULT [{tool_name}]:\n{block_result}",
            })
            continue

        if correction_msg:
            tool_name = corrected_tool
            arguments = corrected_args
            thought = f"[INTERCEPTED] {correction_msg} | Original: {thought}"

        yield {
            "type": "thought", "iteration": iteration,
            "thought": thought, "tool": tool_name, "arguments": arguments,
        }

        if should_stop and should_stop():
            yield {"type": "stopped", "message": "Stopped by user."}
            return

        try:
            tool_result = dispatch_tool(tool_name, arguments)
        except Exception as e:
            tool_result = f"Error executing {tool_name}: {e}"

        yield {
            "type": "tool_result", "tool": tool_name,
            "result": tool_result[:500],
        }

        corrected_raw = json.dumps({
            "thought": thought, "tool": tool_name, "arguments": arguments,
        })
        messages.append({"role": "assistant", "content": corrected_raw})
        messages.append({
            "role": "user",
            "content": f"TOOL RESULT [{tool_name}]:\n{tool_result}",
        })

    yield {"type": "error", "message": f"Max iterations ({MAX_ITERATIONS}) reached."}


# ---------------------------------------------------------------------------
# Public API: Blocking (for CLI)
# ---------------------------------------------------------------------------

def run(goal: str) -> str:
    """Run the orchestrator for a goal, print progress, return final message."""
    for event in run_stream(goal):
        _print_event(event)

        if event["type"] == "done":
            return event["message"]
        elif event["type"] in ("error", "stopped"):
            return event["message"]

    return "Orchestrator finished without explicit completion."


def _print_event(event: dict):
    """Pretty-print an orchestrator event to the terminal."""
    t = event.get("type")

    if t == "start":
        print(f'\n  🎯 Goal: "{event["goal"]}"')
    elif t == "thinking":
        print(f"\n  🧠 Thinking... (step {event['iteration']})")
    elif t == "thought":
        print(f'  💭 Thought: {event["thought"]}')
        args_str = json.dumps(event["arguments"]) if event["arguments"] else ""
        print(f'  🔧 Tool: {event["tool"]}({args_str})')
    elif t == "tool_result":
        result_preview = event["result"][:200]
        print(f"  📤 Result: {result_preview}")
    elif t == "done":
        print(f'\n  ✅ DONE: {event["message"]}')
    elif t == "error":
        print(f'\n  ❌ ERROR: {event["message"]}')
    elif t == "stopped":
        print(f'\n  ⏹️  STOPPED: {event["message"]}')

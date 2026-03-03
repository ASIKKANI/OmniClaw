"""
tools.py — The Toolbox for OmniClaw Orchestrator (v6 — General Intelligence).

Defines strict Python functions the LLM can call via the ReAct loop.
Each tool takes string arguments and returns a string result.

Tools:
  - search_local_file:         Find a file on the local PC.
  - adb_push_file:             Push a local file to Android device.
  - adb_check_app:             Check if an Android app is installed.
  - adb_install_app:           Install an APK on Android device.
  - find_and_launch_app:       Dynamically search + launch any app by common name.
  - press_hardware_key:        Press BACK / HOME / ENTER hardware keys.
  - android_intent_dispatcher: Fire Android intents (Gmail, WhatsApp, browser, alarm…).
  - execute_android_ui_task:   UI automation (last resort, with state-hash anti-loop).
  - search_web:                Search the web for information.
"""

import hashlib
import os
import re
import shlex
import subprocess
import time
from urllib.parse import quote

import xml.etree.ElementTree as ET

import adb_utils
import llm_router
import web_utils


# ---------------------------------------------------------------------------
# ADB path (shared with adb_utils)
# ---------------------------------------------------------------------------

ADB_PATH = adb_utils.ADB_PATH


# ---------------------------------------------------------------------------
# Tool: search_local_file
# ---------------------------------------------------------------------------

def search_local_file(filename: str) -> str:
    """Search common local directories for a file matching the given name.

    Args:
        filename: The file name or partial name to search for (e.g. "pitch_deck").

    Returns:
        The absolute path(s) found, or an error message.
    """
    if not filename or not filename.strip():
        return "Error: filename cannot be empty."

    filename = filename.strip()
    search_roots = [
        os.path.expanduser("~\\Desktop"),
        os.path.expanduser("~\\Documents"),
        os.path.expanduser("~\\Downloads"),
        os.path.expanduser("~"),
    ]

    search_lower = filename.lower()

    found = []
    seen_paths = set()

    for root_dir in search_roots:
        if not os.path.isdir(root_dir):
            continue
        try:
            for dirpath, dirnames, filenames_list in os.walk(root_dir):
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith(".") and d not in (
                        "node_modules", "__pycache__", ".git", "AppData",
                        "venv", ".venv", "env",
                    )
                ]

                for fname in filenames_list:
                    if search_lower in fname.lower():
                        full_path = os.path.join(dirpath, fname)
                        if full_path not in seen_paths:
                            seen_paths.add(full_path)
                            found.append(full_path)

                        if len(found) >= 10:
                            break
                if len(found) >= 10:
                    break
        except PermissionError:
            continue

    if not found:
        return f"Error: No file matching '{filename}' found in Desktop, Documents, Downloads, or Home."

    if len(found) == 1:
        return f"Found: {found[0]}"

    result_lines = [f"Found {len(found)} matches:"]
    for i, path in enumerate(found, 1):
        result_lines.append(f"  {i}. {path}")
    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# Tool: adb_push_file
# ---------------------------------------------------------------------------

def adb_push_file(local_path: str, remote_dir: str = "/sdcard/Download/") -> str:
    """Push a local file to the connected Android device via ADB."""
    if not local_path or not local_path.strip():
        return "Error: local_path cannot be empty."

    local_path = local_path.strip()
    if not os.path.isfile(local_path):
        return f"Error: File not found at '{local_path}'."

    if not remote_dir.endswith("/"):
        remote_dir += "/"

    try:
        cmd = f'"{ADB_PATH}" push "{local_path}" "{remote_dir}"'
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=60, shell=True,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            filename = os.path.basename(local_path)
            return f"Success: Pushed '{filename}' to {remote_dir} on device. {output}"
        else:
            return f"Error: ADB push failed. {output}"
    except subprocess.TimeoutExpired:
        return "Error: ADB push timed out (60s limit)."
    except FileNotFoundError:
        return f"Error: ADB not found at '{ADB_PATH}'."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool: adb_check_app
# ---------------------------------------------------------------------------

def adb_check_app(package_name: str) -> str:
    """Check if an Android app is installed on the connected device."""
    if not package_name or not package_name.strip():
        return "Error: package_name cannot be empty."

    package_name = package_name.strip()
    try:
        cmd = f'"{ADB_PATH}" shell pm list packages'
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=15, shell=True,
        )
        if result.returncode != 0:
            return f"Error: ADB command failed. {result.stderr.strip()}"

        search_lower = package_name.lower()
        for line in result.stdout.strip().splitlines():
            pkg = line.replace("package:", "").strip().lower()
            if search_lower in pkg:
                actual_pkg = line.replace("package:", "").strip()
                print(f"  ✅ App found: {actual_pkg}")
                return f"Installed: {actual_pkg}"

        print(f"  ❌ App not found: {package_name}")
        return f"Not Installed: '{package_name}' is not installed on this device."
    except subprocess.TimeoutExpired:
        return "Error: ADB command timed out."
    except FileNotFoundError:
        return f"Error: ADB not found at '{ADB_PATH}'."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool: adb_install_app
# ---------------------------------------------------------------------------

def adb_install_app(local_apk_path: str) -> str:
    """Install an APK file on the connected Android device via ADB."""
    if not local_apk_path or not local_apk_path.strip():
        return "Error: local_apk_path cannot be empty."

    local_apk_path = local_apk_path.strip()
    if not os.path.isfile(local_apk_path):
        return f"Error: APK file not found at '{local_apk_path}'."
    if not local_apk_path.lower().endswith(".apk"):
        return f"Error: File '{local_apk_path}' is not an .apk file."

    try:
        print(f"  📦 Installing APK: {os.path.basename(local_apk_path)}...")
        cmd = f'"{ADB_PATH}" install -r "{local_apk_path}"'
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=120, shell=True,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0 and "Success" in output:
            filename = os.path.basename(local_apk_path)
            print(f"  ✅ Installed: {filename}")
            return f"Success: Installed '{filename}' on device. {output}"
        else:
            print(f"  ❌ Install failed: {output}")
            return f"Error: APK install failed. {output}"
    except subprocess.TimeoutExpired:
        return "Error: APK install timed out (120s limit)."
    except FileNotFoundError:
        return f"Error: ADB not found at '{ADB_PATH}'."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool: find_and_launch_app (DYNAMIC — never guess package names)
# ---------------------------------------------------------------------------

def find_and_launch_app(app_name: str) -> str:
    """Dynamically search the phone's installed packages and launch the best match.

    NEVER guess a package name. This tool searches the Android device's
    package registry for matches and launches the most likely one.

    Args:
        app_name: Common name like "clock", "calculator", "spotify", "camera".

    Returns:
        "Launched <package>" or "App not found on this device."
    """
    if not app_name or not app_name.strip():
        return "Error: app_name cannot be empty."

    app_name = app_name.strip().lower()
    print(f"  🔍 Searching phone for app: '{app_name}'...")

    try:
        cmd = f'"{ADB_PATH}" shell pm list packages'
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=15, shell=True,
        )
        if result.returncode != 0:
            return f"Error: ADB command failed. {result.stderr.strip()}"

        all_packages = []
        for line in result.stdout.strip().splitlines():
            pkg = line.replace("package:", "").strip()
            if pkg:
                all_packages.append(pkg)

        # Search for matches (case-insensitive)
        matches = [p for p in all_packages if app_name in p.lower()]

        if not matches:
            # Try broader search with common aliases
            aliases = {
                "clock": ["clock", "deskclock", "alarm"],
                "calculator": ["calculator", "calc"],
                "camera": ["camera", "cam"],
                "calendar": ["calendar"],
                "gallery": ["gallery", "photos"],
                "music": ["music", "player"],
                "notes": ["notes", "memo"],
                "settings": ["settings"],
                "files": ["files", "filemanager", "myfiles"],
                "contacts": ["contacts"],
                "messages": ["messaging", "mms"],
            }
            search_terms = aliases.get(app_name, [app_name])
            for term in search_terms:
                matches = [p for p in all_packages if term in p.lower()]
                if matches:
                    break

        if not matches:
            return f"App not found: No package matching '{app_name}' is installed on this device."

        # Pick the best match: prefer shorter names, manufacturer-specific packages
        # Sort by length (shorter = more likely the main app) then alphabetically
        matches.sort(key=lambda p: (len(p), p))
        selected = matches[0]

        print(f"  📦 Found {len(matches)} match(es). Launching: {selected}")

        # Launch using monkey (reliable launcher intent)
        launch_cmd = (
            f'"{ADB_PATH}" shell monkey -p {selected}'
            " -c android.intent.category.LAUNCHER 1"
        )
        launch_result = subprocess.run(
            launch_cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=10, shell=True,
        )

        if launch_result.returncode == 0:
            time.sleep(1.5)  # Give the app time to render
            print(f"  ✅ Launched: {selected}")
            return f"Launched: {selected}"
        else:
            output = (launch_result.stdout + launch_result.stderr).strip()
            return f"Error: Failed to launch {selected}. {output}"

    except subprocess.TimeoutExpired:
        return "Error: ADB command timed out."
    except FileNotFoundError:
        return f"Error: ADB not found at '{ADB_PATH}'."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool: press_hardware_key (escape dead ends)
# ---------------------------------------------------------------------------

KEYEVENT_MAP = {
    "BACK": 4,
    "HOME": 3,
    "ENTER": 66,
    "POWER": 26,
    "VOLUME_UP": 24,
    "VOLUME_DOWN": 25,
    "TAB": 61,
    "RECENT_APPS": 187,
}


def press_hardware_key(key: str) -> str:
    """Press a hardware key on the Android device.

    Use this to escape dead ends, close keyboards/popups, or go home.

    Args:
        key: One of "BACK", "HOME", "ENTER", "TAB", "RECENT_APPS".

    Returns:
        "Pressed <key>." or error.
    """
    if not key or not key.strip():
        return f"Error: key cannot be empty. Supported: {list(KEYEVENT_MAP.keys())}"

    key = key.strip().upper()

    if key not in KEYEVENT_MAP:
        return f"Error: Unknown key '{key}'. Supported: {list(KEYEVENT_MAP.keys())}"

    keycode = KEYEVENT_MAP[key]

    try:
        cmd = f'"{ADB_PATH}" shell input keyevent {keycode}'
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=10, shell=True,
        )

        if result.returncode == 0:
            time.sleep(0.5)
            print(f"  ⌨️  Pressed: {key} (keycode {keycode})")
            return f"Pressed {key}."
        else:
            output = (result.stdout + result.stderr).strip()
            return f"Error: Key press failed. {output}"

    except subprocess.TimeoutExpired:
        return "Error: Key press timed out."
    except FileNotFoundError:
        return f"Error: ADB not found at '{ADB_PATH}'."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool: android_intent_dispatcher (INSTANT actions — bypasses UI)
# ---------------------------------------------------------------------------

def _escape_for_adb_shell(text: str) -> str:
    """Escape a string for safe passage through 'adb shell am start --es'.

    - Converts Python newlines to %0A so Android Intents preserve line breaks.
    - Uses shlex.quote() for shell-safety, then strips the outer single-quotes.
    """
    text = text.replace("\\n", "%0A").replace("\n", "%0A")
    escaped = shlex.quote(text)
    if escaped.startswith("'") and escaped.endswith("'"):
        escaped = escaped[1:-1]
    return escaped


def android_intent_dispatcher(
    app: str,
    target: str = "",
    subject: str = "",
    body: str = "",
    attachment_phone_path: str = "",
    hour: str = "",
    minutes: str = "",
    message: str = "",
) -> str:
    """Fire raw Android intents via ADB for instant, accurate execution.

    Bypasses the UI entirely — opens the app with fields pre-filled.

    Args:
        app: "gmail", "whatsapp", "browser", "dialer"/"call", "sms", "alarm".
        target: Email address, phone number, or URL.
        subject: Email subject (gmail only).
        body: Message body (gmail, whatsapp, sms).
        attachment_phone_path: Path ON THE PHONE (e.g. "/sdcard/Download/file.pdf").
        hour: Hour for alarm (0-23).
        minutes: Minutes for alarm (0-59).
        message: Alarm label.
    """
    if not app or not app.strip():
        return "Error: 'app' cannot be empty. Supported: gmail, whatsapp, browser, dialer, sms, alarm."

    app = app.strip().lower()

    try:
        if app == "gmail":
            safe_subject = _escape_for_adb_shell(subject) if subject else ""
            safe_body = _escape_for_adb_shell(body) if body else ""
            cmd_parts = [
                f'"{ADB_PATH}" shell am start',
                "-a android.intent.action.SEND",
                '-t "message/rfc822"',
                "-n com.google.android.gm/.ComposeActivityGmailExternal",
            ]
            if target:
                cmd_parts.append(f"--es android.intent.extra.EMAIL '{target}'")
            if safe_subject:
                cmd_parts.append(f"--es android.intent.extra.SUBJECT '{safe_subject}'")
            if safe_body:
                cmd_parts.append(f"--es android.intent.extra.TEXT '{safe_body}'")
            if attachment_phone_path:
                cmd_parts.append(
                    f'--eu android.intent.extra.STREAM "file://{attachment_phone_path}"'
                )
            cmd = " ".join(cmd_parts)
            print(f"  📧 Gmail intent → {target or '(no recipient)'}")

        elif app == "whatsapp":
            phone_clean = re.sub(r"[^\d+]", "", target) if target else ""
            body_encoded = quote(body) if body else ""
            url = f"https://api.whatsapp.com/send?phone={phone_clean}"
            if body_encoded:
                url += f"&text={body_encoded}"
            cmd = f""""{ADB_PATH}" shell am start -a android.intent.action.VIEW -d '{url}'"""
            print(f"  💬 WhatsApp intent → {phone_clean or '(no number)'}")

        elif app == "browser":
            url = target if target else "https://www.google.com"
            cmd = f""""{ADB_PATH}" shell am start -a android.intent.action.VIEW -d '{url}'"""
            print(f"  🌐 Browser intent → {url[:60]}")

        elif app in ("dialer", "call"):
            phone_clean = re.sub(r"[^\d+]", "", target) if target else ""
            if len(phone_clean) < 5:
                return f"Error: Invalid phone number '{target}'."
            cmd = f'"{ADB_PATH}" shell am start -a android.intent.action.CALL -d "tel:{phone_clean}"'
            print(f"  📞 Call intent → {phone_clean}")

        elif app == "sms":
            phone_clean = re.sub(r"[^\d+]", "", target) if target else ""
            safe_body = _escape_for_adb_shell(body) if body else ""
            cmd = (
                f'"{ADB_PATH}" shell am start'
                f" -a android.intent.action.SENDTO"
                f" -d 'sms:{phone_clean}'"
                f" --es sms_body '{safe_body}'"
            )
            print(f"  💬 SMS intent → {phone_clean}")

        elif app == "alarm":
            h = int(hour) if hour else 8
            m = int(minutes) if minutes else 0
            label = message or "OmniClaw Alarm"
            cmd = (
                f'"{ADB_PATH}" shell am start'
                " -a android.intent.action.SET_ALARM"
                f" --ei android.intent.extra.alarm.HOUR {h}"
                f" --ei android.intent.extra.alarm.MINUTES {m}"
                f" --es android.intent.extra.alarm.MESSAGE '{_escape_for_adb_shell(label)}'"
                " --ez android.intent.extra.alarm.SKIP_UI true"
            )
            print(f"  ⏰ Alarm intent → {h:02d}:{m:02d} ({label})")

        elif app == "timer":
            # duration from 'hour' (minutes) and 'minutes' (seconds), or just total seconds
            mins = int(hour) if hour else 0
            secs = int(minutes) if minutes else 0
            total_seconds = mins * 60 + secs
            if total_seconds <= 0:
                total_seconds = 300  # default 5 min
            label = message or "OmniClaw Timer"
            cmd = (
                f'"{ADB_PATH}" shell am start'
                " -a android.intent.action.SET_TIMER"
                f" --ei android.intent.extra.timer.LENGTH {total_seconds}"
                f" --es android.intent.extra.timer.MESSAGE '{_escape_for_adb_shell(label)}'"
                " --ez android.intent.extra.timer.SKIP_UI true"
            )
            print(f"  ⏱️ Timer intent → {total_seconds}s ({label})")

        elif app == "calendar":
            # Calendar event: target=title, subject=location, body=description
            # hour/minutes used for start time relative to now
            import datetime
            now = datetime.datetime.now()
            start_h = int(hour) if hour else now.hour + 1
            start_m = int(minutes) if minutes else 0
            start_dt = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
            if start_dt < now:
                start_dt += datetime.timedelta(days=1)
            end_dt = start_dt + datetime.timedelta(hours=1)
            begin_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)
            title = _escape_for_adb_shell(target) if target else "OmniClaw Event"
            desc = _escape_for_adb_shell(body) if body else ""
            location = _escape_for_adb_shell(subject) if subject else ""
            cmd_parts = [
                f'"{ADB_PATH}" shell am start',
                "-a android.intent.action.INSERT",
                "-d content://com.android.calendar/events",
                f"--el beginTime {begin_ms}",
                f"--el endTime {end_ms}",
                f"--es title '{title}'",
            ]
            if desc:
                cmd_parts.append(f"--es description '{desc}'")
            if location:
                cmd_parts.append(f"--es eventLocation '{location}'")
            cmd = " ".join(cmd_parts)
            print(f"  📅 Calendar intent → {target or 'Event'} at {start_h:02d}:{start_m:02d}")

        else:
            return (
                f"Error: Unsupported app '{app}'. "
                "Supported: gmail, whatsapp, browser, dialer/call, sms, alarm, timer, calendar."
            )

        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=15, shell=True,
        )
        output = (result.stdout + result.stderr).strip()

        if result.returncode == 0:
            time.sleep(1.0)
            return (
                f"Intent executed successfully for '{app}'. "
                "The app is now open with fields pre-filled. "
                "User is reviewing the screen. "
                "If a 'Send' button needs to be tapped, use execute_android_ui_task."
            )
        else:
            return f"Error: Intent failed. {output}"

    except subprocess.TimeoutExpired:
        return "Error: Intent command timed out."
    except FileNotFoundError:
        return f"Error: ADB not found at '{ADB_PATH}'."
    except Exception as e:
        return f"Error: Intent dispatch failed: {e}"


# ---------------------------------------------------------------------------
# Tool: execute_android_ui_task (with STATE-HASH anti-loop)
# ---------------------------------------------------------------------------

LAUNCH_DELAY = 1.5
VERIFY_DELAY = 0.8
DEFAULT_MAX_STEPS = 10
MAX_CONSECUTIVE_FAILS = 3


def _hash_xml(xml_str: str) -> str:
    """Create a fast hash of the UI XML to detect unchanged screens."""
    return hashlib.md5(xml_str.encode("utf-8", errors="replace")).hexdigest()


def _execute_action(action, ui_elements, context):
    """Execute a single UI action. Returns (success, action_type, description)."""
    action_type = action.get("action")

    # ─── BLOCKED ACTIONS (inner LLM must NOT launch apps or make calls) ───
    if action_type == "launch":
        return False, action_type, "BLOCKED: launch is forbidden. Use tap/type/back/enter only."

    if action_type == "call":
        return False, action_type, "BLOCKED: call is forbidden. Return DONE — orchestrator handles calls."

    if action_type == "open_url":
        return False, action_type, "BLOCKED: open_url is forbidden. Return DONE — orchestrator handles URLs."

    # ─── ALLOWED ACTIONS ───
    if action_type == "type":
        text = action.get("text", "")
        if not text:
            return False, action_type, "Missing text"
        success = adb_utils.type_text(text)
        short = text[:50] + ("..." if len(text) > 50 else "")
        return success, action_type, 'Type "' + short + '"'

    elif action_type == "tap":
        target_id = action.get("target_id")
        if target_id is None:
            return False, action_type, "Missing target_id"
        matched = None
        for e in ui_elements:
            if e["id"] == target_id:
                matched = e
                break
        if not matched:
            return False, action_type, "Element " + str(target_id) + " not found"
        cx, cy = matched["cx"], matched["cy"]
        label = matched.get("text") or matched.get("desc") or "(no label)"
        success = adb_utils.tap(cx, cy)
        return success, action_type, 'Tap "' + str(label)[:40] + '"'

    elif action_type == "back":
        success = adb_utils.press_back()
        return success, action_type, "Back"

    elif action_type == "enter":
        success = adb_utils.press_enter()
        return success, action_type, "Enter"

    elif action_type == "research":
        query = action.get("query", "")
        if not query:
            return False, action_type, "Missing query"
        print("  Research: " + query)
        result = web_utils.search_web(query)
        context["research"] = context.get("research", "") + "\n--- Research: " + query + " ---\n" + result + "\n"
        return True, action_type, 'Research "' + query[:40] + '"'

    else:
        return False, action_type, "Unknown: " + str(action_type)


def execute_android_ui_task(task_description: str, max_steps: int = DEFAULT_MAX_STEPS) -> str:
    """Run the OmniClaw UI automation engine for a specific Android task.

    Has:
      - Hard step limit (max_steps kill-switch) to prevent infinite loops.
      - STATE HASHING: detects when the screen doesn't change after a tap
        and returns a hard error instead of looping forever.
      - Enhanced UI parsing with resource-id and hint text.

    Args:
        task_description: A specific UI goal, e.g. "Tap the Send button in Gmail"
        max_steps: Max action steps before bailing out (default: 10).

    Returns:
        A summary string of what happened.
    """
    if not task_description or not task_description.strip():
        return "Error: task_description cannot be empty."

    goal = task_description.strip()
    max_steps = min(max(int(max_steps), 1), 25)

    print(f"\n  📱 Android UI Task: \"{goal}\" (max {max_steps} steps)")

    history = []
    attempted_actions = set()
    consecutive_fails = 0
    context = {}
    steps_executed = 0
    previous_xml_hash = None

    for turn in range(1, max_steps + 5):
        # ----- Kill-switch -----
        if steps_executed >= max_steps:
            return (
                f"UI Task Timed Out after {steps_executed} steps. "
                f"Last actions: {'; '.join(history[-3:])}. "
                "Returning control to orchestrator."
            )

        # ----- PERCEIVE (enhanced with state hashing) -----
        try:
            xml_str = adb_utils.dump_ui()
            current_hash = _hash_xml(xml_str)
            elements = _parse_ui_enhanced(xml_str)
        except RuntimeError as e:
            print(f"  ❌ UI dump failed: {e}")
            time.sleep(2)
            continue

        if not elements:
            print("  ⚠️  No UI elements, waiting...")
            time.sleep(2)
            continue

        # ----- STATE-HASH ANTI-LOOP -----
        if (previous_xml_hash is not None
                and current_hash == previous_xml_hash
                and steps_executed > 0):
            stale_msg = (
                "ACTION FAILED: Screen did not change after last action. "
                "The button was unresponsive or the tap hit a non-interactive element. "
                "Try a DIFFERENT UI element, or use press_hardware_key('BACK') to reset."
            )
            history.append("⚠️ STALE SCREEN — no state change detected")
            print(f"  ⚠️  State hash unchanged: {current_hash[:8]}")
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                return (
                    f"UI Task Failed: Screen stuck for {MAX_CONSECUTIVE_FAILS} actions. "
                    f"Hash: {current_hash[:8]}. "
                    "Returning control to orchestrator — try press_hardware_key('BACK') or a different approach."
                )
            # Feed stale-screen error back into history so LLM adapts
            history.append(stale_msg)

        # ----- THINK -----
        try:
            action = llm_router.get_next_action(
                goal, elements, history,
                context=context.get("research", "")
            )
        except RuntimeError as e:
            return f"Error: LLM failed — {e}"

        # DONE?
        if action.get("status") == "DONE":
            summary = action.get("summary", "Goal completed.")
            print(f"  ✅ UI Task Done: {summary}")
            return f"Task Complete: {summary}"

        action_type = action.get("action", "?")

        # ----- ANTI-LOOP (action dedup) -----
        if action_type == "tap":
            action_key = "tap:" + str(action.get("target_id"))
        elif action_type == "call":
            action_key = "call:" + str(action.get("phone"))
        elif action_type == "type":
            action_key = "type:" + str(action.get("text"))
        elif action_type == "launch":
            action_key = "launch:" + str(action.get("package"))
        elif action_type == "research":
            action_key = "research:" + str(action.get("query"))
        else:
            action_key = action_type

        if action_key in attempted_actions:
            history.append("BLOCKED: repeated " + action_key)
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                return (
                    f"UI Task Failed: Stuck in loop after {steps_executed} steps. "
                    f"Repeated action: {action_key}"
                )
            continue

        attempted_actions.add(action_key)

        # ----- ACT -----
        success, executed_type, desc = _execute_action(action, elements, context)
        steps_executed += 1

        status_str = desc
        if not success:
            status_str += " -> FAILED"
        history.append(status_str)

        if not success:
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                return (
                    f"UI Task Failed: {MAX_CONSECUTIVE_FAILS} consecutive failures "
                    f"after {steps_executed} steps."
                )
            continue

        consecutive_fails = 0
        # Save hash for next iteration's state comparison
        previous_xml_hash = current_hash

        if executed_type == "research":
            continue

        # ----- VERIFY -----
        expected = action.get("expected_state", "")
        if expected:
            time.sleep(VERIFY_DELAY)
            try:
                new_xml = adb_utils.dump_ui()
                new_elements = _parse_ui_enhanced(new_xml)
                result = llm_router.verify_action(expected, new_elements)
                ok = result.get("verified", True)
                obs = result.get("observation", "")
                if ok:
                    history.append("  -> OK")
                else:
                    history.append("  -> FAILED: " + obs)
            except Exception as e:
                print(f"  ⚠️  Verify error: {e}")

    return (
        f"UI Task Timed Out after {steps_executed} steps. "
        "Returning control to orchestrator."
    )


# ---------------------------------------------------------------------------
# Enhanced UI Parser (extracts resource-id and hint for field precision)
# ---------------------------------------------------------------------------

def _extract_center(bounds_str: str):
    """Extract center (x, y) from bounds '[x1,y1][x2,y2]'."""
    match = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
    if len(match) != 2:
        return None
    x1, y1 = int(match[0][0]), int(match[0][1])
    x2, y2 = int(match[1][0]), int(match[1][1])
    return (x1 + x2) // 2, (y1 + y2) // 2


def _parse_ui_enhanced(xml_str: str) -> list[dict]:
    """Parse UI XML into elements with resource-id, hint, and type info."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError as e:
        print(f"  ❌ XML parse error: {e}")
        return []

    elements = []
    node_id = 0

    for node in root.iter("node"):
        text = node.get("text", "").strip()
        desc = node.get("content-desc", "").strip()
        hint = node.get("hint", "").strip()
        resource_id = node.get("resource-id", "").strip()
        clickable = node.get("clickable", "false") == "true"
        long_clickable = node.get("long-clickable", "false") == "true"
        focusable = node.get("focusable", "false") == "true"
        focused = node.get("focused", "false") == "true"
        bounds = node.get("bounds", "")
        class_name = node.get("class", "")

        is_interactable = clickable or long_clickable or focusable
        has_content = bool(text or desc or hint)
        if not (is_interactable or has_content):
            continue

        center = _extract_center(bounds)
        if center is None:
            continue
        cx, cy = center

        if cy < 80 or cx < 0 or cx > 1080 or cy > 2400:
            continue

        cl = class_name.lower()
        widget_type = "view"
        if "edittext" in cl:
            widget_type = "input"
        elif "button" in cl or "imagebutton" in cl:
            widget_type = "button"
        elif "imageview" in cl:
            widget_type = "icon"
        elif "textview" in cl:
            widget_type = "text"
        elif "checkbox" in cl or "switch" in cl:
            widget_type = "toggle"

        node_id += 1
        entry = {
            "id": node_id,
            "type": widget_type,
            "cx": cx,
            "cy": cy,
        }

        if text:
            entry["text"] = text
        if desc:
            entry["desc"] = desc
        if hint:
            entry["hint"] = hint
        if resource_id:
            short_rid = resource_id.split("/")[-1] if "/" in resource_id else resource_id
            entry["res_id"] = short_rid
        if focused:
            entry["focused"] = True

        elements.append(entry)

    print(f"  🔍 {len(elements)} elements (enhanced)")
    return elements


# ---------------------------------------------------------------------------
# Tool: search_web (wrapper)
# ---------------------------------------------------------------------------

def search_web_tool(query: str) -> str:
    """Search the web for information using DuckDuckGo."""
    if not query or not query.strip():
        return "Error: query cannot be empty."
    return web_utils.search_web(query.strip())


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "search_local_file": {
        "function": search_local_file,
        "description": (
            "Search the local PC for a file by name or partial name. "
            "Args: {\"filename\": \"<name or partial name>\"}. "
            "Returns the absolute file path(s) or an error."
        ),
    },
    "adb_push_file": {
        "function": adb_push_file,
        "description": (
            "Push a local file to the connected Android device via ADB. "
            "Args: {\"local_path\": \"<absolute path>\", \"remote_dir\": \"/sdcard/Download/\" (optional)}. "
            "Returns success or error."
        ),
    },
    "adb_check_app": {
        "function": adb_check_app,
        "description": (
            "Check if an Android app is installed on the connected device. "
            "Args: {\"package_name\": \"<package name e.g. com.twitter.android>\"}. "
            "Returns 'Installed: <package>' or 'Not Installed'."
        ),
    },
    "adb_install_app": {
        "function": adb_install_app,
        "description": (
            "Install an APK file from the local PC onto the connected Android device. "
            "Args: {\"local_apk_path\": \"<absolute path to .apk file>\"}. "
            "Returns success or error."
        ),
    },
    "find_and_launch_app": {
        "function": find_and_launch_app,
        "description": (
            "Dynamically search the phone for an app by common name and launch it. "
            "NEVER guess package names — use this tool instead. "
            "Args: {\"app_name\": \"<common name like clock, calculator, spotify>\"}. "
            "Returns 'Launched <package>' or 'App not found'."
        ),
    },
    "press_hardware_key": {
        "function": press_hardware_key,
        "description": (
            "Press a hardware key on the Android device. Use to escape dead ends, "
            "close keyboards/popups, or go home. "
            "Args: {\"key\": \"BACK|HOME|ENTER|TAB|RECENT_APPS\"}. "
            "Returns 'Pressed <key>'."
        ),
    },
    "android_intent_dispatcher": {
        "function": android_intent_dispatcher,
        "description": (
            "INSTANT action: Fire raw Android intents to open apps with pre-filled fields. "
            "Bypasses UI entirely. Supports: gmail, whatsapp, browser, dialer/call, sms, alarm. "
            "Args: {\"app\": \"gmail|whatsapp|browser|dialer|sms|alarm\", \"target\": \"<email/phone/url>\", "
            "\"subject\": \"<subject>\" (gmail), \"body\": \"<message body>\", "
            "\"attachment_phone_path\": \"/sdcard/Download/file.pdf\" (optional), "
            "\"hour\": \"8\" (alarm), \"minutes\": \"0\" (alarm), \"message\": \"label\" (alarm)}. "
            "Returns success. The app opens with fields pre-filled instantly."
        ),
    },
    "execute_android_ui_task": {
        "function": execute_android_ui_task,
        "description": (
            "LAST RESORT: Control the Android phone's UI by tapping, typing, scrolling. "
            "Has STATE-HASH anti-loop: detects when screen doesn't change and returns error. "
            "Use ONLY for custom apps or tasks that other tools cannot handle. "
            "Args: {\"task_description\": \"<specific UI goal>\", \"max_steps\": 10 (optional)}. "
            "Returns completion summary or 'ACTION FAILED' if stuck."
        ),
    },
    "search_web": {
        "function": search_web_tool,
        "description": (
            "Search the web for information using DuckDuckGo. "
            "Args: {\"query\": \"<search query>\"}. "
            "Returns search results as text."
        ),
    },
}


def dispatch_tool(tool_name: str, arguments: dict) -> str:
    """Look up a tool by name and call it with the provided arguments."""
    if tool_name not in TOOL_REGISTRY:
        return f"Error: Unknown tool '{tool_name}'. Available: {list(TOOL_REGISTRY.keys())}"

    func = TOOL_REGISTRY[tool_name]["function"]

    try:
        return func(**arguments)
    except TypeError as e:
        return f"Error: Bad arguments for '{tool_name}': {e}"
    except Exception as e:
        return f"Error: Tool '{tool_name}' failed: {e}"

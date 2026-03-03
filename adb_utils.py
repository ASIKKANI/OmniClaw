"""
adb_utils.py — ADB command wrappers for OmniClaw.

Provides:
  - launch_app, type_text, tap: Basic device control.
  - call_number, open_url: Direct intent shortcuts (bypass UI).
  - press_back, press_enter, press_home: Hardware key simulation.
  - dump_ui, parse_ui: UI hierarchy inspection.
"""

import re
import subprocess
import time
import xml.etree.ElementTree as ET


# Full path to adb.exe
ADB_PATH = r"C:\Users\asikk\Desktop\platform-tools\adb.exe"

UI_DUMP_RETRIES = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_adb(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """Run an ADB command and return the result."""
    cmd = f'"{ADB_PATH}" ' + " ".join(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=True,
        shell=True,
    )


def _extract_center(bounds_str: str) -> tuple[int, int] | None:
    """Extract center (x, y) from bounds "[x1,y1][x2,y2]"."""
    match = re.findall(r"\[(\d+),(\d+)\]", bounds_str)
    if len(match) != 2:
        return None
    x1, y1 = int(match[0][0]), int(match[0][1])
    x2, y2 = int(match[1][0]), int(match[1][1])
    return (x1 + x2) // 2, (y1 + y2) // 2


# ---------------------------------------------------------------------------
# Basic Device Control
# ---------------------------------------------------------------------------

def launch_app(package: str) -> bool:
    """Launch an app by package name using monkey."""
    try:
        cmd = (
            f'"{ADB_PATH}" shell monkey '
            f'-p {package} -c android.intent.category.LAUNCHER 1'
        )
        result = subprocess.run(
            cmd, capture_output=True, encoding="utf-8",
            errors="replace", timeout=15, shell=True,
        )
        if "Events injected: 1" in result.stdout:
            print(f"  ✅ Launched {package}")
            return True
        else:
            print(f"  ❌ Failed to launch {package}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout launching {package}")
        return False


def type_text(text: str) -> bool:
    """Type text on the device (shell-safe). Spaces → %s, specials escaped."""
    sanitized = text
    for char in ['&', '<', '>', '(', ')', '|', ';', '"', "'", '`', '$', '\\', '!', '?', '*', '#']:
        sanitized = sanitized.replace(char, f'\\{char}')
    sanitized = sanitized.replace(" ", "%s")

    try:
        _run_adb(["shell", "input", "text", f'"{sanitized}"'])
        print(f"  ✅ Typed: \"{text}\"")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to type: {e.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout typing")
        return False


def tap(x: int, y: int) -> bool:
    """Tap at exact pixel coordinates."""
    try:
        _run_adb(["shell", "input", "tap", str(x), str(y)])
        print(f"  ✅ Tapped at ({x}, {y})")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to tap: {e.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout tapping")
        return False


# ---------------------------------------------------------------------------
# Direct Intent Shortcuts (bypass UI navigation entirely)
# ---------------------------------------------------------------------------

def call_number(phone: str) -> bool:
    """Directly initiate a phone call via Android intent.

    This bypasses ALL UI navigation — one ADB command = call starts.
    """
    # Strip any non-digit chars except +
    clean = re.sub(r"[^\d+]", "", phone)
    try:
        _run_adb(["shell", "am", "start", "-a", "android.intent.action.CALL",
                   "-d", f"tel:{clean}"])
        print(f"  ✅ Calling {clean}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Call failed: {e.stderr.strip()}")
        return False


def open_url(url: str) -> bool:
    """Open a URL in the default browser via Android intent."""
    try:
        _run_adb(["shell", "am", "start", "-a", "android.intent.action.VIEW",
                   "-d", f'"{url}"'])
        print(f"  ✅ Opened {url}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Open URL failed: {e.stderr.strip()}")
        return False


# ---------------------------------------------------------------------------
# Hardware Key Simulation
# ---------------------------------------------------------------------------

def press_back() -> bool:
    """Press the Android Back button."""
    try:
        _run_adb(["shell", "input", "keyevent", "4"])
        print(f"  ✅ Pressed BACK")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(f"  ❌ Failed to press BACK")
        return False


def press_enter() -> bool:
    """Press the Enter/Return key (useful after typing in search fields)."""
    try:
        _run_adb(["shell", "input", "keyevent", "66"])
        print(f"  ✅ Pressed ENTER")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(f"  ❌ Failed to press ENTER")
        return False


def press_home() -> bool:
    """Press the Home button."""
    try:
        _run_adb(["shell", "input", "keyevent", "3"])
        print(f"  ✅ Pressed HOME")
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(f"  ❌ Failed to press HOME")
        return False


# ---------------------------------------------------------------------------
# UI Hierarchy Inspection
# ---------------------------------------------------------------------------

def dump_ui() -> str:
    """Dump the current UI hierarchy as XML. Retries on failure."""
    for attempt in range(1, UI_DUMP_RETRIES + 2):
        try:
            _run_adb(["shell", "uiautomator", "dump", "/data/local/tmp/dump.xml"], timeout=15)
            result = _run_adb(["shell", "cat", "/data/local/tmp/dump.xml"], timeout=10)
            xml_str = result.stdout.strip()

            if xml_str and (xml_str.startswith("<?xml") or xml_str.startswith("<hierarchy")):
                print(f"  📄 UI dumped ({len(xml_str)} chars)")
                return xml_str

            if attempt <= UI_DUMP_RETRIES:
                print(f"  ⚠️  Empty dump, retrying...")
                time.sleep(0.5)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt <= UI_DUMP_RETRIES:
                print(f"  ⚠️  Dump error, retrying...")
                time.sleep(0.5)

    raise RuntimeError("UI dump failed after all retries.")


def parse_ui(xml_str: str) -> list[dict]:
    """Parse UI XML into interactable elements with center coords, type, focus.

    Filters: status bar (top 80px), off-screen, non-interactable.
    """
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
        clickable = node.get("clickable", "false") == "true"
        long_clickable = node.get("long-clickable", "false") == "true"
        focusable = node.get("focusable", "false") == "true"
        focused = node.get("focused", "false") == "true"
        bounds = node.get("bounds", "")
        class_name = node.get("class", "")

        is_interactable = clickable or long_clickable or focusable
        has_content = bool(text or desc)
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
        elements.append({
            "id": node_id,
            "text": text,
            "desc": desc,
            "cx": cx,
            "cy": cy,
            "focused": focused,
            "type": widget_type,
        })

    print(f"  🔍 {len(elements)} interactable elements")
    return elements

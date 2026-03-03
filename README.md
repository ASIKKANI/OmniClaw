<p align="center">
  <img src="https://img.shields.io/badge/🦀-OmniClaw-FF6B35?style=for-the-badge&labelColor=1a1a2e" alt="OmniClaw"/>
</p>

<h1 align="center">OmniClaw</h1>

<p align="center">
  <strong>An Autonomous General-Intelligence Agent That Controls Your Android Phone</strong>
</p>

<p align="center">
  <em>Speak or type a goal → OmniClaw reasons, plans, and executes it on your phone — hands-free.</em>
</p>

<p align="center">
  <a href="#features"><img src="https://img.shields.io/badge/Features-9_Tools-blue?style=flat-square" alt="Tools"/></a>
  <a href="#architecture"><img src="https://img.shields.io/badge/Architecture-ReAct_Loop-purple?style=flat-square" alt="Architecture"/></a>
  <a href="https://github.com/ASIKKANI/OmniClaw/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License"/></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/LLM-Llama_3.1_70B-FF6F00?style=flat-square&logo=meta&logoColor=white" alt="Llama"/>
  <img src="https://img.shields.io/badge/Platform-Android_via_ADB-3DDC84?style=flat-square&logo=android&logoColor=white" alt="Android"/>
  <img src="https://img.shields.io/badge/Voice-Whisper-74aa9c?style=flat-square&logo=openai&logoColor=white" alt="Whisper"/>
  <img src="https://img.shields.io/badge/Server-Flask_SSE-000000?style=flat-square&logo=flask&logoColor=white" alt="Flask"/>
</p>

---

## 🎯 What Is OmniClaw?

OmniClaw is an **autonomous AI agent** that takes a natural-language goal — spoken or typed — and executes it on a connected Android device. It combines **LLM reasoning** (Llama 3.1 70B via NVIDIA NIM), **Android Debug Bridge** control, **voice input** (Whisper), and a **real-time web dashboard** into a single system that can:

- 📧 Draft and send emails with real-time web research
- 📞 Make phone calls and send WhatsApp/SMS messages
- ⏰ Set alarms, timers, and calendar events
- 🌐 Open URLs and search the web
- 📱 Navigate any Android app through UI automation
- 🔍 Find, install, and launch apps dynamically
- 📎 Locate local files and push them to the phone

> **Think Siri + Jarvis** — but open-source, running locally, and powered by a 70B-parameter LLM.

---

## 🧪 Demo

| Voice Command | What Happens |
|---|---|
| *"Email alex@gmail.com about the latest SpaceX launch"* | Searches the web → drafts email with real data → opens Gmail with fields pre-filled |
| *"Set an alarm for 7:30 AM"* | **Fast-path**: instant intent dispatch, no LLM needed (< 1 second) |
| *"Send 100rs to Yeswanth on FamPay"* | Launches FamPay → navigates UI → finds contact → enters amount |
| *"Open the calculator and compute 500 × 2"* | Dynamically finds calculator package → launches → taps buttons → reads result |

---

## ✨ Features

### ⚡ Three Execution Tiers

| Tier | Speed | When |
|---|---|---|
| **Fast-Path** | < 1s | Alarms, calls, SMS, browser, calendar — bypasses LLM entirely |
| **Intent Dispatch** | ~2s | Gmail, WhatsApp, dialer, timer — fires raw Android intents via ADB |
| **LLM + UI Automation** | 10–60s | Complex tasks requiring multi-step reasoning and screen interaction |

### 🛡️ Multi-Layer Safety

- **Fast-Path Router** — intercepts known patterns before the LLM even runs
- **Intent Interceptor** — code-level guardrail that corrects the LLM if it tries to launch apps that have dedicated intents
- **Action Blocker** — blocks the inner LLM from executing forbidden actions (launch, call, open_url)
- **State-Hash Anti-Loop** — detects unchanged screens and prevents infinite loops
- **Action Deduplication** — prevents repeated identical actions

### 🎙️ Dual Input Modes

- **Voice** — local Whisper transcription (base.en model, CPU, int8)
- **Text** — CLI or web UI

---

## 🏗️ Architecture

```mermaid
graph TB
    subgraph Input
        V["🎙️ Voice Engine<br/><small>Whisper STT</small>"]
        T["⌨️ Text Input<br/><small>CLI / Web UI</small>"]
    end

    subgraph Core["🧠 Core Intelligence"]
        FP["⚡ Fast-Path Router<br/><small>Regex pattern matching</small>"]
        O["🦀 Orchestrator<br/><small>ReAct Loop</small>"]
        LLM["🤖 Llama 3.1 70B<br/><small>NVIDIA NIM API</small>"]
        INT["🛡️ Intent Interceptor<br/><small>Guardrail Layer</small>"]
    end

    subgraph Tools["🔧 Tool Registry"]
        AID["📱 Intent Dispatcher<br/><small>Gmail, WhatsApp, SMS,<br/>Alarm, Timer, Calendar</small>"]
        UI["🖱️ UI Automation<br/><small>Tap, Type, Navigate</small>"]
        APP["📦 App Launcher<br/><small>Dynamic Package Search</small>"]
        WEB["🌐 Web Search<br/><small>DuckDuckGo</small>"]
        FS["📂 File Tools<br/><small>Search, Push, Install</small>"]
        HW["⌨️ Hardware Keys<br/><small>Back, Home, Enter</small>"]
    end

    subgraph Device["📲 Android Device"]
        ADB["ADB Bridge"]
        PHONE["Phone Screen"]
    end

    V --> FP
    T --> FP
    FP -->|"Known pattern"| AID
    FP -->|"Complex task"| O
    O <-->|"Reason ↔ Act"| LLM
    O --> INT
    INT --> AID
    INT --> UI
    INT --> APP
    INT --> WEB
    INT --> FS
    INT --> HW
    AID --> ADB
    UI --> ADB
    APP --> ADB
    HW --> ADB
    ADB --> PHONE

    style FP fill:#ff6b35,color:#fff
    style O fill:#6c5ce7,color:#fff
    style LLM fill:#0984e3,color:#fff
    style INT fill:#d63031,color:#fff
```

---

## 🔄 ReAct Loop

The orchestrator follows a **Reason + Act** cycle until the goal is achieved or the iteration limit is reached:

```mermaid
flowchart LR
    A["🎯 User Goal"] --> B{"⚡ Fast-Path?"}
    B -->|Yes| C["🚀 Intent Dispatch"]
    B -->|No| D["🧠 LLM Thinks"]
    D --> E["📋 JSON Action"]
    E --> F{"🛡️ Interceptor"}
    F -->|Corrected| G["🔧 Execute Tool"]
    F -->|Blocked| D
    G --> H["📤 Tool Result"]
    H --> I{"✅ DONE?"}
    I -->|No| D
    I -->|Yes| J["🏁 Complete"]
    C --> J
```

Each LLM step outputs a structured JSON action:

```json
{
  "thought": "I need SpaceX info. Rule 5: search_web first.",
  "tool": "search_web",
  "arguments": {"query": "latest SpaceX launch news 2026"}
}
```

---

## 📁 Project Structure

```
OmniClaw/
├── main.py              # 🚀 CLI entry point (voice + text modes)
├── server.py            # 🌐 Flask web server with SSE streaming
├── orchestrator.py      # 🧠 ReAct loop, fast-path router, intent interceptor
├── llm_router.py        # 🤖 LLM integration (Llama 3.1 70B via NVIDIA NIM)
├── tools.py             # 🔧 9 tools: intents, UI automation, file ops, web search
├── adb_utils.py         # 📱 ADB command wrappers (tap, type, dump UI, keys)
├── voice_engine.py      # 🎙️ Whisper-based speech-to-text
├── web_utils.py         # 🌐 DuckDuckGo search + page scraping
├── index.html           # 🎨 Web dashboard (single-file, real-time SSE)
├── requirements.txt     # 📦 Python dependencies
└── .env                 # 🔑 API keys (not committed)
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.10+ |
| **ADB** | [Platform Tools](https://developer.android.com/tools/releases/platform-tools) installed and in PATH |
| **Android Device** | Connected via USB with USB Debugging enabled |
| **NVIDIA NIM API Key** | [Get one here](https://build.nvidia.com/) (free tier available) |

### 1. Clone & Install

```bash
git clone https://github.com/ASIKKANI/OmniClaw.git
cd OmniClaw
pip install -r requirements.txt
```

### 2. Configure

Create a `.env` file in the project root:

```env
NVIDIA_API_KEY=nvapi-your-key-here

# Optional overrides
LLAMA_MODEL=meta/llama-3.1-70b-instruct
LLAMA_BASE_URL=https://integrate.api.nvidia.com/v1
```

### 3. Connect Your Phone

```bash
adb devices   # Verify your device appears
```

> Enable **USB Debugging** in Developer Options on your Android device.

### 4. Run

**Web UI** (recommended):
```bash
python server.py
# Open http://localhost:5000
```

**CLI — Voice Mode**:
```bash
python main.py
# Speak your command, silence stops recording
```

**CLI — Text Mode**:
```bash
python main.py --text
# Type your goal and press Enter
```

---

## 🔧 Tools Reference

| # | Tool | Description | Speed |
|---|---|---|---|
| 1 | `android_intent_dispatcher` | Fire Android intents (Gmail, WhatsApp, browser, alarm, timer, calendar, SMS, call) | ⚡ Instant |
| 2 | `find_and_launch_app` | Dynamically search device packages and launch by common name | 🏃 Fast |
| 3 | `press_hardware_key` | Press BACK, HOME, ENTER, TAB, RECENT_APPS | ⚡ Instant |
| 4 | `execute_android_ui_task` | LLM-driven UI automation with anti-loop protection | 🐢 Slow |
| 5 | `search_web` | Search DuckDuckGo for real-time information | 🏃 Fast |
| 6 | `search_local_file` | Find files on the local PC (Desktop, Documents, Downloads) | 🏃 Fast |
| 7 | `adb_push_file` | Push a local file to the Android device | 🏃 Fast |
| 8 | `adb_check_app` | Check if a package is installed on the device | ⚡ Instant |
| 9 | `adb_install_app` | Install an APK on the device | 🐢 Slow |

---

## 🧠 Intelligence Layers

```mermaid
graph LR
    subgraph Layer1["Layer 1: Fast-Path"]
        FP["Regex Pattern Match<br/><small>alarm, call, sms, browser,<br/>timer, calendar, WhatsApp</small>"]
    end

    subgraph Layer2["Layer 2: Orchestrator LLM"]
        ORC["Llama 3.1 70B<br/><small>ReAct reasoning loop<br/>Tool selection & arguments</small>"]
    end

    subgraph Layer3["Layer 3: Inner UI LLM"]
        INNER["Llama 3.1 70B<br/><small>Screen understanding<br/>Tap/Type decisions</small>"]
    end

    subgraph Layer4["Layer 4: Evaluator"]
        EVAL["Progress Evaluator<br/><small>On-track assessment<br/>Course correction</small>"]
    end

    FP -->|"Miss"| ORC
    ORC -->|"UI task"| INNER
    ORC -->|"Check progress"| EVAL
    EVAL -->|"Correction"| ORC

    style FP fill:#ff6b35,color:#fff
    style ORC fill:#6c5ce7,color:#fff
    style INNER fill:#0984e3,color:#fff
    style EVAL fill:#00b894,color:#fff
```

| Layer | Role | Model |
|---|---|---|
| **Fast-Path** | Instant intent dispatch for known patterns | None (regex) |
| **Orchestrator** | Strategic reasoning, tool selection | Llama 3.1 70B |
| **UI Agent** | Screen reading, tap/type decisions | Llama 3.1 70B |
| **Evaluator** | Progress assessment, course correction | Llama 3.1 70B |

---

## 🛡️ Guardrail System

OmniClaw has **three independent layers** preventing the LLM from going off-track:

```mermaid
flowchart TD
    LLM["🤖 LLM Output"] --> G1{"🛡️ Guard 1:<br/>Intent Redirect"}
    G1 -->|"LLM tries UI for alarm"| FIX1["→ Redirect to<br/>intent_dispatcher(alarm)"]
    G1 -->|"Pass"| G2{"🛡️ Guard 2:<br/>Package Block"}
    G2 -->|"LLM uses com.samsung.*"| FIX2["→ BLOCKED<br/>Use find_and_launch_app"]
    G2 -->|"Pass"| G3{"🛡️ Guard 3:<br/>Action Block"}
    G3 -->|"Inner LLM tries launch/call"| FIX3["→ BLOCKED<br/>Return DONE"]
    G3 -->|"Pass"| EXEC["✅ Execute Action"]

    style G1 fill:#e17055,color:#fff
    style G2 fill:#d63031,color:#fff
    style G3 fill:#c0392b,color:#fff
    style EXEC fill:#00b894,color:#fff
```

---

## 🌐 Web Dashboard

The web UI provides a **real-time view** of the agent's thinking process via Server-Sent Events:

- 🎯 Goal display with input bar
- 🧠 Live thought stream (see each ReAct step)
- 🔧 Tool execution with arguments
- 📤 Results from each tool call
- ⏹️ Skip / Stop controls

**Start the dashboard:**
```bash
python server.py
# Navigate to http://localhost:5000
```

---

## 🔑 Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `NVIDIA_API_KEY` | ✅ | — | NVIDIA NIM API key for Llama 3.1 |
| `LLAMA_API_KEY` | ⚠️ | — | Alternative to NVIDIA_API_KEY |
| `LLAMA_MODEL` | ❌ | `meta/llama-3.1-70b-instruct` | Model identifier |
| `LLAMA_BASE_URL` | ❌ | `https://integrate.api.nvidia.com/v1` | API base URL |

---

## 🧩 How It Works — End to End

```mermaid
sequenceDiagram
    actor User
    participant Voice as 🎙️ Voice Engine
    participant FP as ⚡ Fast-Path
    participant Orch as 🧠 Orchestrator
    participant LLM as 🤖 Llama 3.1
    participant Tools as 🔧 Tools
    participant ADB as 📱 ADB
    participant Phone as 📲 Phone

    User->>Voice: "Email alex about SpaceX"
    Voice->>FP: Transcribed text
    FP->>Orch: No fast-path match
    Orch->>LLM: GOAL + System Prompt
    LLM->>Orch: {"tool": "search_web", ...}
    Orch->>Tools: search_web("SpaceX launch")
    Tools-->>Orch: "Starship Flight 10..."
    Orch->>LLM: Tool result + context
    LLM->>Orch: {"tool": "android_intent_dispatcher", ...}
    Orch->>Tools: intent_dispatcher(gmail, ...)
    Tools->>ADB: am start -a SEND ...
    ADB->>Phone: Opens Gmail compose
    Phone-->>Orch: Success
    Orch->>LLM: Intent result
    LLM->>Orch: {"tool": "DONE", ...}
    Orch-->>User: ✅ "Email sent to alex@gmail.com"
```

---

## 📊 Tech Stack

| Component | Technology |
|---|---|
| **LLM** | Meta Llama 3.1 70B Instruct |
| **LLM API** | NVIDIA NIM (OpenAI-compatible) |
| **Voice** | faster-whisper (CTranslate2 backend) |
| **Device Control** | Android Debug Bridge (ADB) |
| **Web Server** | Flask + Server-Sent Events |
| **Web Research** | DuckDuckGo + BeautifulSoup4 |
| **Language** | Python 3.10+ |

---

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

---

## 📜 License

This project is open source and available under the [MIT License](LICENSE).

---

<p align="center">
  <strong>Built with 🦀 by <a href="https://github.com/ASIKKANI">ASIKKANI</a></strong>
  <br/>
  <sub>OmniClaw — One goal. Every action. Fully autonomous.</sub>
</p>

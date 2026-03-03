"""
main.py — OmniClaw Entry Point.

Flow:
  1. Listen for voice input (or accept typed text with --text flag).
  2. Pass the goal to the Llama-powered orchestrator.
  3. Orchestrator reasons, calls tools, and completes the goal.

Usage:
  python main.py              # Voice mode (speak your command)
  python main.py --text       # Text mode (type your command)
"""

import os
import sys

from dotenv import load_dotenv


def main():
    load_dotenv()

    # Check API key
    api_key = os.getenv("LLAMA_API_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        print("❌ No API key found. Set LLAMA_API_KEY or NVIDIA_API_KEY in .env")
        sys.exit(1)

    print()
    print("=" * 50)
    print("  🦀 OmniClaw — Agentic Orchestrator")
    print("=" * 50)

    # Determine input mode
    text_mode = "--text" in sys.argv

    if text_mode:
        # ---- TEXT MODE ----
        print("\n  📝 Text mode. Type your goal below.\n")
        goal = input("  Goal: ").strip()
        if not goal:
            print("  No goal entered. Exiting.")
            sys.exit(0)
    else:
        # ---- VOICE MODE ----
        try:
            import voice_engine
        except ImportError as e:
            print(f"\n  ⚠️  Voice dependencies missing: {e}")
            print("  Install with: pip install faster-whisper sounddevice scipy")
            print("  Falling back to text mode.\n")
            goal = input("  Goal: ").strip()
            if not goal:
                print("  No goal entered. Exiting.")
                sys.exit(0)
        else:
            goal = voice_engine.listen_and_transcribe()
            if not goal:
                print("  No speech detected. Exiting.")
                sys.exit(0)

    # ---- RUN ORCHESTRATOR ----
    print(f'\n  🚀 Orchestrating: "{goal}"\n')

    import orchestrator
    result = orchestrator.run(goal)

    print(f"\n  🏁 Final: {result}")
    print()


if __name__ == "__main__":
    main()

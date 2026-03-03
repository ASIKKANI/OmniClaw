"""
voice_engine.py — The Ears of OmniClaw.

Records audio from the microphone until silence is detected,
transcribes it locally using faster-whisper, and returns the text.
"""

import io
import os
import tempfile
import time

import numpy as np
import sounddevice as sd
from scipy.io import wavfile
from faster_whisper import WhisperModel


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000          # 16 kHz mono — optimal for Whisper
SILENCE_THRESHOLD = 0.015    # RMS below this = silence
SILENCE_DURATION = 1.5       # Seconds of silence before stopping
CHUNK_DURATION = 0.5         # Seconds per audio chunk
MAX_RECORD_SECONDS = 30      # Safety cap

WHISPER_MODEL_SIZE = "base.en"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE = "int8"


# ---------------------------------------------------------------------------
# Lazy-loaded model
# ---------------------------------------------------------------------------

_model = None


def _get_model() -> WhisperModel:
    """Load the Whisper model once, reuse on subsequent calls."""
    global _model
    if _model is None:
        print("  🔄 Loading Whisper model (first time)...")
        _model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE,
        )
        print("  ✅ Whisper model ready.")
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def listen_and_transcribe() -> str:
    """Record from microphone until silence, transcribe, return text.

    Returns:
        The transcribed text, or an empty string on failure.
    """
    print("\n  🎙️  Listening... (speak now, silence to stop)")

    chunks = []
    silent_chunks = 0
    chunks_needed_for_silence = int(SILENCE_DURATION / CHUNK_DURATION)
    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION)
    max_chunks = int(MAX_RECORD_SECONDS / CHUNK_DURATION)

    try:
        for _ in range(max_chunks):
            # Record one chunk
            audio_chunk = sd.rec(
                chunk_samples,
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
            )
            sd.wait()

            rms = np.sqrt(np.mean(audio_chunk ** 2))
            chunks.append(audio_chunk)

            if rms < SILENCE_THRESHOLD:
                silent_chunks += 1
            else:
                silent_chunks = 0

            # Stop after enough silence (but only if we have some speech)
            if silent_chunks >= chunks_needed_for_silence and len(chunks) > chunks_needed_for_silence + 2:
                break

    except Exception as e:
        print(f"  ❌ Microphone error: {e}")
        return ""

    if len(chunks) <= chunks_needed_for_silence + 2:
        print("  ⚠️  No speech detected.")
        return ""

    print("  🔄 Transcribing...")

    # Combine chunks into single array
    audio = np.concatenate(chunks, axis=0).flatten()

    # Convert to int16 for WAV
    audio_int16 = (audio * 32767).astype(np.int16)

    # Write to temp WAV file
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            wavfile.write(tmp_path, SAMPLE_RATE, audio_int16)

        # Transcribe
        model = _get_model()
        segments, info = model.transcribe(tmp_path, beam_size=5)

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        transcript = " ".join(text_parts).strip()

        if transcript:
            print(f'  ✅ You said: "{transcript}"')
        else:
            print("  ⚠️  Transcription empty.")

        return transcript

    except Exception as e:
        print(f"  ❌ Transcription error: {e}")
        return ""

    finally:
        # Cleanup temp file
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

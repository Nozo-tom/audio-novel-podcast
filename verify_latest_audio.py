import os
import sys
import hashlib
import json
from pathlib import Path
from pydub import AudioSegment
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def verify_mp3(file_path):
    print(f"Verifying: {file_path}")
    if not os.path.exists(file_path):
        print("File not found")
        return

    audio = AudioSegment.from_mp3(file_path)
    duration_sec = len(audio) / 1000
    print(f"Duration: {duration_sec:.2f} seconds ({duration_sec/60:.2f} minutes)")

    # Extract first 30 seconds
    first_30 = audio[:30000]
    temp_first = "temp_first.mp3"
    first_30.export(temp_first, format="mp3")

    print("Transcribing first 30 seconds...")
    try:
        with open(temp_first, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ja",
                response_format="text"
            )
        print(f"Result: {transcript}")
    except Exception as e:
        print(f"Transcription error: {e}")
    finally:
        if os.path.exists(temp_first):
            os.remove(temp_first)

# Find the latest MP3 of the target novel
mp3_dir = Path("docs")
target_pattern = "20250915_お母さんの手料理レシピ*"
files = list(mp3_dir.glob(target_pattern + ".mp3"))
if not files:
    print("No matching MP3 found in docs/")
else:
    # Sort by mtime
    latest_file = sorted(files, key=os.path.getmtime)[-1]
    verify_mp3(str(latest_file))

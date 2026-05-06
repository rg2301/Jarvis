# Save as test_voice.py in your jarvis folder and run it
import requests
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

key      = os.getenv("ELEVENLABS_KEY")
voice_id = os.getenv("ELEVENLABS_VOICE_ID")

print(f"Key found:      {bool(key)}")
print(f"Key starts with: {key[:8] if key else 'EMPTY'}")
print(f"Voice ID:        {voice_id}")

url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
headers = {"xi-api-key": key, "Content-Type": "application/json"}
payload = {
    "text": "Jarvis online. All systems nominal, sir.",
    "model_id": "eleven_turbo_v2",
    "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
}

print("\nCalling ElevenLabs...")
r = requests.post(url, headers=headers, json=payload, timeout=30, stream=True)
print(f"Status code: {r.status_code}")

if r.status_code == 200:
    out = Path.home() / "_test_voice.mp3"
    with open(out, "wb") as f:
        for chunk in r.iter_content(4096):
            if chunk:
                f.write(chunk)
    print(f"Audio saved to: {out}  ({out.stat().st_size} bytes)")
    print("Playing...")
    os.system(f"afplay '{out}'")
    print("Done. Did you hear it?")
else:
    print(f"Error: {r.text}")
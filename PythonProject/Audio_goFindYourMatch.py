"""
ElevenLabs Version
"""

import json
import os
import requests
import subprocess
from openai import OpenAI
import ReaperLoad_mp3

# -----------------------------
# CONFIG
# -----------------------------

# ElevenLabs API Key
ELEVENLABS_API_KEY = "sk_f4da161c5a2918a6f13ded354e72d500bf9efc90b0d40f23"
# Voice ID
ELEVENLABS_JESSICA_VOICE = "cgSgspJ2msm6clMCkdW9"

client = OpenAI()

save_root = r"C:\SCI-Arc\F25-STUDIO\FINAL\data\faces\Person_selected"
audio_root = r"C:\SCI-Arc\F25-STUDIO\FINAL\data\YenhsingDeyingAudio\dialogue"
os.makedirs(audio_root, exist_ok=True)


# -----------------------------
# 讀取配對資料
# -----------------------------
def get_matched_person():
    clothes_file = os.path.join(save_root, "clothes.json")

    if not os.path.exists(clothes_file):
        return None

    with open(clothes_file, "r") as f:
        return json.load(f)


# -----------------------------
# 生成一句自然英文提示
# -----------------------------
def generate_natural_call(clothes_data):
    prompt = f"""Based on the following clothing description, generate ONE natural English calling phrase.

Clothing description:
- Top: {clothes_data.get('top', 'unknown')}
- Pants: {clothes_data.get('pants', 'unknown')}
- Shoes: {clothes_data.get('shoes', 'unknown')}

Requirements:
1. Start with "Got them! Go find your match in the..." or "Match confirmed! Say hi to your match in..."
2. Select the most noticeable 1-2 clothing features
3. Sound natural and polite
4. Output ONLY ONE SENTENCE, no extra explanation or variations

Generate only one sentence:"""

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": "You generate exactly one sentence. No explanations, no alternatives, just one instruction phrase."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=50
    )

    result = resp.choices[0].message.content.strip()
    return result.split('\n')[0].strip()


# -----------------------------
# ElevenLabs TTS
# -----------------------------
def text_to_speech(text, filename="match_call"):
    if not filename:
        filename = "match_call"

    audio_path = os.path.join(audio_root, f"{filename}.mp3")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_JESSICA_VOICE}?optimize_streaming_latency=0"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    data = {
        "text": text,
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.9,
            "style": 0.3,
            "use_speaker_boost": True
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        print("❌ ElevenLabs TTS error:", response.text)
        return None

    # 儲存 MP3
    with open(audio_path, "wb") as f:
        f.write(response.content)

    print(f"Audio saved at: {audio_path}")
    return audio_path


# -----------------------------
# 匯入 Reaper 專案
# -----------------------------
def import_to_reaper(audio_path):
    project_path = os.path.join(audio_root, "YenhsingDeyingReaper.rpp")

    if audio_path is None:
        print("❌ No audio file generated.")
        return None

    audio_path_abs = os.path.abspath(audio_path).replace('\\', '/')

    # Verify the MP3 file exists
    if not os.path.exists(audio_path):
        print(f"❌ ERROR: MP3 not found at {audio_path}")
        return None

    print(f"MP3 file: {audio_path_abs}")

    new_track = f"""  <TRACK
    NAME "match_call"
    <ITEM
      POSITION 0
      LENGTH 10
      <SOURCE WAVE
        FILE "{audio_path_abs}"
      >
    >
  >
"""

    # Append or create new RPP
    if os.path.exists(project_path):
        with open(project_path, "r") as f:
            content = f.read()

        content = content.rstrip().rstrip('>')
        content += '\n' + new_track + '>\n'

        with open(project_path, "w") as f:
            f.write(content)
    else:
        content = f"""<REAPER_PROJECT 0.1
{new_track}>
"""
        with open(project_path, "w") as f:
            f.write(content)

    print(f"Added to Reaper project: {project_path}")

    # Open Reaper
    try:
        reaper_path = r"C:\Program Files\REAPER (x64)\reaper.exe"
        if os.path.exists(reaper_path):
            subprocess.Popen([reaper_path, project_path])
    except:
        pass

    return project_path


# -----------------------------
# 完整流程
# -----------------------------
def run_complete_workflow():
    clothes = get_matched_person()

    if not clothes:
        print("❌ No clothes.json found.")
        return

    dialogue = generate_natural_call(clothes)

    # Save text
    text_path = os.path.join(save_root, "match_call.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(dialogue)

    # Convert to speech
    audio_path = text_to_speech(dialogue)

    if audio_path is None:
        print("❌ Audio generation failed.")
        return

    # Import to Reaper
    rm = ReaperLoad_mp3.ReaperManager()
    rm.loadTrackToReaper(audio_path)

    print("\n--- Output ---")
    print("match_call.txt")
    print("match_call.mp3")
    print(dialogue)


if __name__ == "__main__":
    run_complete_workflow()

import os
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()

def split_text_into_chunks(text, max_size=4000):
    paragraphs = text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    chunks = []
    current_chunk = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current_chunk: chunks.append(current_chunk.strip())
            current_chunk = ""
            import re
            sentences = re.split(r'([。！？])', paragraph)
            temp_chunk = ""
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                if i + 1 < len(sentences): sentence += sentences[i + 1]
                if len(temp_chunk) + len(sentence) <= max_size: temp_chunk += sentence
                else:
                    if temp_chunk: chunks.append(temp_chunk.strip())
                    temp_chunk = sentence
            if temp_chunk: current_chunk = temp_chunk
        else:
            test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
            if len(test_chunk) <= max_size: current_chunk = test_chunk
            else:
                if current_chunk: chunks.append(current_chunk.strip())
                current_chunk = paragraph
    if current_chunk: chunks.append(current_chunk.strip())
    return chunks

input_file = "novels/completed/20250915_お母さんの手料理レシピを持って異世界に転移したら、なぜか最強の料理人になった件.txt"
with open(input_file, 'r', encoding='utf-8') as f:
    novel_text = f.read()

novel_text = novel_text.strip()
novel_text = re.sub(r'\r\n', '\n', novel_text)
novel_text = re.sub(r'\n{3,}', '\n\n', novel_text)

# Mimic publish_novel replacements
corrections = {
  "美咲": "みさき",
  "リオ": "りお",
  "銀の鈴亭": "ぎんのすずてい",
  "苦笑い": "にがわらい",
  "味見": "あじみ",
  "手伝って": "てつだって",
  "涙": "なみだ",
  "異世界": "いせかい",
  "転移": "てんい"
}
sorted_corrections = sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True)
for word, reading in sorted_corrections:
    novel_text = novel_text.replace(word, reading)

chunks = split_text_into_chunks(novel_text, 4000)
chunk1 = chunks[0]

print(f"Chunk 1 Length: {len(chunk1)}")
print(f"Chunk 1 Text Start: {chunk1[:100]}")

output_path = "debug_chunk1.mp3"
print(f"Generating audio for chunk 1...")
response = client.audio.speech.create(
    model="tts-1",
    voice="fable",
    input=chunk1,
    response_format="mp3"
)
response.stream_to_file(output_path)

size = os.path.getsize(output_path)
print(f"Chunk 1 MP3 Size: {size} bytes")

# Check duration
from pydub import AudioSegment
audio = AudioSegment.from_mp3(output_path)
print(f"Chunk 1 Duration: {len(audio)/1000} seconds")

# Transcribe beginning and end of chunk 1 audio
def transcribe_part(audio_segment, name):
    temp = f"temp_{name}.mp3"
    audio_segment.export(temp, format="mp3")
    with open(temp, "rb") as f:
        t = client.audio.transcriptions.create(model="whisper-1", file=f, language="ja")
    os.remove(temp)
    return t.text

print(f"Beginning (10s): {transcribe_part(audio[:10000], 'start')}")
print(f"End (10s): {transcribe_part(audio[-10000:], 'end')}")

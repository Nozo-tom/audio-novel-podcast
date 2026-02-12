import re
import os
from pathlib import Path

def split_text_into_chunks(text, max_size=4000):
    paragraphs = text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            import re
            sentences = re.split(r'([。！？])', paragraph)
            temp_chunk = ""
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                if i + 1 < len(sentences):
                    sentence += sentences[i + 1]
                
                if len(temp_chunk) + len(sentence) <= max_size:
                    temp_chunk += sentence
                else:
                    if temp_chunk:
                        chunks.append(temp_chunk.strip())
                    temp_chunk = sentence
            
            if temp_chunk:
                current_chunk = temp_chunk
        else:
            test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
            
            if len(test_chunk) <= max_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
    
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

input_file = "novels/completed/20250915_お母さんの手料理レシピを持って異世界に転移したら、なぜか最強の料理人になった件.txt"
with open(input_file, 'r', encoding='utf-8') as f:
    text = f.read()

text = text.strip()
text = re.sub(r'\r\n', '\n', text)
text = re.sub(r'\n{3,}', '\n\n', text)

chunks = split_text_into_chunks(text, 4000)

with open("chunks_debug.txt", "w", encoding="utf-8") as f:
    f.write(f"Total chunks: {len(chunks)}\n\n")
    for i, chunk in enumerate(chunks):
        f.write(f"--- Chunk {i+1} (Length: {len(chunk)}) ---\n")
        f.write(f"START: {chunk[:200]}\n")
        f.write(f"END: {chunk[-200:]}\n\n")

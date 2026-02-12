import os
import re
import sys
import time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Windows対応
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def create_script(text_path):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        print(f"❌ ファイル読み込みエラー: {e}")
        return

    print(f"📖 文字数: {len(text)} 文字")
    print(f"🎙️ 全文ルビ（ふりがな）付き台本を作成中... (GPT-4o使用)")

    # 1000文字程度で分割して処理（プロンプト落ちを防ぐ）
    chunk_size = 1200
    # 段落で区切る
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""
    for p in paragraphs:
        if len(current_chunk) + len(p) < chunk_size:
            current_chunk += p + "\n"
        else:
            chunks.append(current_chunk)
            current_chunk = p + "\n"
    if current_chunk:
        chunks.append(current_chunk)

    full_script = ""
    
    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
            
        print(f"   ⏳ 処理中 ({i+1}/{len(chunks)}): {chunk[:20].strip()}...")
        
        prompt = f"""
以下の小説テキストの「すべての漢字」に、正しい読み（ひらがな）を [] で付けて、朗読用台本を作成してください。
形式: 漢字[かんじ]

【ルール】
1. すべての漢字に対して `漢字[かんじ]` の形式でルビを振ってください。
2. ひらがな、カタカナ、記号（「」など）、アルファベットはそのまま残してください。
3. 読みが複数ある場合は、文脈的に最も自然な読みを採用してください。
4. 「料理人[りょうりにん]」のように、熟語はまとめて振っても、一文字ずつ振っても構いませんが、TTSが読みやすそうな方を優先してください。
5. 出力は台本のみにしてください。説明や挨拶は一切不要です。

テキスト:
---
{chunk}
---
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o", # 高精度なコンテキスト理解のため4oを使用
                messages=[
                    {"role": "system", "content": "あなたはプロのナレーター用台本作成者です。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )
            script_chunk = response.choices[0].message.content.strip()
            # 稀にAIが返してくるコードブロックマークを除去
            script_chunk = re.sub(r'^```.*?\n', '', script_chunk)
            script_chunk = re.sub(r'\n```$', '', script_chunk)
            
            full_script += script_chunk + "\n"
            
        except Exception as e:
            print(f"⚠️ チャンク {i+1} でエラー: {e}")
            full_script += chunk + "\n" # 失敗した場合は原文をそのまま入れる

    # 出力パス: 小説名.script.txt
    script_path = Path(text_path).with_suffix('.script.txt')
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(full_script.strip())
    
    print(f"\n✨ 台本が完成しました: {script_path}")
    print("💡 このファイルの [] の中身を書き換えることで、読み方を100%制御できます。")
    print("💡 滑舌が悪い箇所は、[りょうり にん] のように中にスペースを入れると改善します。")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        create_script(sys.argv[1])
    else:
        print("使い方: python create_script.py novels/小説.txt")

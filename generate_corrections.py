import os
import re
import yaml
import sys
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# .envの読み込み
load_dotenv()

# Windows対応
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def generate_corrections(text_path):
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
    except Exception as e:
        print(f"❌ 読み込み失敗: {e}")
        return

    print(f"🔍 最強辞書（全文スキャン）を作成中: {Path(text_path).name} ...")
    
    # テキスト量が多い場合は、重要な箇所（最初・中間・最後）をサンプリングしてAIに渡す
    # または全文を投げる（今回は3k-4k文字程度までを想定）
    content_sample = full_text[:4000] 

    prompt = f"""
以下の小説テキストを読み、TTS（音声合成）の読み間違いを防ぐための「完璧な読み辞書」を作成してください。
テキストに登場する「すべての漢字を含む単語（熟語、名前、一般名詞）」を抽出し、正しい読み（ひらがな）をJSONで出力してください。

【抽出ルール】
1. 登場人物の名前（黒崎、花音など）などの固有名詞。
2. 「肉親」「宝物」「料理人」「涙」などの一般名詞。
3. 数字を含む表現（17歳、280歳、1年間など）。
4. 読みが複数ある漢字や、AIが間違えやすい熟語すべて。

出力形式: JSON {{ "単語": "よみ" }}

テキスト:
---
{content_sample}
---
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 抽出精度を上げるため 4o を使用
            messages=[{"role": "system", "content": "あなたはプロの編集者です。"},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        
        corrections = json.loads(response.choices[0].message.content)
        
        filename_stem = Path(text_path).stem
        title = re.sub(r'^\d{8}_', '', filename_stem)
        
        # 性別判定
        gender_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "主人公の性別を 'male' または 'female' で答えてください。"},
                      {"role": "user", "content": content_sample[:1000]}],
        )
        gender = gender_res.choices[0].message.content.strip().lower()
        suggested_voice = "fable" if "male" in gender else "nova"

        yaml_data = {
            "title": title,
            "category": "現実世界[恋愛]",
            "voice": suggested_voice,
            "original_date": filename_stem.split('_')[0] if '_' in filename_stem else "",
            "corrections": corrections
        }
        
        yaml_path = Path(text_path).with_suffix('.yaml')
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
        print(f"✅ 最強辞書を保存しました: {yaml_path}")
        print(f"   登録単語数: {len(corrections)}件")
            
    except Exception as e:
        print(f"❌ 解析エラー: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_corrections(sys.argv[1])

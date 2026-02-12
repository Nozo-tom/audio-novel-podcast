import os
import re
import yaml
import sys
import json
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

# .envの読み込み（OpenAI API Key用）
load_dotenv()

# Windows対応
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

def generate_corrections(text_path):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ エラー: OPENAI_API_KEY が設定されていません。")
        return

    client = OpenAI(api_key=api_key)
    
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            content = f.read(4000)
    except Exception as e:
        print(f"❌ 読み込み失敗: {e}")
        return

    print(f"🔍 AIディープ解析中: {Path(text_path).name} ...")
    
    prompt = f"""
以下の小説テキストを詳細に解析し、読み間違いそうな「人名」「地名」「特殊な用語」「数字の読み（単位含む）」などを抽出してください。

【注意】
- 前の作品のキャラ名（田村美咲、リオなど）を出さないでください。
- 今渡されているテキストに「実際に登場する」語句だけを抽出してください。
- 単位（歳、ヶ月、人など）がつく数字の読みは必ず含めてください。
- 「肉親」「宝物」「無事」などの一般語も、テキスト内にあれば含めてください。

出力形式: JSON {{ "元の表記": "正しい読みのひらがな" }}

テキスト:
---
{content}
---
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "あなたは正確な小説校正者です。"},
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
                      {"role": "user", "content": content[:1000]}],
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
        
        print(f"✅ 正しい辞書を保存しました: {yaml_path}")
        for word, reading in corrections.items():
            print(f"   - {word}: {reading}")
            
    except Exception as e:
        print(f"❌ 解析エラー: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_corrections(sys.argv[1])

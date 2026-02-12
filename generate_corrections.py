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

    print(f"🔍 最強辞書（全文スキャン＆全漢字抽出）を作成中: {Path(text_path).name} ...")
    
    # 解析対象（モデルのトークン制限内で最大化）
    content_sample = full_text[:6000] 

    prompt = f"""
以下の小説テキストに登場する「すべての漢字を含む単語（熟語、固有名詞、一般名詞、動詞、形容詞など）」を漏らさず抽出し、
その正しい読み（ひらがな）をJSON形式でリスト化してください。

【抽出の最重要ルール】
1. 小説に出てくる全ての漢字熟語を対象にしてください。
2. 特に以下の語句はTTSが読み間違えやすいため、確実に入れてください：
   - 「正体（しょうたい）」「成人（せいじん）」「肉親（にくしん）」「宝物（たからもの）」「死神（しにがみ）」「見習い（みならい）」
   - 固有名詞（黒崎レイ、山田花音、桜ヶ丘高校など）
   - 数字と単位（17歳、280歳、1年間、4月、2年B組など）
   - 文脈で読みが変わる語句（昨日、今日、明日、今朝、十分など）
3. 活用語（動詞の送り仮名付きなど）も、読み間違いが懸念されるものは含めてください。

出力形式: JSON {{ "漢字": "ひらがな" }}
※「漢字」は本文中の表記そのまま、「ひらがな」は正しい読みのみ。

テキスト:
---
{content_sample}
---
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 精度優先
            messages=[{"role": "system", "content": "あなたはプロの校正者です。"},
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
        
        print(f"✅ 最強辞書（全網羅版）を保存しました: {yaml_path}")
        print(f"   登録単語数: {len(corrections)}件")
            
    except Exception as e:
        print(f"❌ 解析エラー: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_corrections(sys.argv[1])

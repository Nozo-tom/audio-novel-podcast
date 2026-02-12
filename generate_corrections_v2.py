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

def get_text_analysis_from_ai(client, text_chunk):
    """テキストチャンクから読み間違いそうな単語をAIに抽出させる"""
    prompt = f"""
以下の小説テキストを解析し、TTS（音声合成）が読み間違えそうな「人名」「地名」「特殊な用語」「数字の読み（単位含む）」をすべて抽出してください。
特に以下のパターンを重点的にチェックしてください：
- 日本人の姓名（例: 斉藤、美咲、悠太）
- 異世界もの特有の造語（例: 魔導石、ギルド、レムリア）
- 文脈で読みが変わる漢字（例: 一人暮らし、昨日、明日、十分）
- 数字+単位（例: 10日、25歳、3ヶ月、二倍）
- 料理名や材料（例: おにぎり、梅干し、隠し味）

テキスト:
---
{text_chunk}
---
出力は「単語: 正しいひらがな読み」のJSON形式のみにしてください。
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "あなたはプロの小説校正者です。"},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ 解析中にエラー（スキップします）: {e}")
        return {}

def generate_corrections_v2(text_path):
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    with open(text_path, 'r', encoding='utf-8') as f:
        full_text = f.read()

    # 全文をスキャンし、重要な品詞をJanomeで先に絞り込むのも良いが、
    # ここでは「全文から主要なトークンをAIに抽出させる」方式をとる
    # 文量が多い場合は、先頭、中間、末尾からサンプリング
    text_samples = []
    chunk_size = 2000
    text_samples.append(full_text[:chunk_size]) # 開始
    if len(full_text) > chunk_size * 2:
        text_samples.append(full_text[len(full_text)//2 : len(full_text)//2 + chunk_size]) # 中間
    if len(full_text) > chunk_size * 3:
        text_samples.append(full_text[-chunk_size:]) # 末尾

    all_corrections = {}
    print(f"🔍 全文ディープスキャン中...")
    for i, sample in enumerate(text_samples):
        print(f"   サンプル {i+1} を解析中...")
        res = get_text_analysis_from_ai(client, sample)
        all_corrections.update(res)

    # 数字の特殊読みを補完（正規表現で自動抽出）
    # 例: 10日 -> とおか
    numbers_found = re.findall(r'\d+[年月日日人歳倍回分秒]', full_text)
    if numbers_found:
        print(f"🔢 数字表現を補完中...")
        num_prompt = f"以下の表現の正しい読み（ひらがな）を教えてください: {', '.join(set(numbers_found))}"
        res = get_text_analysis_from_ai(client, num_prompt)
        all_corrections.update(res)

    # 保存
    filename_stem = Path(text_path).stem
    title = re.sub(r'^\d{8}_', '', filename_stem)
    yaml_data = {
        "title": title,
        "category": "現実世界[恋愛]",
        "original_date": filename_stem.split('_')[0] if '_' in filename_stem else "",
        "corrections": all_corrections
    }
    
    yaml_path = Path(text_path).with_suffix('.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    print(f"✨ 最強辞書が完成しました: {yaml_path}")
    print(f"   登録単語数: {len(all_corrections)}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_corrections_v2(sys.argv[1])
    else:
        print("使い方: python generate_corrections.py novels/小説ファイル.txt")

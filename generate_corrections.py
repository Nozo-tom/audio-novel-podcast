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
        print("❌ エラー: OPENAI_API_KEY が設定されていません。.env ファイルを確認してください。")
        return

    client = OpenAI(api_key=api_key)
    
    # テキスト読み込み（冒頭4000文字程度）
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            content = f.read(4000)
    except FileNotFoundError:
        print(f"❌ エラー: ファイルが見つかりません: {text_path}")
        return
    except UnicodeDecodeError:
        # 他のエンコーディングを試す
        try:
            with open(text_path, 'r', encoding='shift_jis') as f:
                content = f.read(4000)
        except:
            print(f"❌ エラー: ファイルの読み込みに失敗しました。UTF-8で保存してください。")
            return

    print(f"🔍 AI解析中: {Path(text_path).name} ...")
    
    prompt = f"""
以下の小説の冒頭を読み、TTS（音声合成）が読み間違えそうな「人名」「地名」「特殊な用語」「数字の読み（単位含む）」を抽出し、
{{ "元の表記": "ひらがなでの読み" }} の形式で辞書を作ってください。

【特に注意する点】
- 苗字と名前の組み合わせ（例: 田村美咲 → たむらみさき）
- 異世界もの特有のカタカナ名や造語
- 数字の読み間違い（例: 10歳 → じゅっさい, 25歳 → にじゅうごさい）
- 文脈で読みが変わる漢字（例: 一人暮らし → ひとりぐらし）
- 料理名や材料名

小説の冒頭:
---
{content}
---
出力は純粋なJSON形式（{{ "単語": "よみ" }}）のみにしてください。
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "あなたは小説の校正者です。TTS読み上げのための読み替え辞書をJSON形式で作成します。"},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        
        corrections_json = response.choices[0].message.content
        corrections = json.loads(corrections_json)
        
        # YAMLデータの作成
        # ファイル名から日付等のプレフィックスを除去（例: 20250915_タイトル.txt -> タイトル）
        filename_stem = Path(text_path).stem
        title = re.sub(r'^\d{8}_', '', filename_stem)
        
        yaml_data = {
            "title": title,
            "category": "現実世界[恋愛]", # デフォルト値（必要に応じてAIに判定させることも可能）
            "original_date": filename_stem.split('_')[0] if '_' in filename_stem else "",
            "corrections": corrections
        }
        
        # 保存先：小説と同じフォルダの .yaml
        yaml_path = Path(text_path).with_suffix('.yaml')
        
        # すでにファイルがある場合は、correctionsをマージするか検討（今回は上書き保存）
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
        print(f"✅ 辞書を自動生成・保存しました: {yaml_path}")
        print("\n--- 抽出された読み替え ---")
        for word, reading in corrections.items():
            print(f"   - {word}: {reading}")
            
    except Exception as e:
        print(f"❌ AI解析中にエラーが発生しました: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        generate_corrections(sys.argv[1])
    else:
        print("使い方: python generate_corrections.py novels/小説ファイル.txt")

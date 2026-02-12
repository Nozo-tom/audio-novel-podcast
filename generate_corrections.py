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

    print(f"🔍 AIディープ解析中: {Path(text_path).name} ...")
    
    prompt = f"""
以下の小説テキストを詳細に解析し、TTS（音声合成）が読み間違えそうな全ての語句を抽出し、
{{ "元の表記": "正しい読みのひらがな" }} の形式で辞書を作ってください。

【最重要：読み間違いを根絶するための特別指示】
以下の語句は、AIが文脈を読み間違えて不自然な読み（例:肉親を「にくおや」など）をすることがあるため、必ず辞書に含めて「正解のひらがな」を指定してください：
1. 本来「音読み」すべき熟語や、一文字ずつ読まれやすい語句（例: 肉親 -> にくしん, 宝物 -> たからもの, 無事 -> ぶじ, 今朝 -> けさ, 男の子 -> おとこのこ）
2. 登場人物の名前（田村美咲 -> たむらみさき, リオ -> りお など）
3. 年齢や時間、単位（25歳 -> にじゅうごさい, 三ヶ月 -> さんかげつ, 10歳 -> jじゅっさい）
4. 異世界特有の用語、料理名、材料名

テキスト:
---
{{content}}
---
出力はJSON形式（{{ "単語": "よみ" }}）のみにしてください。
""".replace("{{content}}", content)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "あなたは小説の校正者です。TTS読み上げのための読み替え辞書をJSON形式で作成します。"},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        
        corrections_json = response.choices[0].message.content
        corrections = json.loads(corrections_json)
        
        # ファイル名からタイトルを抽出
        filename_stem = Path(text_path).stem
        title = re.sub(r'^\d{8}_', '', filename_stem)
        
        # 性別・音声判定の追加
        gender_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "小説の冒頭を読み、主人公の性別を判定してください。'male' か 'female' か 'unknown' で答えてください。"},
                      {"role": "user", "content": f"小説冒頭:\n---\n{content[:1000]}"}],
            response_format={ "type": "text" }
        )
        gender = gender_res.choices[0].message.content.strip().lower()
        
        # 性別に基づいたデフォルト音声の提案
        suggested_voice = "nova" if "female" in gender else "fable"
        print(f"👤 主人公の性別判定: {gender} -> 推奨音声: {suggested_voice}")

        yaml_data = {
            "title": title,
            "category": "現実世界[恋愛]",
            "voice": suggested_voice,
            "original_date": filename_stem.split('_')[0] if '_' in filename_stem else "",
            "corrections": corrections
        }
        
        # 保存先：小説と同じフォルダの .yaml
        yaml_path = Path(text_path).with_suffix('.yaml')
        
        # 保存
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
        generate_corrections(text_path=sys.argv[1])
    else:
        print("使い方: python generate_corrections.py novels/小説ファイル.txt")

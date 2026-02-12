import os
import json
import yaml
import sys
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

def sync_from_report(yaml_path):
    report_path = Path("reading_errors_report.txt")
    if not report_path.exists():
        print("❌ レポートファイルが見つかりません。")
        return

    print(f"🔄 レポートを解析して {yaml_path} を自動修正します...")
    
    with open(report_path, "r", encoding="utf-8") as f:
        report_content = f.read()

    client = OpenAI()
    
    # 差分が多い場合のため、重要な箇所を抽出
    prompt = f"""
以下の「TTS読み間違いレポート」を解析し、実際に読み上げミスが発生している「語句」とその「正しい読み（ひらがな）」を抽出してください。
「一致率」が低いものは特に重要です。

【注意】
- 「18歳」が「18さい」になっているなど、数字の書き換えは無視して良いです。
- 「花音」が「ハナオテ」となっている場合、「花音: かのん」のように修正してください。

レポート内容:
---
{report_content[:8000]} 
---
出力はJSON形式 {{ "単語": "正しいよみ" }} のみにしてください。
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    new_data = json.loads(response.choices[0].message.content)

    if os.path.exists(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        if "corrections" not in data:
            data["corrections"] = {}
        
        data["corrections"].update(new_data)
        
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
        
        print(f"✅ {len(new_data)}件の修正を反映しました。")
    else:
        print("❌ YAMLファイルが見つかりません。")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        sync_from_report(sys.argv[1])
    else:
        print("使い方: python fix_corrections.py novels/小説.yaml")

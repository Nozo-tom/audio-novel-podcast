"""
読み間違いレポート + 原文テキストから辞書を自動補強するツール

【アプローチ】
  1. 読み間違いレポート（原文 vs Whisper認識結果）を解析
  2. 原文テキストも読み込み、差異箇所の前後の文脈を取得
  3. GPT-4oに「原文の漢字語句」「差異箇所の文脈」を送り、
     正確な読みを長い文言で辞書登録する
  4. バリデーション: 登録キーが原文に実在するか検証

【使い方】
  python fix_corrections_from_report.py novel.yaml --report report.txt --text novel.txt
  python fix_corrections_from_report.py novel.yaml --report report.txt
"""
import os
import json
import re
import yaml
import sys
import argparse
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Windows対応: UTF-8出力設定
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# スクリプト自身のディレクトリ
SCRIPT_DIR = Path(__file__).parent


def parse_report(report_content):
    """レポートから差異情報を構造化して抽出"""
    differences = []
    current = {}
    
    for line in report_content.split('\n'):
        line = line.strip()
        
        # 差異ヘッダ: 【1】チャンク 3 (一致率: 45.2%)
        match = re.match(r'【(\d+)】.*一致率:\s*([\d.]+)%', line)
        if match:
            if current:
                differences.append(current)
            current = {
                'num': int(match.group(1)),
                'ratio': float(match.group(2)),
                'original': '',
                'transcribed': ''
            }
            continue
        
        if line.startswith('原文:'):
            current['original'] = line[len('原文:'):].strip()
        elif line.startswith('認識:'):
            current['transcribed'] = line[len('認識:'):].strip()
    
    if current and current.get('original'):
        differences.append(current)
    
    return differences


def filter_meaningful_differences(differences):
    """意味のある差異のみをフィルタリング"""
    filtered = []
    
    for diff in differences:
        ratio = diff['ratio']
        orig = diff['original']
        trans = diff['transcribed']
        
        # 一致率が98%以上は無視（ほぼ一致）
        if ratio >= 98:
            continue
        
        # 一致率が20%未満はチャンクずれの可能性が高いので除外
        if ratio < 20:
            continue
        
        # 原文が短すぎるものは除外
        if len(orig) < 3:
            continue
        
        filtered.append(diff)
    
    return filtered


def find_context_in_text(original_text, sentence, context_chars=100):
    """原文テキスト内で該当文の前後の文脈を取得"""
    # 句読点などを除いて検索
    search_text = sentence[:20]  # 先頭20文字で検索
    pos = original_text.find(search_text)
    
    if pos == -1:
        # 部分一致で再試行
        for length in range(15, 5, -1):
            search_text = sentence[:length]
            pos = original_text.find(search_text)
            if pos != -1:
                break
    
    if pos == -1:
        return sentence  # 見つからない場合はそのまま返す
    
    start = max(0, pos - context_chars)
    end = min(len(original_text), pos + len(sentence) + context_chars)
    return original_text[start:end]


def validate_corrections(corrections, original_text, existing_corrections):
    """辞書エントリのバリデーション"""
    validated = {}
    rejected = []
    
    for word, reading in corrections.items():
        # 値が文字列でない場合はスキップ
        if not isinstance(reading, str) or not isinstance(word, str):
            rejected.append((word, reading, "型が不正"))
            continue
        
        # 空のキーや値はスキップ
        if not word.strip() or not reading.strip():
            rejected.append((word, reading, "空文字"))
            continue
        
        # キーが原文に存在するか確認
        if word not in original_text:
            rejected.append((word, reading, "原文に存在しない"))
            continue
        
        # キーが1文字の場合は除外（部分一致リスク高すぎ）
        if len(word) == 1:
            rejected.append((word, reading, "1文字は部分一致リスク"))
            continue
        
        # 既に全く同じ登録がある場合はスキップ
        if word in existing_corrections and existing_corrections[word] == reading:
            continue
        
        # キーがひらがな・カタカナのみの場合は不要
        if re.match(r'^[ぁ-んァ-ヶー]+$', word):
            rejected.append((word, reading, "かな文字のみ（TTS読める）"))
            continue
        
        # 読み（値）が漢字を含む場合は除外（ひらがなであるべき）
        if re.search(r'[一-龥]', reading):
            rejected.append((word, reading, "読みに漢字が含まれる"))
            continue
        
        # キーに漢字が含まれていない場合は不要
        if not re.search(r'[一-龥]', word):
            rejected.append((word, reading, "キーに漢字なし"))
            continue
        
        # キーに対して漢字の割合が低すぎる場合（文まるごとひらがな化を防止）
        kanji_count = len(re.findall(r'[一-龥]', word))
        if len(word) > 8 and kanji_count / len(word) < 0.2:
            rejected.append((word, reading, f"漢字率が低い({kanji_count}/{len(word)}) → 不要な長文"))
            continue
        
        # 値が全てひらがなで、キーの長さが15文字超 → 文まるごとひらがな化
        if len(word) > 15 and re.match(r'^[ぁ-んー、。！？\s]+$', reading):
            rejected.append((word, reading, "文まるごとひらがな化は禁止"))
            continue
        
        validated[word] = reading
    
    return validated, rejected


def sync_from_report(yaml_path, report_path=None, text_path=None):
    """読み間違いレポートを解析してYAML辞書を自動補強する"""
    
    # レポートパスの解決
    if report_path:
        report_path = Path(report_path)
    else:
        candidate = SCRIPT_DIR / "reading_errors_report.txt"
        if candidate.exists():
            report_path = candidate
        else:
            report_path = Path("reading_errors_report.txt")
    
    if not report_path.exists():
        print(f"❌ レポートファイルが見つかりません: {report_path}")
        print(f"   検索場所: {report_path.resolve()}")
        return
    
    print(f"🔄 レポートを解析して {yaml_path} を自動修正します...")
    print(f"   レポート: {report_path}")
    
    with open(report_path, "r", encoding="utf-8") as f:
        report_content = f.read()
    
    if not report_content.strip():
        print("⚠️ レポートファイルは空です。スキップします。")
        return
    
    # 原文テキストの読み込み
    original_text = ""
    if text_path:
        text_path = Path(text_path)
        if text_path.exists():
            with open(text_path, "r", encoding="utf-8") as f:
                original_text = f.read()
            print(f"   原文: {text_path.name} ({len(original_text):,}文字)")
    
    # 既存YAMLの読み込み
    existing_corrections = {}
    if os.path.exists(yaml_path):
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        existing_corrections = data.get("corrections", {})
        print(f"   既存辞書: {len(existing_corrections)}件")
    else:
        data = {}
    
    # レポートの解析
    differences = parse_report(report_content)
    print(f"   検出差異: {len(differences)}件")
    
    # 意味のある差異のみフィルタ
    meaningful = filter_meaningful_differences(differences)
    print(f"   有効差異: {len(meaningful)}件")
    
    if not meaningful:
        print("ℹ️ 修正が必要な差異が見つかりませんでした。")
        return
    
    # GPTに送信するデータを構築
    # 差異一覧（文脈付き）
    diff_entries = []
    for diff in meaningful:
        entry = {
            "原文": diff['original'],
            "Whisper認識結果": diff['transcribed'],
            "一致率": f"{diff['ratio']:.1f}%"
        }
        # 原文テキストがあれば文脈を追加
        if original_text:
            context = find_context_in_text(original_text, diff['original'])
            entry["前後の文脈"] = context
        diff_entries.append(entry)
    
    # 既存辞書の情報
    existing_list = "\n".join([f"  {k}: {v}" for k, v in existing_corrections.items()])
    
    client = OpenAI()
    
    prompt = f"""\
以下は日本語小説のTTS音声化で発生した「読み間違い」の差異一覧です。

あなたの仕事は、TTSが読み間違えた**漢字語句だけ**を特定し、正しいひらがな読みを出力することです。

【最重要ルール】
- キーは**読み間違えた漢字語句のみ**（2〜10文字程度）
- TTSが正しく読める部分は含めない
- 文まるごとをキーにするのは**絶対禁止**

【具体例】
✅ 正しい出力:
  "悪役令嬢": "あくやくれいじょう"
  "嫌がらせ": "いやがらせ"
  "微笑んだ": "ほほえんだ"
  "心の中で呟いた": "こころのなかでつぶやいた"

❌ 間違った出力:
  "私の名前はエリザベート": "わたしのなまえはえりざべーと"  ← 文まるごと禁止
  "お嬢様、お茶の時間です": "おじょうさま、おちゃのじかんです"  ← TTSは正しく読める
  "エリザベート": "えりざべーと"  ← カタカナはTTSが読める
  "王子": "おうじ"  ← 一般的な漢字はTTSが読める

【登録不要なもの】
- カタカナ語（リリアナ、エリザベート等）→ TTSは正しく読める
- 一般的な漢字（王子、魔法、転生、部屋、彼女等）→ TTSが正しく読める
- 句読点の有無だけの差異 → 読み間違いではない
- Whisperが文をまとめた差異 → チャンク境界の問題で読み間違いではない

【既存の辞書（重複登録しない）】
{existing_list[:2000]}

【差異一覧】
{json.dumps(diff_entries[:80], ensure_ascii=False, indent=2)}

出力はJSON形式 {{ "漢字語句": "ひらがなよみ" }} のみ。本当にTTSが間違えた箇所だけを厳選してください。
"""

    print(f"\n🤖 GPT-4oに{len(meaningful)}件の差異を分析依頼中...")
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        response_format={ "type": "json_object" }
    )
    
    new_data = json.loads(response.choices[0].message.content)
    
    if not new_data:
        print("ℹ️ GPTから修正候補が返されませんでした。")
        return
    
    print(f"📋 GPTから{len(new_data)}件の候補を受信")
    
    # バリデーション
    if original_text:
        validated, rejected = validate_corrections(new_data, original_text, existing_corrections)
        
        if rejected:
            print(f"\n⚠️ {len(rejected)}件をバリデーションで除外:")
            for word, reading, reason in rejected:
                print(f"   ❌ {word}: {reading} → {reason}")
    else:
        # 原文がない場合はバリデーション簡易版
        validated = {k: v for k, v in new_data.items() 
                     if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip()}
        rejected = []
    
    if not validated:
        print("ℹ️ バリデーション後、有効な修正候補がありません。")
        return
    
    # 表示
    print(f"\n✅ {len(validated)}件の修正を適用:")
    for word, reading in validated.items():
        print(f"   📖 {word} → {reading}")
    
    # YAML更新
    if "corrections" not in data:
        data["corrections"] = {}
    
    data["corrections"].update(validated)
    
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    print(f"\n✅ {len(validated)}件の修正を {yaml_path} に反映しました。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="読み間違いレポートから辞書を自動補強")
    parser.add_argument("yaml_path", help="修正対象のYAMLファイルパス")
    parser.add_argument("--report", help="レポートファイルのパス（省略時はスクリプトディレクトリから検索）")
    parser.add_argument("--text", help="原文テキストファイルのパス（バリデーション用）")
    args = parser.parse_args()
    
    sync_from_report(args.yaml_path, args.report, args.text)

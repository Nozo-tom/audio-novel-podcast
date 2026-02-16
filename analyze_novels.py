#!/usr/bin/env python3
"""
全小説テキスト解析 → 主人公名・頻出語抽出 → TTS読み上げチェック → グローバル辞書登録
"""

import os
import re
import sys
import io
import json
import yaml
import time
import concurrent.futures

# Windows環境でUTF-8出力を強制
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from collections import Counter, defaultdict
from pathlib import Path
from janome.tokenizer import Tokenizer
from dotenv import load_dotenv

# .env からAPIキーをロード
load_dotenv()

# OpenAI
from openai import OpenAI

# ─── 設定 ───────────────────────────────────────────────
NOVEL_DIR = Path("novle_input")
CONFIG_PATH = Path("config.yaml")
OUTPUT_REPORT = Path("novel_analysis_report.txt")
BATCH_SIZE = 50  # GPTに一度に送る語数
MIN_FREQUENCY = 2  # この回数以上出現した語を対象
MAX_WORKERS = 4  # 並列処理数

# ─── Janome トークナイザ ─────────────────────────────────
tokenizer = Tokenizer()

# ─── OpenAI クライアント ─────────────────────────────────
client = OpenAI()


def load_config():
    """config.yaml を読み込む"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_existing_corrections():
    """既存の辞書エントリを取得（config.yaml + 個別YAML）"""
    config = load_config()
    corrections = dict(config.get("reading_corrections", {}) or {})
    
    # 個別YAMLからも収集
    for yaml_file in NOVEL_DIR.glob("*.yaml"):
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "corrections" in data and data["corrections"]:
                corrections.update(data["corrections"])
        except Exception:
            pass
    
    return corrections


def load_all_novels():
    """全小説テキストを読み込む"""
    novels = {}
    txt_files = sorted(NOVEL_DIR.glob("*.txt"))
    
    if not txt_files:
        print("❌ novle_input/ にテキストファイルがありません")
        sys.exit(1)
    
    print(f"📚 {len(txt_files)} 件の小説を読み込み中...")
    
    for i, txt_file in enumerate(txt_files, 1):
        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                content = f.read()
            novels[txt_file.name] = content
            # 進行度表示
            bar = "█" * (i * 30 // len(txt_files)) + "░" * (30 - i * 30 // len(txt_files))
            print(f"\r  [{bar}] {i}/{len(txt_files)} 読込完了", end="", flush=True)
        except Exception as e:
            print(f"\n  ⚠️ {txt_file.name}: {e}")
    
    print()
    return novels


def extract_character_names_from_text(text):
    """テキストから「」内の話者やキャラクター名っぽいパターンを抽出"""
    names = []
    
    # 「◯◯は言った」「◯◯が叫んだ」パターン
    patterns = [
        r'([一-龥ぁ-んァ-ヶー]{2,6})[はがもの](?:言|叫|呟|囁|答|尋|聞|話|笑|泣|怒|驚)',
        r'「[^」]*」\s*(?:と|って)[、。]?\s*([一-龥ぁ-んァ-ヶー]{2,6})',
        r'([一-龥ぁ-んァ-ヶー]{2,6})(?:さん|くん|ちゃん|様|殿|先生|先輩|後輩|王子|姫|公爵|伯爵|男爵|騎士)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        names.extend(matches)
    
    return names


def analyze_with_janome(text):
    """Janomeで形態素解析して名詞を抽出"""
    results = {
        "proper_nouns": [],      # 固有名詞
        "person_names": [],      # 人名
        "general_nouns": [],     # 一般名詞（漢字含む）
        "compound_words": [],    # サ変接続
    }
    
    tokens = tokenizer.tokenize(text)
    
    for token in tokens:
        surface = token.surface
        part_of_speech = token.part_of_speech.split(",")
        reading = token.reading if token.reading != "*" else None
        
        # 1文字は除外
        if len(surface) <= 1:
            continue
        
        # ひらがな・カタカナのみは除外
        if re.match(r'^[ぁ-んァ-ヶー]+$', surface):
            continue
        
        pos_main = part_of_speech[0]
        pos_sub = part_of_speech[1] if len(part_of_speech) > 1 else ""
        
        if pos_main == "名詞":
            if pos_sub == "固有名詞":
                results["proper_nouns"].append(surface)
            elif pos_sub in ("一般", "サ変接続", "形容動詞語幹"):
                # 漢字を含むもののみ
                if re.search(r'[一-龥]', surface):
                    results["general_nouns"].append(surface)
    
    return results


def analyze_all_novels(novels):
    """全小説を解析して頻出語を集計"""
    print("\n🔍 形態素解析中...")
    
    all_proper_nouns = Counter()
    all_general_nouns = Counter()
    all_character_names = Counter()
    novel_appearances = defaultdict(set)  # 語 → 出現した小説のセット
    
    total = len(novels)
    
    for i, (filename, text) in enumerate(novels.items(), 1):
        bar = "█" * (i * 30 // total) + "░" * (30 - i * 30 // total)
        print(f"\r  [{bar}] {i}/{total} 解析中: {filename[:30]}...", end="", flush=True)
        
        # Janome解析
        results = analyze_with_janome(text)
        
        for word in results["proper_nouns"]:
            all_proper_nouns[word] += 1
            novel_appearances[word].add(filename)
        
        for word in results["general_nouns"]:
            all_general_nouns[word] += 1
            novel_appearances[word].add(filename)
        
        # キャラクター名パターン抽出
        char_names = extract_character_names_from_text(text)
        for name in char_names:
            all_character_names[name] += 1
            novel_appearances[name].add(filename)
    
    print()
    return all_proper_nouns, all_general_nouns, all_character_names, novel_appearances


def check_readability_batch(words, existing_corrections):
    """GPTで一括して読みづらい語をチェック"""
    
    # 既存辞書にあるものは除外
    words_to_check = [w for w in words if w not in existing_corrections]
    
    if not words_to_check:
        return {}
    
    prompt = f"""以下は日本語の小説でよく使われる単語リストです。
    
OpenAI TTS（テキスト読み上げ）で読み間違えやすい単語を特定してください。

判定基準:
1. **人名・キャラクター名**: 漢字の名前は必ず読みが必要（例: 蒼真→そうま）
2. **難読漢字**: 一般的でない読みの語（例: 俯いた→うつむいた）
3. **複数の読み方がある語**: 文脈で読みが変わるもの（例: 流行る→はやる）
4. **ファンタジー用語**: 異世界・魔法系の独特な用語
5. **複合語**: 個別の読みで問題ない語は除外してOK

以下の単語を判定してください:
{json.dumps(words_to_check, ensure_ascii=False, indent=2)}

読み間違えやすいものだけをJSON形式で返してください。
読み間違えない一般的な語（例: 世界、時間、魔法、勇者、能力 etc.）は含めないでください。
特に人名は必ず含めてください。

出力形式（JSONのみ、他の文字なし）:
{{"蒼真": "そうま", "花音": "かのん", "俯いた": "うつむいた"}}

読み間違えやすいものが無ければ空のJSON {{}} を返してください。"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたはTTS（テキスト読み上げ）の専門家です。日本語のTTSが読み間違えやすい単語を判定します。JSON形式で回答してください。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    
    except Exception as e:
        print(f"\n  ⚠️ GPTエラー: {e}")
        return {}


def check_all_words(all_words, existing_corrections):
    """全単語をバッチでGPTチェック"""
    print("\n🤖 GPTで読み上げチェック中...")
    
    words_list = list(all_words)
    total_batches = (len(words_list) + BATCH_SIZE - 1) // BATCH_SIZE
    all_problematic = {}
    
    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(words_list))
        batch = words_list[start:end]
        
        bar = "█" * ((batch_idx + 1) * 30 // total_batches) + "░" * (30 - (batch_idx + 1) * 30 // total_batches)
        print(f"\r  [{bar}] バッチ {batch_idx + 1}/{total_batches} ({start}-{end}/{len(words_list)})", end="", flush=True)
        
        result = check_readability_batch(batch, existing_corrections)
        all_problematic.update(result)
        
        # レート制限対策
        time.sleep(0.5)
    
    print()
    return all_problematic


def update_global_dictionary(new_corrections):
    """config.yaml のグローバル辞書に追加"""
    if not new_corrections:
        print("\n✅ 追加すべき語はありませんでした")
        return
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    
    # reading_corrections セクションの末尾に追加
    additions = "\n  # 🔍 自動解析で追加された読み替え\n"
    for word, reading in sorted(new_corrections.items()):
        additions += f'  "{word}": "{reading}"\n'
    
    # reading_corrections セクションの末尾を見つけて追加
    # 最後の行の後に追加
    lines = content.split("\n")
    insert_idx = len(lines)
    
    # reading_corrections セクション内の最後のエントリを見つける
    in_corrections = False
    last_correction_idx = -1
    for i, line in enumerate(lines):
        if "reading_corrections:" in line:
            in_corrections = True
            continue
        if in_corrections:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                if ":" in stripped:
                    last_correction_idx = i
            # 次のトップレベルセクションに到達したら終了
            if stripped and not stripped.startswith("#") and not stripped.startswith('"') and not stripped.startswith("'") and ":" in stripped and not line.startswith("  "):
                break
    
    if last_correction_idx > 0:
        # 最後のエントリの後に挿入
        lines.insert(last_correction_idx + 1, additions.rstrip())
    else:
        # reading_corrections の直後に追加
        for i, line in enumerate(lines):
            if "reading_corrections:" in line:
                lines.insert(i + 1, additions.rstrip())
                break
    
    new_content = "\n".join(lines)
    
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)
    
    print(f"\n✅ config.yaml に {len(new_corrections)} 件の読み替えを追加しました")


def generate_report(proper_nouns, general_nouns, character_names, 
                    novel_appearances, problematic_words, existing_corrections):
    """解析レポートを生成"""
    report = []
    report.append("=" * 70)
    report.append("📊 全小説テキスト解析レポート")
    report.append("=" * 70)
    report.append("")
    
    # 主人公・キャラクター名候補
    report.append("─" * 70)
    report.append("👤 キャラクター名候補（出現頻度TOP50）")
    report.append("─" * 70)
    
    # 固有名詞 + キャラクター名パターンを統合
    combined_names = Counter()
    for name, count in proper_nouns.items():
        if re.search(r'[一-龥]', name) and 2 <= len(name) <= 6:
            combined_names[name] += count
    for name, count in character_names.items():
        combined_names[name] += count
    
    for word, count in combined_names.most_common(50):
        novels = novel_appearances.get(word, set())
        in_dict = "✅辞書" if word in existing_corrections else ""
        report.append(f"  {word:12s} (出現{count:4d}回, {len(novels):2d}作品) {in_dict}")
    
    report.append("")
    
    # 頻出一般名詞（漢字含む）
    report.append("─" * 70)
    report.append("📝 頻出一般名詞TOP50（漢字を含む）")
    report.append("─" * 70)
    
    for word, count in general_nouns.most_common(50):
        novels = novel_appearances.get(word, set())
        in_dict = "✅辞書" if word in existing_corrections else ""
        report.append(f"  {word:12s} (出現{count:4d}回, {len(novels):2d}作品) {in_dict}")
    
    report.append("")
    
    # TTS読み間違えやすい語
    report.append("─" * 70)
    report.append("⚠️ TTS読み間違えリスク語（GPT判定）")
    report.append("─" * 70)
    
    if problematic_words:
        for word, reading in sorted(problematic_words.items()):
            already = "（既存）" if word in existing_corrections else "🆕 新規追加"
            report.append(f"  {word} → {reading}  {already}")
    else:
        report.append("  （なし）")
    
    report.append("")
    report.append("=" * 70)
    
    report_text = "\n".join(report)
    
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(f"\n📄 レポート保存: {OUTPUT_REPORT}")
    return report_text


def main():
    print("=" * 60)
    print("🔍 全小説テキスト解析 → グローバル辞書更新")
    print("=" * 60)
    
    # 1. 既存辞書の読み込み
    print("\n📖 既存辞書を読み込み中...")
    existing_corrections = load_existing_corrections()
    print(f"  既存エントリ: {len(existing_corrections)} 件")
    
    # 2. 全小説テキストの読み込み
    novels = load_all_novels()
    total_chars = sum(len(text) for text in novels.values())
    print(f"  合計文字数: {total_chars:,} 文字")
    
    # 3. 形態素解析
    proper_nouns, general_nouns, character_names, novel_appearances = analyze_all_novels(novels)
    
    print(f"\n  📊 集計結果:")
    print(f"    固有名詞（ユニーク）: {len(proper_nouns)} 語")
    print(f"    一般名詞（ユニーク）: {len(general_nouns)} 語")
    print(f"    キャラ名候補: {len(character_names)} 語")
    
    # 4. チェック対象をフィルタ
    # 頻度が高い or 人名っぽい語を集める
    words_to_check = set()
    
    # 固有名詞は全部チェック（2回以上出現）
    for word, count in proper_nouns.items():
        if count >= MIN_FREQUENCY and re.search(r'[一-龥]', word):
            words_to_check.add(word)
    
    # キャラクター名候補は全部チェック
    for word, count in character_names.items():
        if count >= MIN_FREQUENCY and re.search(r'[一-龥]', word):
            words_to_check.add(word)
    
    # 一般名詞は頻出上位200語
    for word, _ in general_nouns.most_common(200):
        if re.search(r'[一-龥]', word):
            words_to_check.add(word)
    
    # 既存辞書にあるものを除外
    words_to_check -= set(existing_corrections.keys())
    
    print(f"\n  🎯 GPTチェック対象: {len(words_to_check)} 語（既存辞書除外済み）")
    
    # 5. GPTで読みチェック
    problematic_words = check_all_words(words_to_check, existing_corrections)
    
    print(f"\n  ⚠️ 読み間違えリスク語: {len(problematic_words)} 件")
    
    # 6. レポート生成
    report = generate_report(
        proper_nouns, general_nouns, character_names,
        novel_appearances, problematic_words, existing_corrections
    )
    print(report)
    
    # 7. グローバル辞書更新確認
    new_words = {k: v for k, v in problematic_words.items() if k not in existing_corrections}
    
    if new_words:
        print(f"\n🆕 新規追加候補: {len(new_words)} 件")
        for word, reading in sorted(new_words.items()):
            print(f"  {word} → {reading}")
        
        print(f"\n💾 config.yaml に追加しますか？ (y/n): ", end="", flush=True)
        answer = input().strip().lower()
        
        if answer == "y":
            update_global_dictionary(new_words)
        else:
            print("⏭️ スキップしました")
    else:
        print("\n✅ 新規追加すべき語はありませんでした")
    
    print("\n🏁 完了！")


if __name__ == "__main__":
    main()

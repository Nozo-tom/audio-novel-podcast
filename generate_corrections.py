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


def get_text_analysis_from_ai(client, text_chunk, model="gpt-4o-mini"):
    """テキストチャンクから読み間違いそうな単語をAIに抽出させる"""
    prompt = f"""
以下の小説テキストを解析し、TTS（音声合成）が読み間違えそうな**漢字語句**を抽出してください。

【抽出すべきもの】
1. 人名（佐藤美咲→さとうみさき、蒼真→そうま 等）
2. 地名・施設名（王立魔法学園→おうりつまほうがくえん 等）
3. 文脈で読みが変わる漢字（一人→ひとり、今日→きょう 等）
4. TTSが間違えそうな熟語（嫌がらせ→いやがらせ、嫉妬→しっと 等）

【絶対に登録しないでください】
- カタカナ語（リリアナ、エリザベート、ティーカップ等）→ TTSは正しく読める
- ひらがな語 → 変換不要
- 一般的な漢字（学園、魔法、転生、王子、部屋、彼女、完璧 等）→ TTSが正しく読める
- 数字（二年生、三ヶ月等）→ TTSが正しく読める
- 句読点や記号を含むフレーズ

【出力ルール】
- キーは原文テキストに存在する漢字語句そのまま（2文字以上）
- 値はひらがなのみ（カタカナや漢字を含まない）
- 本当にTTSが間違えそうなものだけに厳選（10〜20件程度）

テキスト:
---
{text_chunk}
---
出力はJSON形式 {{ "漢字語句": "ひらがなよみ" }} のみにしてください。
"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": "あなたはTTS読み間違い防止の専門家です。本当に間違えそうなものだけを厳選してください。"},
                      {"role": "user", "content": prompt}],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ 解析中にエラー（スキップします）: {e}")
        return {}


def generate_corrections(text_path, mode="deep"):
    """
    読み替え辞書を自動生成する。
    
    mode:
        "basic" - 先頭6000文字のみスキャン（高速・低コスト）
        "deep"  - 先頭・中間・末尾をサンプリング＋数字補完（高精度）
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY が設定されていません")
        return
    client = OpenAI(api_key=api_key)
    
    try:
        with open(text_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
    except Exception as e:
        print(f"❌ 読み込み失敗: {e}")
        return

    filename_stem = Path(text_path).stem
    title = re.sub(r'^\d{8}_', '', filename_stem)
    
    print(f"🔍 読み替え辞書を作成中: {Path(text_path).name}")
    print(f"   モード: {'ディープスキャン' if mode == 'deep' else 'クイックスキャン'}")

    all_corrections = {}

    if mode == "basic":
        # --- basic モード: 先頭6000文字のみ（gpt-4o使用） ---
        content_sample = full_text[:6000]
        
        prompt = f"""
以下の小説テキストに登場する「すべての漢字を含む単語（熟語、固有名詞、一般名詞、動詞、形容詞など）」を漏らさず抽出し、
その正しい読み（ひらがな）をJSON形式でリスト化してください。

【抽出の最重要ルール】
1. 小説に出てくる全ての漢字熟語を対象にしてください。
2. 特に以下の語句はTTSが読み間違えやすいため、確実に入れてください：
   - 固有名詞（人名、地名、学校名など）
   - 数字と単位（17歳、280歳、1年間、4月、2年B組など）
   - 文脈で読みが変わる語句（昨日、今日、明日、今朝、十分など）
3. 活用語（動詞の送り仮名付きなど）も、読み間違いが懸念されるものは含めてください。

出力形式: JSON {{ "漢字": "ひらがな" }}

テキスト:
---
{content_sample}
---
"""
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "あなたはプロの校正者です。"},
                          {"role": "user", "content": prompt}],
                response_format={ "type": "json_object" }
            )
            all_corrections = json.loads(response.choices[0].message.content)
            print(f"   ✅ クイックスキャン完了: {len(all_corrections)}件")
        except Exception as e:
            print(f"❌ 解析エラー: {e}")
            return

    else:
        # --- deep モード: 複数箇所サンプリング（gpt-4o-mini使用） ---
        text_samples = []
        chunk_size = 2000
        text_samples.append(full_text[:chunk_size])  # 開始
        if len(full_text) > chunk_size * 2:
            text_samples.append(full_text[len(full_text)//2 : len(full_text)//2 + chunk_size])  # 中間
        if len(full_text) > chunk_size * 3:
            text_samples.append(full_text[-chunk_size:])  # 末尾

        print(f"   📊 {len(text_samples)}箇所をサンプリング")
        for i, sample in enumerate(text_samples):
            print(f"   ⏳ サンプル {i+1}/{len(text_samples)} を解析中...")
            res = get_text_analysis_from_ai(client, sample)
            all_corrections.update(res)
            print(f"      → {len(res)}件 抽出")

        print(f"   ✅ ディープスキャン完了: {len(all_corrections)}件")
    
    # ===== バリデーション: 不要エントリを除外 =====
    filtered = {}
    removed = 0
    for key, val in all_corrections.items():
        # キーか値が文字列でない → スキップ
        if not isinstance(key, str) or not isinstance(val, str):
            removed += 1
            continue
        # キーが1文字 → 部分一致リスクが高い
        if len(key) < 2:
            removed += 1
            continue
        # キーがカタカナのみ → TTSが正しく読める
        if re.match(r'^[\u30A0-\u30FFー・]+$', key):
            removed += 1
            continue
        # キーがひらがなのみ → 変換不要
        if re.match(r'^[\u3040-\u309F]+$', key):
            removed += 1
            continue
        # キーに漢字が含まれていない → 不要
        if not re.search(r'[\u4e00-\u9fa5]', key):
            removed += 1
            continue
        # 値に漢字が含まれている → ひらがな読みじゃない
        if re.search(r'[\u4e00-\u9fa5]', val):
            removed += 1
            continue
        # キーが原文に存在しない → 無効
        if key not in full_text:
            removed += 1
            continue
        filtered[key] = val
    
    if removed > 0:
        print(f"   🧹 {removed}件の不要エントリを除外 → {len(filtered)}件に絞り込み")
    all_corrections = filtered
    
    # ===== 性別判定 → 音声モデル推奨 =====
    print("   🎭 主人公の性別を判定中...")
    try:
        gender_res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """小説の主人公（語り手・一人称視点の人物）の性別を判定してください。

判定基準:
- 一人称が「俺」「僕」→ 男性
- 一人称が「あたし」「わたくし」→ 女性
- 一人称が「私」→ 文脈・名前・タイトルで判断
- タイトルに「令嬢」「姫」「乙女」「女体化」→ 女性の可能性が高い
- 名前（太郎、介、俊 = 男性 / 美咲、花、子 = 女性）
- 「お嬢様」と呼ばれている → 女性

回答は 'male' か 'female' の1語のみ。"""},
                {"role": "user", "content": f"タイトル: {title}\n\n{full_text[:2000]}"}
            ],
        )
        gender = gender_res.choices[0].message.content.strip().lower()
        
        if "female" in gender:
            suggested_voice = "nova"
            gender_label = "女性"
        elif "male" in gender:
            suggested_voice = "fable"
            gender_label = "男性"
        else:
            suggested_voice = "nova"
            gender_label = "女性"
        
        print(f"      → 主人公: {gender_label} → 推奨音声: {suggested_voice}")
    except Exception:
        suggested_voice = "fable"
        gender_label = "不明"
        print(f"      → 判定失敗、デフォルト音声: {suggested_voice}")

    # ===== YAML保存 =====
    yaml_data = {
        "title": title,
        "category": "現実世界[恋愛]",
        "voice": suggested_voice,
        "original_date": filename_stem.split('_')[0] if '_' in filename_stem else "",
        "corrections": all_corrections
    }
    
    yaml_path = Path(text_path).with_suffix('.yaml')
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump(yaml_data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    
    print(f"\n✨ 読み替え辞書が完成しました: {yaml_path}")
    print(f"   登録単語数: {len(all_corrections)}件")
    print(f"   推奨音声: {suggested_voice} ({gender_label}主人公)")
    print(f"   💡 音声を変更したい場合は YAML の voice を書き換えてください")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="📖 読み替え辞書自動生成ツール",
    )
    parser.add_argument("input", help="テキストファイルのパス")
    parser.add_argument("--mode", choices=["basic", "deep"], default="deep",
                        help="スキャンモード: basic(高速) / deep(高精度, デフォルト)")
    
    args = parser.parse_args()
    generate_corrections(args.input, mode=args.mode)

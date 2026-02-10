# =============================================================================
# 🔍 オフライン読み推定ツール
# APIを使わずに、「読み間違いの可能性」がある単語をリストアップ（Janome使用）
# =============================================================================

import os
import sys
from collections import Counter
from janome.tokenizer import Tokenizer

# Windows対応: UTF-8出力設定
sys.stdout.reconfigure(encoding='utf-8')

# 設定
INPUT_FILE = r"c:\Users\natak\Documents\Novel\ひより01_元 copy.txt"

# =============================================================================
# 初期化
# =============================================================================

print("\n" + "=" * 70)
print("🔍 オフライン読み推定ツール")
print("=" * 70)

if not os.path.exists(INPUT_FILE):
    print(f"❌ ファイルが見つかりません: {INPUT_FILE}")
    sys.exit(1)

# テキスト読み込み
try:
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        text = f.read()
    print(f"✅ ファイル読み込み成功: {len(text):,} 文字")
except UnicodeDecodeError:
    # UTF-8でダメならShift-JIS
    try:
        with open(INPUT_FILE, 'r', encoding='shift_jis') as f:
            text = f.read()
        print(f"✅ ファイル読み込み成功(Shift-JIS): {len(text):,} 文字")
    except:
        print("❌ ファイルの読み込みに失敗しました")
        sys.exit(1)

# Janome初期化
print("⏳ 解析中...")
t = Tokenizer()

# =============================================================================
# 解析処理
# =============================================================================

# 抽出したい品詞
TARGET_POS = ['名詞']
IGNORE_WORDS = ['こと', 'もの', 'よう', 'ため', 'やつ', 'これ', 'それ', 'あれ']

word_list = []
unknown_words = []

for token in t.tokenize(text):
    pos = token.part_of_speech.split(',')[0]
    sub_pos = token.part_of_speech.split(',')[1]
    
    if pos in TARGET_POS:
        surface = token.surface
        reading = token.reading
        
        # カタカナ、ひらがな、英数字のみの単語はスキップ（読み間違いにくい）
        if all(c in "ァ-ンーぁ-ん0-9a-zA-Z" for c in surface):
            continue
            
        # 無視リスト
        if surface in IGNORE_WORDS:
            continue
            
        # 固有名称（人名、地域、組織）は特に重要
        is_proper = (sub_pos == '固有名詞')
        
        # 読みが推定できない場合（未知語）
        if reading == '*':
            unknown_words.append(surface)
        else:
            word_list.append((surface, reading, is_proper))

# 集計
counter = Counter(word_list)
sorted_words = sorted(counter.items(), key=lambda x: (not x[0][2], -x[1])) # 固有名詞優先、頻度順

# =============================================================================
# 結果表示
# =============================================================================

print("\n" + "=" * 70)
print("🧐 読みチェックリスト（固有名詞・漢字語）")
print("  ※カタカナ読みがあなたの想定と違う場合は辞書に追加してください")
print("=" * 70)

print(f"{'単語':<12} | {'推定読み':<12} | {'回数':<4} | {'判定'}")
print("-" * 50)

lines_printed = 0
MAX_LINES = 100

for (word, reading, is_proper), count in sorted_words:
    # 漢字を含まないものはスキップ（再チェック）
    if all(c in "ァ-ンーぁ-ん0-9a-zA-Z" for c in word):
        continue
    
    # 1文字の名詞はノイズが多いのでスキップ（重要そうなものを除く）
    if len(word) == 1 and not is_proper:
        continue

    mark = "🔴" if is_proper else "  "
    print(f"{mark} {word:<10} | {reading:<12} | {count:<4} |")
    
    lines_printed += 1
    if lines_printed >= MAX_LINES:
        print(f"\n... 他 {len(sorted_words) - MAX_LINES} 語")
        break

if unknown_words:
    print("\n" + "=" * 70)
    print("⚠️ 読みが不明な単語 (辞書登録推奨)")
    print("=" * 70)
    for word, count in Counter(unknown_words).most_common(20):
         print(f"❓ {word} ({count}回)")

print("\n✔ 完了")

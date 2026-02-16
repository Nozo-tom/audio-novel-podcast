"""
小説テキストファイルのヘッダー（重複タイトル・区切り線）を一括削除するツール

【対象ヘッダー形式】
  1行目: タイトル
  2行目: ==================================================
  3-5行目: (空行)
  6行目: 第1話: タイトル
  7行目: ----------------------------------------
  ↑ ここまで削除。7行目の '----' の次の行から本文として残す。

【使い方】
  python cleanup_headers.py             # 実行（ファイルを上書き）
  python cleanup_headers.py --dry-run   # 確認のみ（変更なし）

【対象フォルダ】
  novle_input/ 内の全 .txt ファイル
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

SCRIPT_DIR = Path(__file__).parent
input_dir = SCRIPT_DIR / "novle_input"
dry_run = '--dry-run' in sys.argv

if dry_run:
    print("🔍 ドライラン（変更なし）\n")
else:
    print("🔧 ヘッダー削除を実行します\n")

count = 0
total = 0

for txt in sorted(input_dir.glob('*.txt')):
    total += 1
    with open(txt, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # ヘッダーパターンを探す: '----' で始まる行を見つけ、その次の行から本文
    header_end = None
    for i, line in enumerate(lines):
        if line.strip().startswith('----') and i >= 1:
            header_end = i + 1  # '----' の次の行が本文開始
            break

    if header_end is None or header_end >= len(lines):
        print(f'  スキップ: {txt.name} (ヘッダーなし)')
        continue

    old_len = len(lines)
    new_lines = lines[header_end:]
    new_len = len(new_lines)
    removed = old_len - new_len

    if removed > 0:
        print(f'  ✅ {txt.name}')
        print(f'     削除: {removed}行 (残り: {new_len}行)')
        if not dry_run:
            with open(txt, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
        count += 1

print(f'\n合計: {count}/{total} ファイル処理')

import csv
import pathlib
import re
import yaml
import sys

# 標準出力のエンコーディングを UTF-8 に強制（Windows対策）
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

csv_path = pathlib.Path('docs/novel to mp3 - ひより.csv')
output_dir = pathlib.Path('novels')
output_dir.mkdir(exist_ok=True)

with open(csv_path, 'r', encoding='utf-8', newline='') as f:
    reader = csv.reader(f, quotechar='"', delimiter=',', quoting=csv.QUOTE_MINIMAL)
    
    try:
        header = next(reader)
    except StopIteration:
        print("Error: CSV file is empty")
        sys.exit(1)
        
    count = 0
    for row in reader:
        if not row or len(row) < 3:
            continue
            
        full_date = row[0] 
        title = row[1]
        category = row[2]
        content = row[3] if len(row) >= 4 else ""
        
        if not content.strip():
            continue

        # 日付を "20250910" 形式に変換
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', full_date)
        date_str = date_match.group(1) + date_match.group(2) + date_match.group(3) if date_match else "00000000"
        
        # ファイル名を生成
        safe_title = sanitize_filename(title)
        if len(safe_title) > 30:
            safe_title = safe_title[:30]
        base_name = f"{date_str}_{safe_title}"
        
        # 1. 本文テキストの保存
        txt_path = output_dir / f"{base_name}.txt"
        txt_path.write_text(content, encoding='utf-8')
        
        # 2. 作品情報(YAML)の保存
        info_path = output_dir / f"{base_name}.yaml"
        info = {
            'title': title,
            'category': category,
            'original_date': full_date,
            'corrections': {}
        }
        with open(info_path, 'w', encoding='utf-8') as yf:
            yaml.dump(info, yf, allow_unicode=True, sort_keys=False)
            
        print(f"Processed: {base_name}")
        count += 1

print(f"\nCompleted: Created {count} documents.")

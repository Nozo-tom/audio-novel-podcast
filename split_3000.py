"""
小説テキストの冒頭3000文字だけを切り出して保存するスクリプト
"""
import os
import sys
import glob
import shutil

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = r"c:\Users\natak\Documents\Novel"
SOURCE_DIRS = [
    os.path.join(BASE_DIR, "novels", "completed"),
    os.path.join(BASE_DIR, "novels"),
    os.path.join(BASE_DIR, "novle_input"),
]
OUTPUT_DIR = os.path.join(BASE_DIR, "novels", "completed_3000ver")

CHUNK_SIZE = 3000

def extract_head(filepath, output_dir):
    """小説テキストの冒頭3000文字を切り出して保存"""
    basename = os.path.splitext(os.path.basename(filepath))[0]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    
    total_chars = len(text)
    head = text[:CHUNK_SIZE]
    
    out_filename = f"{basename}.txt"
    out_path = os.path.join(output_dir, out_filename)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(head)
    
    print(f"  {basename}")
    print(f"     {total_chars}文字 -> 冒頭{len(head)}文字を保存")

def main():
    # 出力ディレクトリをクリアして再作成
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)
    print(f"[出力先] {OUTPUT_DIR}\n")
    
    # 全ソースディレクトリから .txt を収集（重複排除）
    seen = set()
    all_files = []
    for src_dir in SOURCE_DIRS:
        if not os.path.exists(src_dir):
            continue
        for f in sorted(glob.glob(os.path.join(src_dir, "*.txt"))):
            basename = os.path.basename(f)
            if basename not in seen:
                seen.add(basename)
                all_files.append(f)
    
    all_files.sort(key=lambda f: os.path.basename(f))
    
    for filepath in all_files:
        extract_head(filepath, OUTPUT_DIR)
        print()
    
    print(f"[完了] {len(all_files)}作品の冒頭3000文字を保存しました")

if __name__ == "__main__":
    main()

import requests
from bs4 import BeautifulSoup
import time
import json
import re
from pathlib import Path

# download_novel.pyの関数をそのまま使ってテスト
from download_novel import get_author_novels, download_novel

output_dir = Path(r"c:\Users\natak\Documents\Novel\novle_input")

novels = get_author_novels("2955620")

# テスト: 2番目の作品(短編1話)をDL
novel = novels[1]
print(f"テスト対象: {novel['title']}")
print(f"  ncode={novel['ncode']} 話数={novel['general_all_no']}")

result = download_novel(
    novel['ncode'], novel['title'], novel['general_all_no'],
    novel.get('general_firstup', ''), output_dir
)

# 結果確認
if result and result.exists():
    size = result.stat().st_size
    with open(result, 'r', encoding='utf-8') as f:
        content = f.read()
    print(f"\nファイルサイズ: {size} bytes")
    print(f"行数: {len(content.splitlines())}")
    print(f"先頭100文字:\n{content[:200]}")

import requests
from bs4 import BeautifulSoup
import time
import json
import re
from pathlib import Path

def get_author_novels(user_id):
    """作者IDから作品一覧を取得"""
    # gf=general_firstup(初回掲載日)を追加
    api_url = f"https://api.syosetu.com/novelapi/api/?userid={user_id}&lim=500&out=json&of=t-n-s-ga-gf"
    
    try:
        response = requests.get(api_url)
        response.encoding = 'utf-8'
        novels = json.loads(response.text)
        
        if len(novels) < 2:
            print("作品が見つかりませんでした")
            return []
        
        return novels[1:]
    except Exception as e:
        print(f"API取得エラー: {e}")
        return []

def download_episode(ncode, episode_num, is_short=False):
    """指定したエピソードの本文を取得"""
    # 短編は /ncode/ 直接、連載は /ncode/ep/
    if is_short:
        url = f"https://ncode.syosetu.com/{ncode.lower()}/"
    else:
        url = f"https://ncode.syosetu.com/{ncode.lower()}/{episode_num}/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # サブタイトル取得
        subtitle_tag = soup.find('h1', class_='p-novel__title')
        if subtitle_tag:
            subtitle = subtitle_tag.text.strip()
        else:
            subtitle_tag = soup.find('p', class_='novel_subtitle')
            subtitle = subtitle_tag.text.strip() if subtitle_tag else f"第{episode_num}話"
        
        # 本文取得
        honbun_tag = soup.find('div', class_='js-novel-text')
        if not honbun_tag:
            honbun_tag = soup.find('div', id='novel_honbun')
        
        if not honbun_tag:
            return None, None
        
        paragraphs = []
        for p in honbun_tag.find_all('p'):
            text = p.get_text(strip=True)
            if text:
                paragraphs.append(text)
        
        honbun = '\n'.join(paragraphs)
        return subtitle, honbun
    except Exception as e:
        print(f"  エピソード{episode_num}取得エラー: {e}")
        return None, None

def safe_filename(title, max_len=60):
    """ファイル名に使えない文字を除去"""
    # Windowsで使えない文字を除去
    safe = re.sub(r'[\\/:*?"<>|]', '', title)
    safe = safe.strip()
    if len(safe) > max_len:
        safe = safe[:max_len]
    return safe

def download_novel(ncode, title, total_episodes, first_up, output_dir):
    """作品全体をダウンロード"""
    # 初回掲載日をYYYYMMDD形式に変換
    date_str = first_up.replace('-', '').replace(' ', '').split('T')[0][:8] if first_up else "00000000"
    # "2026-02-11 12:00:00" -> "20260211"
    date_str = re.sub(r'[^0-9]', '', first_up)[:8] if first_up else "00000000"
    
    fname = f"{date_str}_{safe_filename(title)}.txt"
    output_file = output_dir / fname
    
    # 既にDL済みで中身があるならスキップ
    if output_file.exists() and output_file.stat().st_size > 500:
        print(f"  [スキップ] 既にDL済み: {fname}")
        return output_file
    
    is_short = (total_episodes == 1)
    print(f"  DL開始: {fname} ({'短編' if is_short else str(total_episodes) + '話'})")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"{title}\n")
        f.write("=" * 50 + "\n\n")
        
        for ep_num in range(1, total_episodes + 1):
            subtitle, honbun = download_episode(ncode, ep_num, is_short=is_short)
            
            if honbun:
                f.write(f"\n\n第{ep_num}話: {subtitle}\n")
                f.write("-" * 40 + "\n")
                f.write(honbun + "\n")
                print(f"    [{ep_num}/{total_episodes}] {subtitle}")
            else:
                print(f"    [{ep_num}/{total_episodes}] 取得失敗")
            
            time.sleep(1)
    
    print(f"  [完了] {fname}")
    return output_file

def main():
    user_id = "2955620"
    output_dir = Path(r"c:\Users\natak\Documents\Novel\novle_input")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    print(f"作者ID {user_id} の作品一覧を取得中...")
    novels = get_author_novels(user_id)
    
    if not novels:
        return
    
    total = len(novels)
    print(f"\n全{total}作品を順次ダウンロードします\n")
    
    for i, novel in enumerate(novels, 1):
        title = novel.get('title', '不明')
        ncode = novel.get('ncode', '')
        story_count = novel.get('general_all_no', 0)
        first_up = novel.get('general_firstup', '')
        
        print(f"[{i}/{total}] {title}")
        download_novel(ncode, title, story_count, first_up, output_dir)

if __name__ == "__main__":
    main()

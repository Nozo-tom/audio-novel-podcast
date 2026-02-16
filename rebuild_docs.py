# =============================================================================
# 🔄 docs/ フォルダ一括再構築スクリプト
#
# mp3/ フォルダの完成版MP3から1分プレビューを作成し、
# png/ フォルダのカバー画像とともに docs/ に配置する。
#
# 命名規則:
#   MP3:  {日付}_{作品名先頭5文字}_preview.mp3
#   画像: {日付}_{作品名先頭5文字}.png (または .jpg)
#
# 使い方:
#   python rebuild_docs.py              # docs/ を再構築（確認あり）
#   python rebuild_docs.py --yes        # 確認なしで実行
#   python rebuild_docs.py --dry-run    # 実行せずに計画を表示
# =============================================================================

import os
import sys
import re
import json
import shutil
import hashlib
import argparse
import urllib.parse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Windows対応
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).parent
MP3_DIR = BASE_DIR / "mp3"
PNG_DIR = BASE_DIR / "png"
DOCS_DIR = BASE_DIR / "docs"
CONFIG_PATH = BASE_DIR / "config.yaml"

# =============================================================================
# ユーティリティ
# =============================================================================

def load_config():
    """config.yaml を読み込む"""
    try:
        import yaml
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"⚠️ config.yaml 読み込み失敗: {e}")
        return {}


def get_mp3_duration(filepath):
    """MP3ファイルの再生時間を秒で返す"""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(filepath)
        return len(audio) / 1000
    except Exception:
        return 0


def format_duration_itunes(seconds):
    """秒をiTunesフォーマット (HH:MM:SS) に変換"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def xml_escape(text):
    """XMLエスケープ"""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


def extract_date_prefix(filename):
    """ファイル名から日付プレフィックス(8桁)を抽出"""
    m = re.match(r'^(\d{8})_', filename)
    return m.group(1) if m else None


def extract_title_from_filename(filename):
    """ファイル名から作品タイトルを抽出（日付プレフィックスとタイムスタンプを除去）"""
    stem = Path(filename).stem
    # 日付プレフィックス除去
    title = re.sub(r'^\d{8}_', '', stem)
    # 末尾のタイムスタンプ除去 (_20260210_170946 のような部分)
    title = re.sub(r'_\d{8}_\d{4,6}$', '', title)
    # _preview サフィックス除去
    title = re.sub(r'_preview$', '', title)
    return title


def make_short_name(date_prefix, title, max_title_chars=5):
    """統一命名用のショート名を生成: {日付}_{作品名先頭N文字}"""
    short_title = title[:max_title_chars]
    return f"{date_prefix}_{short_title}"


# =============================================================================
# メイン処理
# =============================================================================

def find_best_mp3_per_group():
    """
    mp3/ フォルダ内のMP3を日付プレフィックスでグルーピングし、
    各グループの最新・最大ファイルを「完成版」として選定する。
    """
    if not MP3_DIR.exists():
        print("❌ mp3/ フォルダが見つかりません")
        return {}
    
    groups = defaultdict(list)
    
    for f in MP3_DIR.iterdir():
        if not f.suffix.lower() == '.mp3':
            continue
        date_prefix = extract_date_prefix(f.name)
        if not date_prefix:
            continue  # テストファイルなどはスキップ
        
        groups[date_prefix].append(f)
    
    best = {}
    for date_prefix, files in sorted(groups.items()):
        # 最も大きいファイルを完成版とみなす（フルバージョン）
        # サイズが同じ場合は最新のものを選ぶ
        largest = max(files, key=lambda f: (f.stat().st_size, f.stat().st_mtime))
        title = extract_title_from_filename(largest.name)
        best[date_prefix] = {
            'path': largest,
            'title': title,
            'size_mb': largest.stat().st_size / 1024 / 1024,
            'all_files': len(files),
        }
    
    return best


def find_cover_images():
    """
    png/ フォルダ内のカバー画像を日付プレフィックスで分類する。
    日付プレフィックスがないファイルも別途返す。
    """
    if not PNG_DIR.exists():
        print("❌ png/ フォルダが見つかりません")
        return {}, []
    
    covers = {}
    no_date = []
    
    for f in PNG_DIR.iterdir():
        if f.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            continue
        date_prefix = extract_date_prefix(f.name)
        if date_prefix:
            covers[date_prefix] = f
        else:
            no_date.append(f)
    
    return covers, no_date


def create_preview(mp3_path, output_path, duration_sec=60):
    """MP3から1分プレビューを作成"""
    from pydub import AudioSegment
    
    audio = AudioSegment.from_mp3(str(mp3_path))
    full_duration_ms = len(audio)
    preview_duration_ms = duration_sec * 1000
    
    if full_duration_ms > preview_duration_ms:
        preview = audio[:preview_duration_ms].fade_out(3000)
    else:
        preview = audio
    
    preview.export(str(output_path), format='mp3')
    return len(preview) / 1000  # 秒で返す


def rebuild_docs(dry_run=False):
    """docs/ フォルダを再構築する"""
    
    print("\n" + "=" * 70)
    print("  🔄 docs/ フォルダ再構築")
    print("=" * 70)
    
    # 1. 完成版MP3を探す
    print("\n📂 mp3/ フォルダをスキャン中...")
    best_mp3s = find_best_mp3_per_group()
    
    if not best_mp3s:
        print("❌ 処理対象のMP3が見つかりません")
        return
    
    # 2. カバー画像を探す
    print("🖼️ png/ フォルダをスキャン中...")
    cover_images, no_date_covers = find_cover_images()
    
    # 3. 計画を表示
    print("\n" + "─" * 70)
    print("  📋 再構築計画")
    print("─" * 70)
    
    episodes_plan = []
    
    for i, (date_prefix, mp3_info) in enumerate(sorted(best_mp3s.items()), 1):
        title = mp3_info['title']
        short_name = make_short_name(date_prefix, title)
        cover = cover_images.get(date_prefix)
        cover_ext = cover.suffix if cover else "(なし)"
        
        preview_name = f"{short_name}_preview.mp3"
        cover_name = f"{short_name}{cover_ext}" if cover else None
        
        plan = {
            'number': i,
            'date_prefix': date_prefix,
            'title': title,
            'short_name': short_name,
            'source_mp3': mp3_info['path'],
            'source_cover': cover,
            'preview_name': preview_name,
            'cover_name': cover_name,
            'size_mb': mp3_info['size_mb'],
            'all_files': mp3_info['all_files'],
        }
        episodes_plan.append(plan)
        
        cover_status = f"✅ {cover.name}" if cover else "❌ なし"
        print(f"\n  📖 EP{i}: {title}")
        print(f"     元MP3: {mp3_info['path'].name} ({mp3_info['size_mb']:.2f}MB, {mp3_info['all_files']}件中)")
        print(f"     → docs/{preview_name}")
        print(f"     カバー: {cover_status}")
        if cover_name:
            print(f"     → docs/{cover_name}")
    
    if no_date_covers:
        print(f"\n  ⚠️ 日付プレフィックスなしの画像: {[f.name for f in no_date_covers]}")
    
    print(f"\n  📊 合計: {len(episodes_plan)}エピソード")
    
    if dry_run:
        print("\n  🧪 ドライランのためここで終了します")
        return
    
    # 4. docs/ をクリーンアップ（MP3とエピソード画像を削除、cover.jpgは残す）
    print("\n" + "─" * 70)
    print("  🧹 docs/ をクリーンアップ中...")
    print("─" * 70)
    
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    
    keep_files = {'cover.jpg', 'novel to mp3 - ひより.csv'}  # 残すファイル
    
    for f in DOCS_DIR.iterdir():
        if f.name in keep_files:
            continue
        if f.suffix.lower() in ('.mp3', '.json', '.xml', '.png', '.jpg', '.jpeg'):
            print(f"  🗑️ 削除: {f.name}")
            f.unlink()
    
    # 5. プレビューMP3とカバー画像を生成・コピー
    print("\n" + "─" * 70)
    print("  🎵 プレビューMP3を生成中...")
    print("─" * 70)
    
    episodes_data = []
    total = len(episodes_plan)
    
    for i, plan in enumerate(episodes_plan, 1):
        pct = i / total * 100
        bar = "█" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
        print(f"\n  [{i}/{total}] {bar} {pct:.0f}%")
        print(f"  📖 {plan['title']}")
        
        # 1分プレビュー作成
        preview_path = DOCS_DIR / plan['preview_name']
        print(f"  ✂️ 1分プレビュー作成中... → {plan['preview_name']}")
        preview_duration = create_preview(plan['source_mp3'], preview_path)
        preview_size = preview_path.stat().st_size
        print(f"  ✅ {preview_duration:.0f}秒 ({preview_size/1024:.0f}KB)")
        
        # カバー画像コピー
        cover_filename_in_feed = None
        if plan['source_cover'] and plan['cover_name']:
            cover_dest = DOCS_DIR / plan['cover_name']
            shutil.copy2(str(plan['source_cover']), str(cover_dest))
            cover_filename_in_feed = plan['cover_name']
            print(f"  🖼️ カバー画像コピー → {plan['cover_name']}")
        else:
            print(f"  ⚠️ カバー画像なし")
        
        # エピソードデータ
        ep_data = {
            "number": plan['number'],
            "title": plan['title'],
            "description": f"「{plan['title']}」の音声版をお届けします。",
            "filename": plan['preview_name'],
            "cover_image": cover_filename_in_feed,
            "size": preview_size,
            "duration": preview_duration,
            "duration_formatted": format_duration_itunes(preview_duration),
            "pub_date": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0900"),
            "guid": hashlib.md5(f"{plan['title']}_{plan['preview_name']}".encode()).hexdigest(),
        }
        episodes_data.append(ep_data)
    
    # 6. episodes.json を保存
    print("\n" + "─" * 70)
    print("  📝 episodes.json を生成中...")
    print("─" * 70)
    
    episodes_json_path = DOCS_DIR / "episodes.json"
    with open(episodes_json_path, 'w', encoding='utf-8') as f:
        json.dump(episodes_data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {len(episodes_data)}エピソード保存")
    
    # 7. feed.xml を生成
    print("\n" + "─" * 70)
    print("  📡 feed.xml を生成中...")
    print("─" * 70)
    
    config = load_config()
    generate_feed_xml(config, episodes_data)
    
    # 8. 完了サマリー
    print("\n" + "=" * 70)
    print("  🎉 docs/ 再構築完了！")
    print("=" * 70)
    
    print(f"\n  📂 docs/ の内容:")
    for f in sorted(DOCS_DIR.iterdir()):
        size = f.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size/1024/1024:.2f}MB"
        else:
            size_str = f"{size/1024:.0f}KB"
        print(f"     {f.name} ({size_str})")
    
    print(f"\n  💡 次のステップ:")
    print(f"     git add docs/")
    print(f"     git commit -m 'Rebuild docs with preview MP3s and cover images'")
    print(f"     git push")


def generate_feed_xml(config, episodes_data):
    """feed.xml を生成"""
    
    podcast_config = config.get('podcast', {})
    output_config = config.get('output', {})
    
    channel_title = podcast_config.get('title', '音声小説チャンネル')
    channel_author = podcast_config.get('author', '制作チーム')
    channel_desc = podcast_config.get('description', 'オリジナル音声小説')
    channel_lang = podcast_config.get('language', 'ja')
    channel_category = podcast_config.get('category', 'Arts')
    channel_subcategory = podcast_config.get('subcategory', 'Books')
    channel_website = podcast_config.get('website', '')
    channel_email = podcast_config.get('email', '')
    cover_art = podcast_config.get('cover_art', 'cover.jpg')
    base_url = podcast_config.get('base_url', 'YOUR_HOSTING_URL_HERE')
    feed_filename = output_config.get('feed_filename', 'feed.xml')
    
    # エピソードXML
    items_xml = ""
    for ep in reversed(episodes_data):  # 新しい順
        # エピソード個別のカバー画像
        ep_image_xml = ""
        if ep.get('cover_image'):
            ep_image_xml = f'\n      <itunes:image href="{base_url}/{urllib.parse.quote(ep["cover_image"])}"/>'
        
        items_xml += f"""
    <item>
      <title>{xml_escape(ep['title'])}</title>
      <description>{xml_escape(ep['description'])}</description>
      <enclosure url="{base_url}/{urllib.parse.quote(ep['filename'])}" length="{ep['size']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{ep['guid']}</guid>
      <pubDate>{ep['pub_date']}</pubDate>
      <itunes:duration>{ep['duration_formatted']}</itunes:duration>
      <itunes:episode>{ep['number']}</itunes:episode>
      <itunes:explicit>false</itunes:explicit>{ep_image_xml}
    </item>"""
    
    # チャンネルカバー画像
    cover_xml = ""
    if cover_art:
        cover_xml = f'\n    <itunes:image href="{base_url}/{cover_art}"/>'
    
    # オーナー情報
    owner_xml = ""
    if channel_email:
        owner_xml = f"""
    <itunes:owner>
      <itunes:name>{xml_escape(channel_author)}</itunes:name>
      <itunes:email>{channel_email}</itunes:email>
    </itunes:owner>"""
    
    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{xml_escape(channel_title)}</title>
    <description>{xml_escape(channel_desc)}</description>
    <language>{channel_lang}</language>
    <itunes:author>{xml_escape(channel_author)}</itunes:author>{owner_xml}
    <itunes:category text="{channel_category}">
      <itunes:category text="{channel_subcategory}"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>{cover_xml}
    <link>{channel_website}</link>
    <atom:link href="{base_url}/{feed_filename}" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>"""
    
    feed_path = DOCS_DIR / feed_filename
    with open(feed_path, 'w', encoding='utf-8') as f:
        f.write(feed_xml)
    
    print(f"  ✅ feed.xml 生成完了 ({len(episodes_data)}エピソード)")


# =============================================================================
# エントリポイント
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="🔄 docs/ フォルダ一括再構築",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命名規則:
  MP3:  {日付}_{作品名先頭5文字}_preview.mp3
  画像: {日付}_{作品名先頭5文字}.png (または .jpg)

例:
  20250910_前世で告白_preview.mp3
  20250910_前世で告白.jpg
        """
    )
    parser.add_argument("--yes", "-y", action="store_true", help="確認なしで実行")
    parser.add_argument("--dry-run", action="store_true", help="実行せずに計画のみ表示")
    
    args = parser.parse_args()
    
    if args.dry_run:
        rebuild_docs(dry_run=True)
        return
    
    if not args.yes:
        # 計画表示後に確認
        rebuild_docs(dry_run=True)
        print()
        answer = input("  ❓ docs/ を再構築しますか？ (y/N): ").strip().lower()
        if answer != 'y':
            print("  キャンセルしました")
            return
    
    rebuild_docs(dry_run=False)


if __name__ == "__main__":
    main()

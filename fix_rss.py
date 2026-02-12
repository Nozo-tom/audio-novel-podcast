import json
import os
import sys
from pathlib import Path
from datetime import datetime

# Windows cp932 コンソールで絵文字・Unicode文字を表示するための対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Path setup
BASE_DIR = Path(r"c:\Users\natak\Documents\Novel")
DOCS_DIR = BASE_DIR / "docs"
EPISODES_JSON = DOCS_DIR / "episodes.json"
FEED_XML = DOCS_DIR / "feed.xml"
CONFIG_PATH = BASE_DIR / "config.yaml"

def load_config():
    import yaml
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    return {}

def _xml_escape(text):
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))

def main():
    print("🔧 RSSフィードの重複修正を開始します...")
    
    # 1. Load Episodes
    if not EPISODES_JSON.exists():
        print("❌ episodes.json not found.")
        return

    with open(EPISODES_JSON, 'r', encoding='utf-8') as f:
        episodes = json.load(f)

    print(f"📋 現在のエピソード数: {len(episodes)}")
    
    # 2. Filter Duplicates (Keep the latest one for each title)
    unique_episodes = {}
    for ep in episodes:
        title = ep['title']
        description = ep['description']
        # キーを正規化して比較（念のため）
        key = (title.strip(), description.strip())
        # 後勝ちで上書き（リストは時系列順と仮定）
        unique_episodes[key] = ep
        
    # Convert back to list
    cleaned_episodes = list(unique_episodes.values())
    
    if len(cleaned_episodes) < len(episodes):
        print(f"✨ 重複を削除しました: {len(episodes)} -> {len(cleaned_episodes)}")
    else:
        print("ℹ️ 重複は見つかりませんでした。")
    
    # Renumbering
    for i, ep in enumerate(cleaned_episodes):
        ep['number'] = i + 1
        
    # 3. Save JSON
    with open(EPISODES_JSON, 'w', encoding='utf-8') as f:
        json.dump(cleaned_episodes, f, ensure_ascii=False, indent=2)
        
    # 4. Regenerate XML
    config = load_config()
    podcast_config = config.get('podcast', {})
    output_config = config.get('output', {})
    
    channel_title = podcast_config.get('title', '音声小説チャンネル')
    channel_author = podcast_config.get('author', '制作チーム')
    channel_desc = podcast_config.get('description', 'オリジナル音声小説')
    channel_lang = podcast_config.get('language', 'ja')
    channel_category = podcast_config.get('category', 'Arts')
    channel_subcategory = podcast_config.get('subcategory', 'Books')
    channel_website = podcast_config.get('website', '')
    cover_art = podcast_config.get('cover_art', '')
    base_url = podcast_config.get('base_url', 'YOUR_HOSTING_URL_HERE')
    channel_email = podcast_config.get('email', '')

    items_xml = ""
    # XML should usually define items newest first
    for ep in reversed(cleaned_episodes):
        items_xml += f"""
    <item>
      <title>{_xml_escape(ep['title'])}</title>
      <description>{_xml_escape(ep['description'])}</description>
      <enclosure url="{base_url}/{ep['filename']}" length="{ep['size']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{ep['guid']}</guid>
      <pubDate>{ep['pub_date']}</pubDate>
      <itunes:duration>{ep['duration_formatted']}</itunes:duration>
      <itunes:episode>{ep['number']}</itunes:episode>
      <itunes:explicit>false</itunes:explicit>
    </item>"""

    cover_xml = ""
    if cover_art:
        cover_xml = f'\n    <itunes:image href="{base_url}/{cover_art}"/>'
    
    owner_xml = ""
    if channel_email:
        owner_xml = f"""
    <itunes:owner>
      <itunes:name>{_xml_escape(channel_author)}</itunes:name>
      <itunes:email>{channel_email}</itunes:email>
    </itunes:owner>"""

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{_xml_escape(channel_title)}</title>
    <description>{_xml_escape(channel_desc)}</description>
    <language>{channel_lang}</language>
    <itunes:author>{_xml_escape(channel_author)}</itunes:author>{owner_xml}
    <itunes:category text="{channel_category}">
      <itunes:category text="{channel_subcategory}"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>{cover_xml}
    <link>{channel_website}</link>
    <atom:link href="{base_url}/{output_config.get('feed_filename', 'feed.xml')}" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>"""

    with open(FEED_XML, 'w', encoding='utf-8') as f:
        f.write(feed_xml)
        
    print(f"✅ feed.xml を更新しました: {FEED_XML}")

if __name__ == "__main__":
    main()

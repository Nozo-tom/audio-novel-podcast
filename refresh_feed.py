import os
import json
import hashlib
import urllib.parse
from pathlib import Path
from datetime import datetime

# Import helper functions from publish_novel if possible, or just copy them
def _xml_escape(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&apos;")

def format_duration_itunes(seconds):
    if not seconds: return "00:00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def refresh_feed():
    docs_dir = Path("docs")
    episodes_json = docs_dir / "episodes.json"
    feed_path = docs_dir / "feed.xml"
    
    if not episodes_json.exists():
        print("episodes.json not found")
        return

    with open(episodes_json, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    # Simplified config for refresh
    channel_title = "聞くラノベ ～桜木ひより～"
    channel_author = "桜木ひより"
    channel_desc = "桜木ひよりの小説を音声でお届けします。小説家になろうにて連載中。"
    channel_lang = "ja"
    channel_email = "n.ataka.tom@gmail.com"
    base_url = "https://Nozo-tom.github.io/audio-novel-podcast"
    cover_art = "cover.png"

    items_xml = ""
    for ep in reversed(episodes):
        # Apply URL encoding here
        encoded_url = f"{base_url}/{urllib.parse.quote(ep['filename'])}"
        items_xml += f"""
    <item>
      <title>{_xml_escape(ep['title'])}</title>
      <description>{_xml_escape(ep['description'])}</description>
      <enclosure url="{encoded_url}" length="{ep['size']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{ep['guid']}</guid>
      <pubDate>{ep['pub_date']}</pubDate>
      <itunes:duration>{ep['duration_formatted']}</itunes:duration>
      <itunes:episode>{ep['number']}</itunes:episode>
      <itunes:explicit>false</itunes:explicit>
    </item>"""

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" 
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{_xml_escape(channel_title)}</title>
    <description>{_xml_escape(channel_desc)}</description>
    <language>{channel_lang}</language>
    <itunes:author>{_xml_escape(channel_author)}</itunes:author>
    <itunes:owner>
      <itunes:name>{_xml_escape(channel_author)}</itunes:name>
      <itunes:email>{channel_email}</itunes:email>
    </itunes:owner>
    <itunes:category text="Arts">
      <itunes:category text="Books"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:image href="{base_url}/{cover_art}"/>
    <link></link>
    <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>"""

    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    print("feed.xml refreshed and URL-encoded")

if __name__ == "__main__":
    refresh_feed()

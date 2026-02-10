# =============================================================================
# 📚 音声小説 → Spotify 自動配信ツール (publish_novel.py)
# テキスト → MP3変換 → RSSフィード生成 をワンコマンドで実行
# =============================================================================
#
# 使い方:
#   python publish_novel.py "novels/異世界転移したけど、最初の村が滅んでた件。.txt"
#   python publish_novel.py "novels/小説.txt" --title "第1話 タイトル" --voice fable
#   python publish_novel.py "novels/小説.txt" --description "エピソードの説明文"
#
# 初回セットアップ:
#   1. pip install openai pydub pyyaml python-dotenv podgen mutagen
#   2. config.yaml を編集（番組情報を設定）
#   3. .env にAPIキーを設定
#

import os
import sys

# Windows cp932 コンソールで絵文字・Unicode文字を表示するための対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import re
import time
import argparse
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime

# =============================================================================
# 設定読み込み
# =============================================================================

def load_config():
    """config.yaml を読み込む"""
    config_path = Path(__file__).parent / "config.yaml"
    
    if not config_path.exists():
        print("⚠️  config.yaml が見つかりません。デフォルト設定を使用します。")
        return get_default_config()
    
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print(f"✅ config.yaml を読み込みました")
        return config
    except ImportError:
        print("⚠️  pyyaml がインストールされていません。デフォルト設定を使用します。")
        print("   pip install pyyaml でインストールしてください。")
        return get_default_config()

def get_default_config():
    """デフォルト設定"""
    return {
        'podcast': {
            'title': '音声小説チャンネル',
            'author': '制作チーム',
            'description': 'オリジナル音声小説をお届けします',
            'language': 'ja',
            'category': 'Arts',
            'subcategory': 'Books',
            'cover_art': None,
            'website': '',
        },
        'tts': {
            'model': 'tts-1',
            'voice': 'fable',
            'instructions': None,
            'max_chunk_size': 4000,
            'request_interval': 0.5,
        },
        'output': {
            'mp3_dir': 'mp3',
            'feed_dir': 'feed',
            'feed_filename': 'feed.xml',
        },
        'reading_corrections': {}
    }

def load_env():
    """.env ファイルを読み込む"""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
            print("✅ .env を読み込みました")
        else:
            print("ℹ️  .env ファイルが見つかりません（環境変数から読み込みます）")
    except ImportError:
        print("ℹ️  python-dotenv 未インストール（環境変数から読み込みます）")

# =============================================================================
# ユーティリティ
# =============================================================================

def print_progress_bar(current, total, prefix='', suffix='', length=50, fill='█', empty='░'):
    percent = current / total * 100
    filled_length = int(length * current // total)
    bar = fill * filled_length + empty * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent:6.2f}% {suffix}', end='', flush=True)

def format_time(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}分{secs:02d}秒"

def print_status_box(lines, width=60):
    print("\n" + "┌" + "─" * width + "┐")
    for line in lines:
        padding = width - len(line) - sum(1 for c in line if ord(c) > 127)
        print(f"│ {line}{' ' * max(0, padding - 1)}│")
    print("└" + "─" * width + "┘")

def get_mp3_duration(filepath):
    """MP3ファイルの再生時間を秒で返す"""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(filepath)
        return audio.info.length
    except ImportError:
        # mutagen がなければ pydub で取得
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(filepath)
        return len(audio) / 1000.0
    except Exception:
        return 0

def format_duration_itunes(seconds):
    """秒をiTunesフォーマット (HH:MM:SS) に変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# =============================================================================
# 読み替え辞書
# =============================================================================

# デフォルトの読み替え辞書（config.yaml で上書き可能）
DEFAULT_CORRECTIONS = {
    "異世界": "いせかい",
    "転移": "てんい",
    "勇者": "ゆうしゃ",
    "死者交信": "ししゃこうしん",
    "亡霊": "ぼうれい",
    "刻印": "こくいん",
    "黒煙": "こくえん",
    "青空の下": "あおぞらのした",
}

def apply_replacements(text, corrections):
    """読み替え辞書に基づいてテキストを置換"""
    sorted_dict = sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True)
    for word, reading in sorted_dict:
        text = text.replace(word, reading)
    return text

# =============================================================================
# テキスト分割
# =============================================================================

def split_text_into_chunks(text, max_size=4000):
    """テキストを段落単位で分割"""
    paragraphs = text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(paragraph) > max_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            sentences = re.split(r'([。！？])', paragraph)
            temp_chunk = ""
            
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                if i + 1 < len(sentences):
                    sentence += sentences[i + 1]
                
                if len(temp_chunk) + len(sentence) <= max_size:
                    temp_chunk += sentence
                else:
                    if temp_chunk:
                        chunks.append(temp_chunk.strip())
                    temp_chunk = sentence
            
            if temp_chunk:
                current_chunk = temp_chunk
        else:
            test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
            
            if len(test_chunk) <= max_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

# =============================================================================
# MP3生成
# =============================================================================

def generate_mp3(input_file, config, voice_override=None, model_override=None):
    """テキストファイルをMP3に変換"""
    
    # OpenAI APIキー確認
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 環境変数 OPENAI_API_KEY が設定されていません")
        print("   .env ファイルに OPENAI_API_KEY=sk-xxxxx を記入してください")
        sys.exit(1)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        print("✅ OpenAI クライアント初期化完了")
    except ImportError:
        print("❌ openai ライブラリが必要です: pip install openai")
        sys.exit(1)
    
    try:
        from pydub import AudioSegment
    except ImportError:
        print("❌ pydub ライブラリが必要です: pip install pydub")
        sys.exit(1)
    
    # 設定
    tts_config = config.get('tts', {})
    tts_model = model_override or tts_config.get('model', 'tts-1')
    tts_voice = voice_override or tts_config.get('voice', 'fable')
    tts_instructions = tts_config.get('instructions', None)
    max_chunk_size = tts_config.get('max_chunk_size', 4000)
    request_interval = tts_config.get('request_interval', 0.5)
    
    # gpt-4o-mini-tts の場合のチャンクサイズ調整
    if tts_model == "gpt-4o-mini-tts":
        max_chunk_size = min(max_chunk_size, 1200)
    
    # テキスト読み込み
    print(f"\n📁 テキストファイル: {input_file}")
    
    encodings_to_try = ['utf-8', 'shift_jis', 'cp932', 'euc-jp']
    novel_text = None
    
    for encoding in encodings_to_try:
        try:
            with open(input_file, 'r', encoding=encoding) as f:
                novel_text = f.read()
            break
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            print(f"❌ ファイルが見つかりません: {input_file}")
            sys.exit(1)
    
    if novel_text is None:
        print("❌ エンコーディング検出失敗")
        sys.exit(1)
    
    # 前処理
    novel_text = novel_text.strip()
    novel_text = re.sub(r'\r\n', '\n', novel_text)
    novel_text = re.sub(r'\n{3,}', '\n\n', novel_text)
    
    # 読み替え辞書
    corrections = DEFAULT_CORRECTIONS.copy()
    config_corrections = config.get('reading_corrections', {})
    if config_corrections:
        corrections.update(config_corrections)
    
    print("📝 読み替え辞書を適用中...")
    for word, reading in corrections.items():
        if word in novel_text:
            print(f"   - {word} → {reading}")
    novel_text = apply_replacements(novel_text, corrections)
    
    # テキスト分割
    chunks = split_text_into_chunks(novel_text, max_chunk_size)
    total_chars = sum(len(chunk) for chunk in chunks)
    
    print_status_box([
        "📊 テキスト情報",
        f"   総文字数: {total_chars:,} 文字",
        f"   チャンク数: {len(chunks)}",
        f"   モデル: {tts_model}",
        f"   音声: {tts_voice}",
    ])
    
    # 出力パス
    output_config = config.get('output', {})
    mp3_dir = Path(__file__).parent / output_config.get('mp3_dir', 'mp3')
    mp3_dir.mkdir(parents=True, exist_ok=True)
    
    input_basename = Path(input_file).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{input_basename}_{timestamp}.mp3"
    output_path = mp3_dir / output_filename
    
    # 音声生成
    print("\n" + "=" * 60)
    print("🎙️ 音声生成を開始します")
    print("=" * 60)
    
    temp_dir = tempfile.mkdtemp()
    audio_files = []
    total_audio_size = 0
    start_time = time.time()
    processed_chars = 0
    
    for i, chunk in enumerate(chunks):
        chunk_start = time.time()
        
        try:
            chunk_path = os.path.join(temp_dir, f"chunk_{i+1:03d}.mp3")
            
            params = {
                "model": tts_model,
                "voice": tts_voice,
                "input": chunk,
                "response_format": "mp3",
            }
            if tts_instructions:
                params["instructions"] = tts_instructions
            
            response = client.audio.speech.create(**params)
            response.stream_to_file(chunk_path)
            
            file_size = os.path.getsize(chunk_path)
            audio_files.append(chunk_path)
            total_audio_size += file_size
            
            chunk_time = time.time() - chunk_start
            processed_chars += len(chunk)
            
            # 進捗表示
            pct = processed_chars / total_chars * 100
            bar_len = 20
            filled = int(bar_len * processed_chars // total_chars)
            bar = "█" * filled + "░" * (bar_len - filled)
            size_kb = file_size / 1024
            print(f"  [{i+1}/{len(chunks)}] {len(chunk):,}文字 | {size_kb:.0f}KB | {chunk_time:.1f}s | {bar} {pct:.0f}%")
            
            if i < len(chunks) - 1:
                time.sleep(request_interval)
                
        except Exception as e:
            print(f"\n❌ チャンク {i+1} でエラー: {str(e)}")
            sys.exit(1)
    
    total_time = time.time() - start_time
    
    # 結合
    print("\n🔗 音声ファイルを結合中...")
    combined = AudioSegment.from_mp3(audio_files[0])
    for audio_file in audio_files[1:]:
        combined += AudioSegment.from_mp3(audio_file)
    
    combined.export(str(output_path), format="mp3")
    
    # クリーンアップ
    for f in audio_files:
        try:
            os.remove(f)
        except:
            pass
    
    final_size = os.path.getsize(output_path) / (1024 * 1024)
    duration_sec = len(combined) / 1000
    
    print_status_box([
        "✅ MP3 生成完了！",
        f"   ファイル: {output_filename}",
        f"   サイズ: {final_size:.2f} MB",
        f"   再生時間: {format_time(duration_sec)}",
        f"   処理時間: {format_time(total_time)}",
    ])
    
    return str(output_path), duration_sec

# =============================================================================
# RSSフィード生成
# =============================================================================

def generate_rss_feed(config, mp3_path, episode_title, episode_description, episode_number=None):
    """RSSフィード (feed.xml) を生成・更新"""
    
    output_config = config.get('output', {})
    podcast_config = config.get('podcast', {})
    
    feed_dir = Path(__file__).parent / output_config.get('feed_dir', 'feed')
    feed_dir.mkdir(parents=True, exist_ok=True)
    
    feed_path = feed_dir / output_config.get('feed_filename', 'feed.xml')
    episodes_json = feed_dir / "episodes.json"
    
    # MP3をフィードディレクトリにコピー
    mp3_filename = Path(mp3_path).name
    feed_mp3_path = feed_dir / mp3_filename
    
    import shutil
    shutil.copy2(mp3_path, feed_mp3_path)
    print(f"📁 MP3をfeedディレクトリにコピー: {mp3_filename}")
    
    # MP3の情報取得
    mp3_size = os.path.getsize(feed_mp3_path)
    mp3_duration = get_mp3_duration(str(feed_mp3_path))
    
    # エピソード情報の管理
    import json
    
    episodes = []
    if episodes_json.exists():
        with open(episodes_json, 'r', encoding='utf-8') as f:
            episodes = json.load(f)
    
    # 新しいエピソード
    if episode_number is None:
        episode_number = len(episodes) + 1
    
    new_episode = {
        "number": episode_number,
        "title": episode_title,
        "description": episode_description,
        "filename": mp3_filename,
        "size": mp3_size,
        "duration": mp3_duration,
        "duration_formatted": format_duration_itunes(mp3_duration),
        "pub_date": datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0900"),
        "guid": hashlib.md5(f"{episode_title}_{mp3_filename}".encode()).hexdigest(),
    }
    
    episodes.append(new_episode)
    
    # episodes.json を保存
    with open(episodes_json, 'w', encoding='utf-8') as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)
    
    # RSSフィードXMLを生成
    channel_title = podcast_config.get('title', '音声小説チャンネル')
    channel_author = podcast_config.get('author', '制作チーム')
    channel_desc = podcast_config.get('description', 'オリジナル音声小説')
    channel_lang = podcast_config.get('language', 'ja')
    channel_category = podcast_config.get('category', 'Arts')
    channel_subcategory = podcast_config.get('subcategory', 'Books')
    channel_website = podcast_config.get('website', '')
    cover_art = podcast_config.get('cover_art', '')
    
    # base_url: ホスティング先のURL（config で設定）
    base_url = podcast_config.get('base_url', 'YOUR_HOSTING_URL_HERE')
    
    # XML生成
    items_xml = ""
    for ep in reversed(episodes):  # 新しい順
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
    <itunes:category text="{channel_category}">
      <itunes:category text="{channel_subcategory}"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>{cover_xml}
    <link>{channel_website}</link>
    <atom:link href="{base_url}/{output_config.get('feed_filename', 'feed.xml')}" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>"""
    
    with open(feed_path, 'w', encoding='utf-8') as f:
        f.write(feed_xml)
    
    print_status_box([
        "📡 RSSフィード更新完了！",
        f"   ファイル: {feed_path}",
        f"   エピソード数: {len(episodes)}",
        f"   最新: {episode_title}",
    ])
    
    return str(feed_path)

def _xml_escape(text):
    """XMLエスケープ"""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))

# =============================================================================
# メイン処理
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="📚 音声小説 → Spotify 自動配信ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python publish_novel.py "novels/小説.txt"
  python publish_novel.py "novels/小説.txt" --title "第1話" --voice fable
  python publish_novel.py "novels/小説.txt" --mp3-only
  python publish_novel.py --feed-only --mp3 "mp3/既存.mp3" --title "第2話"
        """
    )
    
    parser.add_argument("input", nargs="?", help="入力テキストファイルのパス")
    parser.add_argument("--title", "-t", help="エピソードタイトル（デフォルト: ファイル名から自動生成）")
    parser.add_argument("--description", "-d", help="エピソードの説明文", default="")
    parser.add_argument("--voice", "-v", help="音声タイプ (alloy, ash, ballad, cedar, coral, echo, fable, marin, nova, onyx, sage, shimmer, verse)")
    parser.add_argument("--model", "-m", help="TTSモデル (tts-1, tts-1-hd, gpt-4o-mini-tts)")
    parser.add_argument("--episode", "-e", type=int, help="エピソード番号")
    parser.add_argument("--mp3-only", action="store_true", help="MP3生成のみ（RSSフィード生成をスキップ）")
    parser.add_argument("--feed-only", action="store_true", help="RSSフィード生成のみ（既存MP3を使用）")
    parser.add_argument("--mp3", help="（--feed-only 時）既存MP3ファイルのパス")
    
    args = parser.parse_args()
    
    # バナー表示
    print("\n" + "=" * 60)
    print("📚 音声小説 → Spotify 自動配信ツール")
    print("=" * 60)
    
    # 設定読み込み
    load_env()
    config = load_config()
    
    # 入力チェック
    if args.feed_only:
        if not args.mp3:
            print("❌ --feed-only の場合は --mp3 で既存MP3ファイルを指定してください")
            sys.exit(1)
        if not args.title:
            print("❌ --feed-only の場合は --title でエピソードタイトルを指定してください")
            sys.exit(1)
        mp3_path = args.mp3
        if not os.path.exists(mp3_path):
            print(f"❌ MP3ファイルが見つかりません: {mp3_path}")
            sys.exit(1)
    else:
        if not args.input:
            parser.print_help()
            sys.exit(1)
        if not os.path.exists(args.input):
            print(f"❌ 入テキストファイルが見つかりません: {args.input}")
            sys.exit(1)
    
    # STEP 1: MP3生成
    if not args.feed_only:
        print("\n" + "─" * 60)
        print("📖 STEP 1: テキスト → MP3 変換")
        print("─" * 60)
        
        mp3_path, duration = generate_mp3(
            args.input,
            config,
            voice_override=args.voice,
            model_override=args.model,
        )
    
    # STEP 2: RSSフィード生成
    if not args.mp3_only:
        print("\n" + "─" * 60)
        print("📡 STEP 2: RSSフィード生成")
        print("─" * 60)
        
        # エピソードタイトル
        if args.title:
            episode_title = args.title
        elif args.input:
            episode_title = Path(args.input).stem
        else:
            episode_title = Path(mp3_path).stem
        
        # エピソード説明
        episode_desc = args.description if args.description else f"「{episode_title}」の音声版をお届けします。"
        
        feed_path = generate_rss_feed(
            config,
            mp3_path,
            episode_title=episode_title,
            episode_description=episode_desc,
            episode_number=args.episode,
        )
        
        # 次のステップの案内
        podcast_config = config.get('podcast', {})
        base_url = podcast_config.get('base_url', '')
        
        print("\n" + "=" * 60)
        print("🎉 すべての処理が完了しました！")
        print("=" * 60)
        
        if not base_url or base_url == 'YOUR_HOSTING_URL_HERE':
            print_status_box([
                "📋 次のステップ（初回のみ）",
                "",
                "1. feedフォルダの中身をホスティングサービスにアップ",
                "   （RSS.com, GitHub Pages, Cloudflare R2 等）",
                "",
                "2. config.yaml の base_url をホスティングURLに更新",
                "",
                "3. Spotify for Podcasters にRSSフィードURLを登録",
                "   https://podcasters.spotify.com",
                "",
                "※ 2回目以降はfeedフォルダを再アップするだけでOK！",
            ], width=58)
        else:
            print_status_box([
                "✅ 配信準備完了！",
                f"   feedフォルダをホスティング先にアップしてください",
                f"   Spotifyが自動巡回して反映されます（数時間〜24h）",
            ])
    else:
        print("\n🎉 MP3生成が完了しました！")
        print(f"   出力: {mp3_path}")

if __name__ == "__main__":
    main()

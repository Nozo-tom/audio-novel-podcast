# =============================================================================
# 📚 音声小説 → Spotify 自動配信ツール (publish_novel.py)
# テキスト → MP3変換 → RSSフィード生成 をワンコマンドで実行
# =============================================================================
#
# 使い方:
#   python publish_novel.py            (novelsフォルダ内の全ファイルを処理)
#   python publish_novel.py "novels/小説.txt"
#   python publish_novel.py --feed-only --mp3 "mp3/既存.mp3" --title "タイトル"
#
# 初回セットアップ:
#   1. pip install openai pydub pyyaml python-dotenv podgen mutagen janome
#   2. config.yaml を編集（番組情報を設定）
#   3. .env にAPIキーを設定
#
# 🚀 Core Ultra 285 最適化:
#   - 並列処理によるAPIリクエスト高速化
#   - オフライン読み推定チェック (Janome)
#
# =============================================================================

import os
import sys
import shutil
import subprocess

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
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        
        # completedディレクトリの作成
        novels_dir = Path(__file__).parent / "novels"
        completed_dir = novels_dir / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)
        
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
            'request_interval': 0.1, # 並列化のため短縮
        },
        'output': {
            'mp3_dir': 'mp3',
            'feed_dir': 'docs', # config.yamlに合わせる
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

def git_commit_push(message="Update podcast feed"):
    """Git commit and push"""
    try:
        print("\n🚀 GitHubへアップロード中...")
        # ステージング
        subprocess.run(["git", "add", "."], check=True)
        # コミット
        result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        if result.returncode != 0:
            if "nothing to commit" in result.stdout:
                print("ℹ️ コミットする変更はありませんでした")
                return # 変更なしでもpushは試みるか、ここで抜けるか。念のためpushはしない
            else:
                print(f"⚠️ Git Commit Error: {result.stderr}")
                return

        subprocess.run(["git", "push"], check=True)
        print("✅ GitHubへのプッシュ完了")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Git操作中にエラーが発生しました: {e}")
    except FileNotFoundError:
        print("⚠️ gitコマンドが見つかりません")
    except Exception as e:
         print(f"⚠️ Git操作失敗: {e}")

def move_to_completed(file_path):
    """処理済みファイルをcompletedフォルダに移動"""
    source = Path(file_path)
    # publish_novel.py と同じ階層の novels/completed を想定
    completed_dir = Path(__file__).parent / "novels" / "completed"
    completed_dir.mkdir(parents=True, exist_ok=True)
    
    target = completed_dir / source.name
    
    # 同名のYAMLファイルも移動
    yaml_source = source.with_suffix('.yaml')
    yaml_target = completed_dir / yaml_source.name
    
    try:
        # 既に存在する場合は上書き移動
        if target.exists():
            target.unlink()
        
        shutil.move(str(source), str(target))
        print(f"📦 テキストファイルを移動: {target.name}")

        if yaml_source.exists():
            if yaml_target.exists():
                yaml_target.unlink()
            shutil.move(str(yaml_source), str(yaml_target))
            print(f"📦 YAMLファイルを移動: {yaml_target.name}")
            
        return True
    except Exception as e:
        print(f"❌ ファイル移動エラー: {e}")
        return False

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
    """読み替え辞書に基づいてテキストを置換（ひらがな化を徹底）"""
    # 長い単語から順に置換
    sorted_dict = sorted(corrections.items(), key=lambda x: len(x[0]), reverse=True)
    for word, reading in sorted_dict:
        # 置換時に前後に微小なスペースまたは句読点を意識させることで、
        # 「おこのこ」のような不自然な読みの分割を防ぐ
        # OpenAI TTS はスペースで発話の区切りを判断するため、読みをひらがなで固定
        text = text.replace(word, reading)
    return text

# =============================================================================
# 読みチェック (Janome)
# =============================================================================
def check_reading(text, corrections, config):
    try:
        from janome.tokenizer import Tokenizer
        from collections import Counter
        
        print("\n" + "─" * 60)
        print("🔍 STEP 0: 読み推定チェック (Beta)")
        print("─" * 60)

        t = Tokenizer()
        
        # チェック対象の抽出
        check_words = []
        unknown_words = []
        
        # 抽出したい品詞
        TARGET_POS = ['名詞']
        IGNORE_WORDS = ['こと', 'もの', 'よう', 'ため', 'やつ', 'これ', 'それ', 'あれ']
        
        print("⏳ テキスト解析中...")
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
                    check_words.append((surface, reading, is_proper))
        
        # 集計
        words_counter = Counter([(w, r, p) for w, r, p in check_words])
        sorted_words = sorted(words_counter.items(), key=lambda x: (not x[0][2], -x[1])) # 固有名詞優先、頻度順
        
        # 結果表示
        print(f"\n{'単語':<12} | {'推定読み':<12} | {'回数':<4} | {'判定'}")
        print("-" * 50)
        
        lines_printed = 0
        MAX_LINES = 20 # 表示数制限
        
        found_issues = False
        
        for (word, reading, is_proper), count in sorted_words:
            # 辞書登録済みのものはスキップ
            if word in corrections:
                continue
                
            # 漢字を含まないものはスキップ
            if all(c in "ァ-ンーぁ-ん0-9a-zA-Z" for c in word):
                continue
            
            # 1文字の名詞はノイズが多いのでスキップ
            if len(word) == 1 and not is_proper:
                continue

            found_issues = True
            mark = "🔴" if is_proper else "  "
            print(f"{mark} {word:<10} | {reading:<12} | {count:<4} |")
            
            lines_printed += 1
            if lines_printed >= MAX_LINES:
                print(f"\n... 他 {len(sorted_words) - MAX_LINES} 語")
                break
        
        if unknown_words:
            print("\n⚠️ 読みが不明な単語 (辞書登録推奨)")
            unknown_counter = Counter(unknown_words)
            for word, count in unknown_counter.most_common(10):
                 print(f"❓ {word} ({count}回)")
            found_issues = True
        
        if found_issues:
            print("\n💡 ヒント: 読み間違いがある場合は .yaml の corrections に追加してください")
            print("   （処理はそのまま続行します）")
        else:
            print("✅ 特に注意が必要な単語は見つかりませんでした")

    except ImportError:
        print("⚠️ janomeライブラリがないため読みチェックをスキップします (pip install janome)")
    except Exception as e:
        print(f"⚠️ 読みチェック中にエラー: {e}")

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

def generate_chunk(client, chunk, i, tts_model, tts_voice, tts_instructions):
    """並列処理用のチャンク生成関数"""
    temp_fd, temp_path = tempfile.mkstemp(suffix=f"_chunk_{i:03d}.mp3")
    os.close(temp_fd)
    
    try:
        params = {
            "model": tts_model,
            "voice": tts_voice,
            "input": chunk,
            "response_format": "mp3",
        }
        if tts_instructions:
            params["instructions"] = tts_instructions
        
        # OpenAI Client is generic, but calls are synchronous. 
        # ThreadPoolExecutor makes them concurrent.
        response = client.audio.speech.create(**params)
        response.stream_to_file(temp_path)
        return i, temp_path, None
    except Exception as e:
        return i, None, str(e)


def generate_mp3(input_file, config, voice_override=None, model_override=None):
    """テキストファイルをMP3に変換（並列処理版）"""
    
    # OpenAI APIキー確認
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 環境変数 OPENAI_API_KEY が設定されていません")
        sys.exit(1)
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
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
            return None, 0
    
    if novel_text is None:
        print("❌ エンコーディング検出失敗")
        return None, 0
    
    # 台本ファイル (.script.txt) の確認
    script_file = Path(input_file).with_suffix('.script.txt')
    is_script = False
    
    if script_file.exists():
        print(f"📖 台本ファイルを発見しました: {script_file.name}")
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                novel_text = f.read()
            is_script = True
        except Exception as e:
            print(f"⚠️ 台本の読み込みに失敗しました（原文を使用します）: {e}")

    # 前処理
    novel_text = novel_text.strip()
    novel_text = re.sub(r'\r\n', '\n', novel_text)
    novel_text = re.sub(r'\n{3,}', '\n\n', novel_text)

    # 読み替え辞書準備
    corrections = DEFAULT_CORRECTIONS.copy()
    config_corrections = config.get('reading_corrections', {})
    if config_corrections:
        corrections.update(config_corrections)
    
    if is_script:
        print("🎭 台本モード: 漢字[かな] を [かな] に変換します...")
        # 漢字[かな] の形式を かな に置換
        # ※ かな の前後にスペースを入れることで、TTSの読みの明瞭さを向上させる
        novel_text = re.sub(r'[^\[\]\n\s]+?\[(.+?)\]', r' \1 ', novel_text)
    else:
        # 通常モード: 読みチェックと辞書適用
        check_reading(novel_text, corrections, config)
        print("📝 読み替え辞書を適用中...")
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
        "   処理: 並列化 (Core Ultra 285 Speed Boost)", 
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
    print("🎙️ Speed Boost 音声生成を開始します (並列処理)")
    print("=" * 60)
    
    audio_files_map = {}
    completed_chunks = 0
    start_time = time.time()
    
    # 並列処理: ThreadPoolExecutorを使用
    # APIリクエストはIOバウンドだが、多数の同時接続による高速化を図る
    # 同時接続数10
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(generate_chunk, client, chunk, i, tts_model, tts_voice, tts_instructions): i for i, chunk in enumerate(chunks)}
        
        for future in as_completed(futures):
            i, path, error = future.result()
            if error:
                print(f"❌ チャンク {i} エラー: {error}")
                # エラー時は生成済みのファイルを消して終了
                for f in audio_files_map.values():
                    try: os.remove(f)
                    except: pass
                return None, 0
            
            audio_files_map[i] = path
            completed_chunks += 1
            
            # 進捗表示
            pct = completed_chunks / len(chunks) * 100
            bar = "█" * int(20 * pct / 100) + "░" * (20 - int(20 * pct / 100))
            print(f"\r🚀 生成中: [{completed_chunks}/{len(chunks)}] {bar} {pct:.0f}%", end='', flush=True)

    print("\n")
    
    # 順番通りに取得
    audio_files = [audio_files_map[i] for i in range(len(chunks))]
    
    total_time = time.time() - start_time
    
    # 結合
    print("🔗 音声ファイルを結合中...")
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
        f"   処理時間: {format_time(total_time)} (並列処理)",
    ])
    
    return str(output_path), duration_sec

# =============================================================================
# RSSフィード生成
# =============================================================================

def generate_rss_feed(config, mp3_path, episode_title, episode_description, episode_number=None):
    """RSSフィード (feed.xml) を生成・更新"""
    
    output_config = config.get('output', {})
    podcast_config = config.get('podcast', {})
    
    feed_dir = Path(__file__).parent / output_config.get('feed_dir', 'docs')
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
    
    # 新しいエピソード番号
    if episode_number is None:
        last_num = 0
        if episodes:
            last_num = max(e.get('number', 0) for e in episodes)
        episode_number = last_num + 1
    
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
    
    channel_email = podcast_config.get('email', '')

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

def process_file(args, input_file, config, overrides=None):
    """単一ファイルの処理"""
    if overrides is None:
        overrides = {}

    # カテゴリーに基づく音声の自動選択
    category = overrides.get('category', '')
    voice_final = args.voice
    
    if not voice_final:
        # YAMLでの指定を優先
        voice_final = overrides.get('voice')
        if not voice_final and category:
            mapping = config.get('tts', {}).get('category_voices', {})
            for kw, v in mapping.items():
                if kw in category:
                    voice_final = v
                    print(f"🎭 カテゴリー '{category}' に基づき音声 '{v}' を選択しました")
                    break
    
    # 個別辞書の適用
    extra_corr = overrides.get('corrections', {})
    if extra_corr:
        if 'reading_corrections' not in config: config['reading_corrections'] = {}
        config['reading_corrections'].update(extra_corr)
        print(f"📖 作品別の読み替え辞書（{len(extra_corr)}件）を適用しました")

    # STEP 1: MP3生成
    mp3_path = None
    if not args.feed_only:
        print("\n" + "─" * 60)
        print(f"📖 STEP 1: テキスト → MP3 変換: {Path(input_file).name}")
        print("─" * 60)
        
        mp3_path, duration = generate_mp3(
            input_file,
            config,
            voice_override=voice_final,
            model_override=args.model,
        )
        if not mp3_path: return False
    else:
        # feed_onlyの場合、mp3_pathが必要
        mp3_path = args.mp3
        if not mp3_path:
             print("❌ --feed-only の場合は --mp3 で既存MP3ファイルを指定してください")
             return False

    # STEP 2: RSSフィード生成
    if not args.mp3_only:
        print("\n" + "─" * 60)
        print("📡 STEP 2: RSSフィード生成")
        print("─" * 60)
        
        # エピソードタイトル
        episode_title = overrides.get('title')
        if not episode_title:
             if args.title:
                 episode_title = args.title
             else:
                 episode_title = Path(input_file).stem
        
        # エピソード説明
        episode_desc = args.description if args.description else f"「{episode_title}」の音声版をお届けします。"
        
        generate_rss_feed(
            config,
            mp3_path,
            episode_title=episode_title,
            episode_description=episode_desc,
            episode_number=args.episode,
        )
    
    # ファイル移動
    if not args.feed_only and input_file:
         move_to_completed(input_file)
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description="📚 音声小説 → Spotify 自動配信ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument("input", nargs="?", help="入力テキストファイルのパス (指定なしの場合はnovelsフォルダ内の全txtを処理)")
    parser.add_argument("--title", "-t", help="エピソードタイトル")
    parser.add_argument("--description", "-d", help="エピソードの説明文")
    parser.add_argument("--voice", "-v", help="音声タイプ")
    parser.add_argument("--model", "-m", help="TTSモデル")
    parser.add_argument("--episode", "-e", type=int, help="エピソード番号")
    parser.add_argument("--mp3-only", action="store_true", help="MP3生成のみ")
    parser.add_argument("--feed-only", action="store_true", help="RSSフィード生成のみ")
    parser.add_argument("--mp3", help="既存MP3ファイルのパス")
    parser.add_argument("--no-push", action="store_true", help="GitHubへのプッシュをスキップ")
    
    args = parser.parse_args()
    
    # バナー表示
    print("\n" + "=" * 60)
    print("📚 音声小説 → Spotify 自動配信ツール")
    print("=" * 60)
    
    # 設定読み込み
    load_env()
    config = load_config()
    
    # 処理対象ファイルのリストアップ
    target_files = []
    
    if args.input:
        if not os.path.exists(args.input):
            print(f"❌ ファイルが見つかりません: {args.input}")
            sys.exit(1)
        target_files.append(args.input)
    elif args.feed_only:
        # feed_onlyの場合はファイル処理なし（引数依存）
        target_files = []
    else:
        # novelsフォルダ内のtxtファイルを検索
        novels_dir = Path(__file__).parent / "novels"
        if novels_dir.exists():
            print(f"DEBUG: Search dir: {novels_dir.absolute()}")
            # Print all files in dir for debug
            for f in novels_dir.iterdir():
                print(f"DEBUG: Found file: {f.name}")
            target_files = list(novels_dir.glob("*.txt"))
            # completedフォルダは除外（globは再帰しないのでOK）
            print(f"🔎 novelsフォルダ内の小説を検索中... {len(target_files)}件ヒット")
        else:
             print("❌ novelsフォルダが見つかりません")
             sys.exit(1)

    if not target_files and not args.feed_only:
        print("⚠️ 処理対象のファイルがありません。")
        sys.exit(0)

    # 処理実行
    processed_count = 0
    for input_file in target_files:
        print(f"\n🚀 処理開始: {input_file}")
        
        # 作品情報の読み込み (.yaml)
        overrides = {}
        info_path = Path(input_file).with_suffix('.yaml')
        if info_path.exists():
            try:
                import yaml
                with open(info_path, 'r', encoding='utf-8') as f:
                    overrides = yaml.safe_load(f) or {}
                print(f"✅ 作品情報を読み込みました: {info_path.name}")
            except Exception as e:
                print(f"⚠️  作品情報の読み込み失敗: {e}")
        
        success = process_file(args, input_file, config, overrides)
        if success:
            processed_count += 1
            
    # RSSフィード生成のみの場合
    if args.feed_only:
         process_file(args, None, config, {})
         processed_count = 1

    # Git Push
    if processed_count > 0 and not args.no_push:
        git_commit_push(message=f"Update podcast: processed {processed_count} episodes")
    
    print("\n🎉 全処理完了！")

if __name__ == "__main__":
    main()

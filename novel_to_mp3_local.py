# =============================================================================
# 📚 日本語小説 → MP3 変換ツール（ローカルPC用）
# OpenAI TTS API を使用して日本語小説を音声化
# =============================================================================

import os
import time
import re
import sys
import tempfile
from pathlib import Path

# 進捗バー用
def print_progress_bar(current, total, prefix='', suffix='', length=50, fill='█', empty='░'):
    """詳細な進捗バーを表示"""
    percent = current / total * 100
    filled_length = int(length * current // total)
    bar = fill * filled_length + empty * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent:6.2f}% {suffix}', end='', flush=True)

def format_time(seconds):
    """秒を分:秒形式にフォーマット"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}分{secs:02d}秒"

def print_status_box(lines, width=60):
    """ステータスボックスを表示"""
    print("\n" + "┌" + "─" * width + "┐")
    for line in lines:
        padding = width - len(line) - sum(1 for c in line if ord(c) > 127)
        print(f"│ {line}{' ' * max(0, padding - 1)}│")
    print("└" + "─" * width + "┘")

# =============================================================================
# 設定
# =============================================================================

# テキストファイルのパス
# テキストファイルのパス
INPUT_FILE = r"c:\Users\natak\Documents\Novel\ひより01_元.txt"

# 出力ファイル名（タイムスタンプ付きで上書き防止）
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
INPUT_BASENAME = os.path.splitext(os.path.basename(INPUT_FILE))[0]
OUTPUT_FILENAME = f"{INPUT_BASENAME}_{timestamp}.mp3"

# TTS設定
REQUEST_INTERVAL = 0.5        # API リクエスト間隔（秒）

# =============================================================================
# モデル選択
# =============================================================================

MODEL_OPTIONS = {
    "1": ("tts-1", "tts-1 - 標準品質・高速・低コスト"),
    "2": ("tts-1-hd", "tts-1-hd - 高品質・やや遅い"),
    "3": ("gpt-4o-mini-tts", "gpt-4o-mini-tts - 最新・話し方指示可能"),
}

print("\n" + "=" * 60)
print("📚 日本語小説 → MP3 変換ツール")
print("=" * 60)

print("\n🔧 モデルを選択してください:\n")
for key, (model_id, desc) in MODEL_OPTIONS.items():
    print(f"  [{key}] {desc}")

while True:
    model_choice = input("\n選択 (1-3, デフォルト=1 tts-1): ").strip()
    if model_choice == "":
        model_choice = "1"
    if model_choice in MODEL_OPTIONS:
        TTS_MODEL, model_desc = MODEL_OPTIONS[model_choice]
        break
    print("❌ 1〜3の数字を入力してください")

print(f"\n✅ 選択されたモデル: {model_desc}")

# モデルに応じたチャンクサイズ設定
# 日本語は1文字≒1.5トークンのため、トークン上限から逆算
if TTS_MODEL == "gpt-4o-mini-tts":
    MAX_CHUNK_SIZE = 1200   # 2000トークン上限 → 約1200文字
    print(f"   チャンクサイズ: {MAX_CHUNK_SIZE}文字 (トークン上限2000)")
else:
    MAX_CHUNK_SIZE = 4000   # tts-1/tts-1-hd は4096トークン上限
    print(f"   チャンクサイズ: {MAX_CHUNK_SIZE}文字")

# gpt-4o-mini-ttsの場合、話し方の指示を入力可能
TTS_INSTRUCTIONS = None
if TTS_MODEL == "gpt-4o-mini-tts":
    print("\n💬 話し方の指示を入力できます（例: 「優しく穏やかに読んでください」）")
    TTS_INSTRUCTIONS = input("   指示 (空欄でスキップ): ").strip()
    if not TTS_INSTRUCTIONS:
        TTS_INSTRUCTIONS = None

# =============================================================================
# 音声選択
# =============================================================================

VOICE_OPTIONS = {
    "1": ("alloy", "🎭 Alloy - 中性的でバランスの取れた、落ち着いた声"),
    "2": ("ash", "🌋 Ash - 落ち着いた、知的な声"),
    "3": ("ballad", "🎵 Ballad - 感情豊かで、語りかけるような声"),
    "4": ("cedar", "🌲 Cedar - 自然で温かみのある声 ⭐おすすめ"),
    "5": ("coral", "🪸 Coral - 明るく軽やかな声"),
    "6": ("echo", "🎤 Echo - 落ち着いた、やや深みのある男性的な声"),
    "7": ("fable", "📖 Fable - 表現力豊かで、物語の朗読に向いた声"),
    "8": ("marin", "🌊 Marin - 自然で聞き取りやすい声 ⭐おすすめ"),
    "9": ("nova", "✨ Nova - 明るく、親しみやすい女性的な声"),
    "10": ("onyx", "💪 Onyx - 力強く、自信に満ちた男性的な声"),
    "11": ("sage", "🌿 Sage - 落ち着いた知的な声"),
    "12": ("shimmer", "💎 Shimmer - 澄んだ、知的な印象を与える女性的な声"),
    "13": ("verse", "📜 Verse - 豊かな表現力を持つ声"),
}

print("\n🎙️ 音声タイプを選択してください:\n")
for key, (voice_id, desc) in VOICE_OPTIONS.items():
    print(f"  [{key:>2s}] {desc}")

while True:
    choice = input("\n選択 (1-13, デフォルト=7 Fable): ").strip()
    if choice == "":
        choice = "7"
    if choice in VOICE_OPTIONS:
        TTS_VOICE, voice_desc = VOICE_OPTIONS[choice]
        break
    print("❌ 1〜13の数字を入力してください")

print(f"\n✅ 選択された音声: {voice_desc}")

# =============================================================================
# 読み替え辞書 (Reading Correction)
# =============================================================================

# TTSが読み間違えやすい単語をひらがなに置換
REPLACEMENT_DICT = {
    # 登場人物
    "花音": "かのん",
    "蒼真": "そうま",
    "黒羽": "くろば",
    "桜庭": "さくらば",
    "悠太": "ゆうた",
    "神崎": "かんざき",
    "黒羽涼介": "くろばりょうすけ",
    "黒羽先輩": "くろば せんぱい",
    
    # 固有名詞・用語
    "転生": "てんせい",
    "転生者": "てんせいしゃ",
    "幼馴染": "おさななじみ",
    "前世": "ぜんせ",
    "表向き": "おもてむき",
    "鏡": "かがみ",
    "流行る": "はやる",
    "楽々": "らくらく",
    "首を傾げ": "くびをかしげ",
    "眼差し": "まなざし",
    "発起人": "ほっきにん",
    "微笑んだ": "ほほえんだ",
    "拳": "こぶし",
    "涙": "なみだ",
    "急騰": "きゅうとう",
    "隣": "となり",
    "大人気": "だいにんき",
    "終えた男": "おえたおとこ",
    "饒舌さ": "じょうぜつさ",
    "口説く": "くどく",
    "一年が経った": "いちねんがたった",
    "見出している": "みいだしてる",
    "花音の心": "かのんのこころ ",
    "青空の下": "あおぞらのした",

    
    
    # 数字・単位（文脈によって読みが変わるもの）
    "一ヶ月": "1ヶ月",  # アラビア数字に統一しておくのも手
    "三倍": "3倍",
    "三十五": "35",
    "十八歳": "18歳",
    "十八": "18",
    "四十": "40",
}

def apply_replacements(text):
    """読み替え辞書に基づいてテキストを置換"""
    # 長い単語から順に置換することで、部分一致による誤変換（例: '三十五' の前に '三' が置換される）を防ぐ
    sorted_dict = sorted(REPLACEMENT_DICT.items(), key=lambda x: len(x[0]), reverse=True)
    
    for word, reading in sorted_dict:
        text = text.replace(word, reading)
    return text


# =============================================================================
# APIキー取得
# =============================================================================

print("\n🔑 OpenAI APIキーを確認中...")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    print("❌ 環境変数 OPENAI_API_KEY が設定されていません")
    OPENAI_API_KEY = input("APIキーを入力してください: ").strip()
    if not OPENAI_API_KEY:
        print("❌ APIキーが必要です")
        sys.exit(1)

# OpenAIクライアント初期化
try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI クライアント初期化完了")
except ImportError:
    print("❌ openaiライブラリがインストールされていません")
    print("   pip install openai を実行してください")
    sys.exit(1)

# pydub確認
try:
    from pydub import AudioSegment
    print("✅ pydub 読み込み完了")
except ImportError:
    print("❌ pydubライブラリがインストールされていません")
    print("   pip install pydub を実行してください")
    sys.exit(1)

# =============================================================================
# テキスト読み込み
# =============================================================================

print(f"\n📁 テキストファイルを読み込み中...")
print(f"   ファイル: {INPUT_FILE}")

encodings_to_try = ['utf-8', 'shift_jis', 'cp932', 'euc-jp']
novel_text = None

for encoding in encodings_to_try:
    try:
        with open(INPUT_FILE, 'r', encoding=encoding) as f:
            novel_text = f.read()
        print(f"✅ エンコーディング '{encoding}' で読み込み成功")
        break
    except UnicodeDecodeError:
        continue
    except FileNotFoundError:
        print(f"❌ ファイルが見つかりません: {INPUT_FILE}")
        sys.exit(1)

if novel_text is None:
    print("❌ ファイルのエンコーディングを検出できませんでした")
    sys.exit(1)

# テキストの前処理
novel_text = novel_text.strip()
novel_text = re.sub(r'\r\n', '\n', novel_text)
novel_text = re.sub(r'\n{3,}', '\n\n', novel_text)

# 読み替え処理を適用
print("\n📝 読み替え辞書を適用中...")
for word, reading in REPLACEMENT_DICT.items():
    if word in novel_text:
        print(f"   - {word} → {reading}")
novel_text = apply_replacements(novel_text)


paragraph_count = len([p for p in novel_text.split('\n\n') if p.strip()])

print_status_box([
    "📊 テキスト情報",
    f"   総文字数: {len(novel_text):,} 文字",
    f"   段落数: {paragraph_count} 段落",
])

# =============================================================================
# テキスト分割
# =============================================================================

def split_text_into_chunks(text: str, max_size: int = 4000) -> list:
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

chunks = split_text_into_chunks(novel_text, MAX_CHUNK_SIZE)
total_chars = sum(len(chunk) for chunk in chunks)

print_status_box([
    "📦 分割結果",
    f"   チャンク数: {len(chunks)}",
    f"   総文字数: {total_chars:,} 文字",
])

print("\n📄 チャンク詳細:")
for i, chunk in enumerate(chunks):
    preview = chunk[:30].replace('\n', ' ') + '...'
    print(f"   [{i+1:2d}] {len(chunk):,}文字 | {preview}")

# =============================================================================
# 音声生成
# =============================================================================

def generate_audio_chunk(text: str, chunk_index: int, output_dir: str) -> tuple:
    """1つのチャンクから音声を生成し、ファイルパスとサイズを返す"""
    output_path = os.path.join(output_dir, f"chunk_{chunk_index:03d}.mp3")
    
    params = {
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "input": text,
        "response_format": "mp3",
    }
    
    # gpt-4o-mini-ttsの場合、話し方の指示を追加
    if TTS_INSTRUCTIONS:
        params["instructions"] = TTS_INSTRUCTIONS
    
    response = client.audio.speech.create(**params)
    
    response.stream_to_file(output_path)
    file_size = os.path.getsize(output_path)
    
    return output_path, file_size

print("\n" + "=" * 60)
print("🎙️ 音声生成を開始します")
print("=" * 60)

print_status_box([
    "🎛️ 設定",
    f"   音声: {voice_desc}",
    f"   モデル: {TTS_MODEL}",
    f"   チャンク数: {len(chunks)}",
    f"   総文字数: {total_chars:,} 文字",
])

temp_dir = tempfile.mkdtemp()
audio_files = []
total_audio_size = 0

print("\n🔊 音声生成中...\n")

# ヘッダー表示
print("┌" + "─" * 78 + "┐")
print("│  #  │ 文字数  │ 累計文字  │ サイズ   │ 処理時間 │ 残り  │ 全体進捗            │")
print("├" + "─" * 78 + "┤")

start_time = time.time()
chunk_times = []
processed_chars = 0

for i, chunk in enumerate(chunks):
    chunk_start = time.time()
    
    try:
        audio_path, file_size = generate_audio_chunk(chunk, i + 1, temp_dir)
        audio_files.append(audio_path)
        total_audio_size += file_size
        
        chunk_time = time.time() - chunk_start
        chunk_times.append(chunk_time)
        
        # 文字数ベースの進捗計算
        processed_chars += len(chunk)
        char_progress_pct = processed_chars / total_chars * 100
        
        # 時間計算（文字数ベースで推定）
        elapsed = time.time() - start_time
        chars_per_sec = processed_chars / elapsed if elapsed > 0 else 0
        remaining_chars = total_chars - processed_chars
        remaining_time = remaining_chars / chars_per_sec if chars_per_sec > 0 else 0
        
        # 進捗バー（文字数ベース）
        bar_length = 15
        filled = int(bar_length * processed_chars // total_chars)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        # 行を表示
        size_kb = file_size / 1024
        print(f"│ {i+1:3d} │ {len(chunk):6,} │ {processed_chars:8,} │ {size_kb:6.1f}KB │ {chunk_time:6.1f}s │ {format_time(remaining_time):5s} │ {bar} {char_progress_pct:5.1f}% │")
        
        # API レート制限対策
        if i < len(chunks) - 1:
            time.sleep(REQUEST_INTERVAL)
            
    except Exception as e:
        print(f"\n❌ チャンク {i+1} でエラー: {str(e)}")
        sys.exit(1)

print("└" + "─" * 78 + "┘")

total_time = time.time() - start_time
total_size_mb = total_audio_size / (1024 * 1024)

print_status_box([
    "✅ 音声生成完了！",
    f"   生成チャンク: {len(audio_files)}",
    f"   総サイズ: {total_size_mb:.2f} MB",
    f"   処理時間: {format_time(total_time)}",
    f"   平均速度: {total_chars / total_time:.0f} 文字/秒",
])

# =============================================================================
# 音声結合
# =============================================================================

print("\n🔗 音声ファイルを結合中...")

output_dir = os.path.dirname(INPUT_FILE)
output_path = os.path.join(output_dir, OUTPUT_FILENAME)

print("\n結合進捗:")

combined = AudioSegment.from_mp3(audio_files[0])
print_progress_bar(1, len(audio_files), prefix='  進捗', suffix=f'1/{len(audio_files)} ファイル')

for i, audio_file in enumerate(audio_files[1:], start=2):
    segment = AudioSegment.from_mp3(audio_file)
    combined += segment
    print_progress_bar(i, len(audio_files), prefix='  進捗', suffix=f'{i}/{len(audio_files)} ファイル')

print()  # 改行

print("\n💾 ファイルを保存中...")
combined.export(output_path, format="mp3")

# 最終情報
final_size = os.path.getsize(output_path) / (1024 * 1024)
duration_sec = len(combined) / 1000
duration_min = int(duration_sec // 60)
duration_sec_rem = int(duration_sec % 60)

print("\n" + "=" * 60)
print("🎉 すべての処理が完了しました！")
print("=" * 60)

print_status_box([
    "📁 出力ファイル情報",
    f"   ファイル名: {OUTPUT_FILENAME}",
    f"   保存先: {output_path}",
    f"   ファイルサイズ: {final_size:.2f} MB",
    f"   再生時間: {duration_min}分{duration_sec_rem:02d}秒",
])

# クリーンアップ
print("\n🧹 一時ファイルを削除中...")
for audio_file in audio_files:
    try:
        os.remove(audio_file)
    except:
        pass
print("✅ クリーンアップ完了")

print("\n🎧 お楽しみください！")

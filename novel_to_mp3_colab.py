# =============================================================================
# 📚 日本語小説 → MP3 変換ツール（Google Colab用）
# OpenAI TTS API を使用して5000文字の日本語小説を音声化
# =============================================================================

# ============================================
# セル1: 必要なライブラリのインストール
# ============================================
# このセルを最初に実行してください

!pip install openai pydub tqdm -q
!apt-get install -y ffmpeg -qq

print("✅ ライブラリのインストール完了！")

# ============================================
# セル2: ライブラリのインポートと設定
# ============================================

import os
import time
import re
from pathlib import Path
from google.colab import userdata, files
from openai import OpenAI
from pydub import AudioSegment
import tempfile
from tqdm.notebook import tqdm
import ipywidgets as widgets
from IPython.display import display, clear_output

# Colabシークレットから API キーを取得
try:
    OPENAI_API_KEY = userdata.get('OPENAI_API_KEY')
    if not OPENAI_API_KEY:
        raise ValueError("API キーが空です")
    print("✅ OpenAI API キーを取得しました")
except Exception as e:
    print(f"❌ エラー: Colabシークレットから 'OPENAI_API_KEY' を取得できませんでした")
    print("📝 設定方法: 左サイドバー 🔑 → 'OPENAI_API_KEY' を追加")
    raise SystemExit("API キーを設定してから再実行してください")

# OpenAI クライアントの初期化
client = OpenAI(api_key=OPENAI_API_KEY)

# ============================================
# 🎙️ 音声タイプの選択
# ============================================

# 利用可能な音声オプション
VOICE_OPTIONS = {
    "alloy": "🎭 Alloy - 中性的でバランスの取れた、落ち着いた声",
    "echo": "🎤 Echo - 落ち着いた、やや深みのある男性的な声",
    "fable": "📖 Fable - 表現力豊かで、物語の朗読に向いた声",
    "onyx": "💪 Onyx - 力強く、自信に満ちた男性的な声",
    "nova": "✨ Nova - 明るく、親しみやすい女性的な声",
    "shimmer": "💎 Shimmer - 澄んだ、知的な印象を与える女性的な声"
}

print("\n" + "=" * 50)
print("🎙️ 音声タイプを選択してください")
print("=" * 50)

for voice_id, description in VOICE_OPTIONS.items():
    print(f"  {description}")

# ドロップダウンで選択
voice_dropdown = widgets.Dropdown(
    options=[(desc, voice_id) for voice_id, desc in VOICE_OPTIONS.items()],
    value='nova',
    description='音声:',
    style={'description_width': 'initial'},
    layout=widgets.Layout(width='500px')
)

# モデル選択
model_dropdown = widgets.Dropdown(
    options=[
        ('tts-1 (標準品質・高速)', 'tts-1'),
        ('tts-1-hd (高品質)', 'tts-1-hd')
    ],
    value='tts-1',
    description='モデル:',
    style={'description_width': 'initial'},
    layout=widgets.Layout(width='500px')
)

# 選択確認ボタン
confirm_button = widgets.Button(
    description='✅ この設定で続行',
    button_style='success',
    layout=widgets.Layout(width='200px')
)

# 選択結果を保存する変数
selected_voice = 'nova'
selected_model = 'tts-1'
selection_confirmed = False

def on_confirm_click(b):
    global selected_voice, selected_model, selection_confirmed
    selected_voice = voice_dropdown.value
    selected_model = model_dropdown.value
    selection_confirmed = True
    clear_output(wait=True)
    print(f"✅ 設定完了!")
    print(f"   🎙️ 音声: {VOICE_OPTIONS[selected_voice]}")
    print(f"   📀 モデル: {selected_model}")

confirm_button.on_click(on_confirm_click)

# ウィジェットを表示
display(widgets.VBox([
    widgets.HTML("<h3>🎛️ 音声設定</h3>"),
    voice_dropdown,
    model_dropdown,
    widgets.HTML("<br>"),
    confirm_button
]))

# ============================================
# セル3: 設定の確定と定数
# ============================================

# 選択された値を使用
TTS_MODEL = selected_model
TTS_VOICE = selected_voice
MAX_CHUNK_SIZE = 4000         # 最大チャンクサイズ（文字数）
REQUEST_INTERVAL = 0.5        # API リクエスト間隔（秒）

print(f"\n📋 使用する設定:")
print(f"   🎙️ 音声: {VOICE_OPTIONS[TTS_VOICE]}")
print(f"   📀 モデル: {TTS_MODEL}")
print(f"   📏 最大チャンクサイズ: {MAX_CHUNK_SIZE}文字")

# ============================================
# セル4: テキストファイルのアップロードと読み込み
# ============================================

print("📁 テキストファイルをアップロードしてください（.txt形式）")
uploaded = files.upload()

if not uploaded:
    raise ValueError("❌ ファイルがアップロードされませんでした")

# アップロードされたファイルを読み込み
filename = list(uploaded.keys())[0]
print(f"📄 アップロードされたファイル: {filename}")

# エンコーディングを自動検出して読み込み
encodings_to_try = ['utf-8', 'shift_jis', 'cp932', 'euc-jp']
novel_text = None

for encoding in encodings_to_try:
    try:
        novel_text = uploaded[filename].decode(encoding)
        print(f"✅ エンコーディング '{encoding}' で読み込み成功")
        break
    except UnicodeDecodeError:
        continue

if novel_text is None:
    raise ValueError("❌ ファイルのエンコーディングを検出できませんでした")

# テキストの前処理（余分な空白や改行を整理）
novel_text = novel_text.strip()
novel_text = re.sub(r'\r\n', '\n', novel_text)  # 改行コードを統一
novel_text = re.sub(r'\n{3,}', '\n\n', novel_text)  # 3つ以上の改行を2つに

print(f"📊 テキスト情報:")
print(f"   - 総文字数: {len(novel_text):,} 文字")
print(f"   - 段落数: {len([p for p in novel_text.split('\n\n') if p.strip()])} 段落")

# ============================================
# セル5: テキストを段落単位で分割
# ============================================

def split_text_into_chunks(text: str, max_size: int = 4000) -> list[str]:
    """
    テキストを段落単位で分割し、各チャンクが max_size 以下になるようにする
    
    Args:
        text: 分割するテキスト
        max_size: 1チャンクの最大文字数
    
    Returns:
        分割されたテキストチャンクのリスト
    """
    # 段落で分割（空行で区切り）
    paragraphs = text.split('\n\n')
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        # 段落自体が長すぎる場合は、文単位で分割
        if len(paragraph) > max_size:
            # 現在のチャンクを保存
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # 長い段落を文単位で分割
            sentences = re.split(r'([。！？])', paragraph)
            temp_chunk = ""
            
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                # 句読点を追加（存在する場合）
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
            # 現在のチャンクに段落を追加できるかチェック
            test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
            
            if len(test_chunk) <= max_size:
                current_chunk = test_chunk
            else:
                # 現在のチャンクを保存し、新しいチャンクを開始
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph
    
    # 最後のチャンクを追加
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks

# テキストを分割
chunks = split_text_into_chunks(novel_text, MAX_CHUNK_SIZE)

print(f"\n📦 分割結果:")
print(f"   - チャンク数: {len(chunks)}")
for i, chunk in enumerate(chunks):
    print(f"   - チャンク {i+1}: {len(chunk):,} 文字")

# ============================================
# セル6: TTS API で音声生成（プログレスバー付き）
# ============================================

def generate_audio_chunk(text: str, chunk_index: int, output_dir: str, voice: str, model: str) -> str:
    """
    1つのテキストチャンクから音声ファイルを生成
    
    Args:
        text: 音声化するテキスト
        chunk_index: チャンクの番号
        output_dir: 出力ディレクトリ
        voice: 使用する音声
        model: 使用するモデル
    
    Returns:
        生成された音声ファイルのパス
    """
    output_path = os.path.join(output_dir, f"chunk_{chunk_index:03d}.mp3")
    
    try:
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format="mp3"
        )
        
        # ファイルに保存
        response.stream_to_file(output_path)
        return output_path
        
    except Exception as e:
        raise RuntimeError(f"チャンク {chunk_index} の音声生成に失敗: {str(e)}")

def generate_all_audio(chunks: list[str], voice: str, model: str) -> list[str]:
    """
    全てのチャンクから音声ファイルを生成（プログレスバー付き）
    
    Args:
        chunks: テキストチャンクのリスト
        voice: 使用する音声
        model: 使用するモデル
    
    Returns:
        生成された音声ファイルパスのリスト
    """
    # 一時ディレクトリを作成
    temp_dir = tempfile.mkdtemp()
    audio_files = []
    
    total_chars = sum(len(chunk) for chunk in chunks)
    processed_chars = 0
    
    print(f"\n🎙️ 音声生成を開始します...")
    print(f"   🎤 使用音声: {VOICE_OPTIONS[voice]}")
    print(f"   📀 モデル: {model}")
    print(f"   📁 保存先: {temp_dir}")
    print(f"   📊 総文字数: {total_chars:,} 文字 / {len(chunks)} チャンク\n")
    
    # プログレスバーを作成
    progress_bar = tqdm(
        total=len(chunks),
        desc="🔊 音声生成中",
        unit="チャンク",
        bar_format='{l_bar}{bar:30}{r_bar}',
        colour='green'
    )
    
    # 詳細情報表示用
    status_output = widgets.Output()
    display(status_output)
    
    start_time = time.time()
    
    for i, chunk in enumerate(chunks):
        chunk_start_time = time.time()
        
        try:
            audio_path = generate_audio_chunk(chunk, i + 1, temp_dir, voice, model)
            audio_files.append(audio_path)
            processed_chars += len(chunk)
            
            # 経過時間と推定残り時間を計算
            elapsed = time.time() - start_time
            avg_time_per_chunk = elapsed / (i + 1)
            remaining_chunks = len(chunks) - (i + 1)
            eta = avg_time_per_chunk * remaining_chunks
            
            # ステータス更新
            with status_output:
                clear_output(wait=True)
                print(f"   ✅ チャンク {i+1}/{len(chunks)} 完了 ({len(chunk):,}文字)")
                print(f"   📊 進捗: {processed_chars:,}/{total_chars:,} 文字 ({processed_chars/total_chars*100:.1f}%)")
                print(f"   ⏱️ 経過時間: {int(elapsed//60)}分{int(elapsed%60)}秒")
                print(f"   ⏳ 残り時間: 約{int(eta//60)}分{int(eta%60)}秒")
            
            progress_bar.update(1)
            
            # API レート制限対策: リクエスト間隔を空ける
            if i < len(chunks) - 1:
                time.sleep(REQUEST_INTERVAL)
                
        except Exception as e:
            progress_bar.close()
            print(f"\n   ❌ チャンク {i+1} でエラー: {str(e)}")
            raise
    
    progress_bar.close()
    
    total_time = time.time() - start_time
    print(f"\n✅ 全 {len(audio_files)} チャンクの音声生成が完了しました！")
    print(f"   ⏱️ 総処理時間: {int(total_time//60)}分{int(total_time%60)}秒")
    
    return audio_files

# 音声を生成
audio_files = generate_all_audio(chunks, TTS_VOICE, TTS_MODEL)

# ============================================
# セル7: 音声ファイルの結合とダウンロード
# ============================================

def combine_audio_files(audio_files: list[str], output_path: str) -> str:
    """
    複数の音声ファイルを1つに結合（プログレスバー付き）
    
    Args:
        audio_files: 結合する音声ファイルパスのリスト
        output_path: 出力ファイルパス
    
    Returns:
        結合された音声ファイルのパス
    """
    print(f"\n🔗 音声ファイルを結合しています...")
    
    if not audio_files:
        raise ValueError("結合する音声ファイルがありません")
    
    # 最初のファイルを読み込み
    combined = AudioSegment.from_mp3(audio_files[0])
    
    # プログレスバーを作成
    progress_bar = tqdm(
        total=len(audio_files),
        desc="🔗 結合中",
        unit="ファイル",
        bar_format='{l_bar}{bar:30}{r_bar}',
        colour='blue'
    )
    progress_bar.update(1)
    
    # 残りのファイルを結合
    for audio_file in audio_files[1:]:
        segment = AudioSegment.from_mp3(audio_file)
        combined += segment
        progress_bar.update(1)
    
    progress_bar.close()
    
    # 結合したファイルを保存
    print("💾 ファイルを保存中...")
    combined.export(output_path, format="mp3")
    
    # ファイルサイズを取得
    file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB
    duration = len(combined) / 1000  # 秒
    
    print(f"\n✅ 結合完了！")
    print(f"   📁 ファイル名: {output_path}")
    print(f"   📊 ファイルサイズ: {file_size:.2f} MB")
    print(f"   ⏱️ 再生時間: {int(duration // 60)}分 {int(duration % 60)}秒")
    
    return output_path

# 音声を結合
OUTPUT_FILENAME = "novel_full.mp3"
final_audio_path = combine_audio_files(audio_files, OUTPUT_FILENAME)

# ダウンロード
print(f"\n📥 ダウンロードを開始します...")
files.download(final_audio_path)

print("\n" + "=" * 50)
print("🎉 すべての処理が完了しました！")
print("=" * 50)

# ============================================
# セル8: クリーンアップ（オプション）
# ============================================

# 一時ファイルを削除する場合は以下のコメントを解除
# import shutil
# for audio_file in audio_files:
#     os.remove(audio_file)
# print("🧹 一時ファイルを削除しました")

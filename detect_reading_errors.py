# =============================================================================
# TTS読み間違い検出ツール
# TTS → Whisper文字起こし → 原文比較で読み間違いを自動検出
# =============================================================================

import os
import time
import re
import sys
import tempfile
import difflib
from pathlib import Path

# Windows対応: UTF-8出力設定
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# =============================================================================
# 設定
# =============================================================================

INPUT_FILE = r"c:\Users\natak\Documents\Novel\ひより01_元.txt"
OUTPUT_DIR = r"c:\Users\natak\Documents\Novel"

TTS_MODEL = "tts-1"
TTS_VOICE = "fable"  # 物語向け
MAX_CHUNK_SIZE = 4000
REQUEST_INTERVAL = 0.5

# =============================================================================
# 初期化
# =============================================================================

print("\n" + "=" * 70)
print("📚 TTS読み間違い検出ツール")
print("=" * 70)

# APIキー取得
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("❌ 環境変数 OPENAI_API_KEY が設定されていません")
    OPENAI_API_KEY = input("APIキーを入力してください: ").strip()
    if not OPENAI_API_KEY:
        print("❌ APIキーが必要です")
        sys.exit(1)

try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    print("✅ OpenAI クライアント初期化完了")
except ImportError:
    print("❌ openaiライブラリがインストールされていません")
    print("   pip install openai を実行してください")
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

print(f"📊 テキスト情報: {len(novel_text):,} 文字")

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

print(f"📦 {len(chunks)} チャンクに分割")

# =============================================================================
# ステップ1: TTS音声生成
# =============================================================================

print("\n" + "=" * 70)
print("🎙️ ステップ1: TTS音声生成")
print("=" * 70)

temp_dir = tempfile.mkdtemp()
audio_files = []
processed_chars = 0

for i, chunk in enumerate(chunks):
    output_path = os.path.join(temp_dir, f"chunk_{i+1:03d}.mp3")
    
    try:
        response = client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=chunk,
            response_format="mp3"
        )
        response.stream_to_file(output_path)
        audio_files.append(output_path)
        
        processed_chars += len(chunk)
        progress = processed_chars / total_chars * 100
        print(f"   [{i+1}/{len(chunks)}] TTS生成完了 ({len(chunk):,}文字) - 進捗: {progress:.1f}%")
        
        if i < len(chunks) - 1:
            time.sleep(REQUEST_INTERVAL)
            
    except Exception as e:
        print(f"❌ チャンク {i+1} でエラー: {str(e)}")
        sys.exit(1)

print(f"✅ 音声生成完了: {len(audio_files)} ファイル")

# =============================================================================
# ステップ2: Whisper文字起こし
# =============================================================================

print("\n" + "=" * 70)
print("📝 ステップ2: Whisper文字起こし")
print("=" * 70)

transcribed_texts = []

for i, audio_path in enumerate(audio_files):
    try:
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ja",
                response_format="text"
            )
        
        transcribed_texts.append(transcript)
        progress = (i + 1) / len(audio_files) * 100
        print(f"   [{i+1}/{len(audio_files)}] 文字起こし完了 - 進捗: {progress:.1f}%")
        
        if i < len(audio_files) - 1:
            time.sleep(REQUEST_INTERVAL)
            
    except Exception as e:
        print(f"❌ チャンク {i+1} でエラー: {str(e)}")
        transcribed_texts.append("")

print(f"✅ 文字起こし完了: {len(transcribed_texts)} チャンク")

# =============================================================================
# ステップ3: 差分比較・読み間違い検出
# =============================================================================

print("\n" + "=" * 70)
print("🔍 ステップ3: 読み間違い検出")
print("=" * 70)

def normalize_text(text):
    """比較用にテキストを正規化"""
    text = re.sub(r'\s+', '', text)  # 空白除去
    text = text.replace('、', '').replace('。', '')  # 句読点除去
    text = text.replace('「', '').replace('」', '')  # 括弧除去
    text = text.replace('！', '').replace('？', '')
    text = text.replace('…', '').replace('......', '')
    return text

def find_differences(original, transcribed, chunk_num):
    """2つのテキストの差分を検出"""
    differences = []
    
    # 文単位で比較
    orig_sentences = re.split(r'[。！？\n]', original)
    trans_sentences = re.split(r'[。！？\n]', transcribed)
    
    orig_sentences = [s.strip() for s in orig_sentences if s.strip()]
    trans_sentences = [s.strip() for s in trans_sentences if s.strip()]
    
    # 各原文に対して最も近い文字起こし文を探す
    for orig in orig_sentences:
        if len(orig) < 5:  # 短すぎる文はスキップ
            continue
            
        orig_norm = normalize_text(orig)
        best_match = None
        best_ratio = 0
        
        for trans in trans_sentences:
            trans_norm = normalize_text(trans)
            ratio = difflib.SequenceMatcher(None, orig_norm, trans_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = trans
        
        # 80%未満の一致率なら差分として記録
        if best_ratio < 0.95 and best_match:
            differences.append({
                'chunk': chunk_num,
                'original': orig,
                'transcribed': best_match,
                'ratio': best_ratio
            })
    
    return differences

all_differences = []

for i, (orig_chunk, trans_chunk) in enumerate(zip(chunks, transcribed_texts)):
    diffs = find_differences(orig_chunk, trans_chunk, i + 1)
    all_differences.extend(diffs)

# =============================================================================
# レポート出力
# =============================================================================

print(f"\n📊 検出結果: {len(all_differences)} 箇所の差異")

report_path = os.path.join(OUTPUT_DIR, "reading_errors_report.txt")

with open(report_path, 'w', encoding='utf-8') as f:
    f.write("=" * 80 + "\n")
    f.write("📚 TTS読み間違い検出レポート\n")
    f.write(f"入力ファイル: {INPUT_FILE}\n")
    f.write(f"音声: {TTS_VOICE} / モデル: {TTS_MODEL}\n")
    f.write(f"検出日時: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 80 + "\n\n")
    
    f.write(f"検出された差異: {len(all_differences)} 箇所\n\n")
    f.write("-" * 80 + "\n\n")
    
    for i, diff in enumerate(all_differences, 1):
        f.write(f"【{i}】チャンク {diff['chunk']} (一致率: {diff['ratio']*100:.1f}%)\n")
        f.write(f"  原文: {diff['original']}\n")
        f.write(f"  認識: {diff['transcribed']}\n")
        f.write("\n")

print(f"\n📄 レポート出力: {report_path}")

# 画面にも主要な差異を表示
print("\n" + "=" * 70)
print("🔍 主な読み間違い候補（一致率90%未満）")
print("=" * 70)

major_diffs = [d for d in all_differences if d['ratio'] < 0.9]

if major_diffs:
    for i, diff in enumerate(major_diffs[:20], 1):  # 最大20件表示
        print(f"\n【{i}】一致率: {diff['ratio']*100:.1f}%")
        print(f"  原文: {diff['original'][:50]}...")
        print(f"  認識: {diff['transcribed'][:50]}...")
else:
    print("\n✅ 大きな読み間違いは検出されませんでした！")

# クリーンアップ
print("\n🧹 一時ファイルを削除中...")
for audio_file in audio_files:
    try:
        os.remove(audio_file)
    except:
        pass

print("\n" + "=" * 70)
print("🎉 処理完了！")
print("=" * 70)
print(f"\n詳細は {report_path} を確認してください。")

# =============================================================================
# TTS読み間違い検出ツール
# エンジン切り替え対応:
#   --engine whisper : TTS → Whisper文字起こし → 原文比較（従来方式）
#   --engine gemini  : MP3 + 原文 → Gemini直接比較（高精度）
#
# 使い方:
#   python detect_reading_errors.py novels/小説.txt                  # 新規TTS生成
#   python detect_reading_errors.py novels/小説.txt --mp3 mp3/既存.mp3  # 既存MP3から
# =============================================================================

import os
import time
import re
import sys
import argparse
import tempfile
import difflib
import json
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# .envファイルを読み込む
load_dotenv()

# Windows対応: UTF-8出力設定
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

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

# =============================================================================
# ルビ処理・読みチェック
# =============================================================================

def strip_ruby(text):
    """漢字【よみ】からルビ部分を除去して漢字だけ残す"""
    return re.sub(r'【[^】]*】', '', text)

def extract_ruby_pairs(text):
    """漢字【よみ】のペアを抽出"""
    # パターン: 漢字部分【よみがな】
    return re.findall(r'([一-龥]+)【([^】]+)】', text)

def check_ruby_readings(ruby_pairs):
    """ルビの読みが正しいかJanomeでチェック"""
    reading_errors = []
    try:
        from janome.tokenizer import Tokenizer
        tokenizer = Tokenizer()
    except ImportError:
        return reading_errors  # Janomeなければスキップ
    
    for kanji, whisper_reading in ruby_pairs:
        # Janomeで正しい読みを取得
        tokens = tokenizer.tokenize(kanji)
        expected_parts = []
        for token in tokens:
            reading = token.reading if token.reading != '*' else token.surface
            expected_parts.append(reading)
        expected_reading = ''.join(expected_parts)
        
        # カタカナ→ひらがな変換して比較
        expected_hira = kata_to_hira(expected_reading)
        whisper_hira = kata_to_hira(whisper_reading)
        
        if expected_hira != whisper_hira and len(kanji) >= 2:
            reading_errors.append({
                'kanji': kanji,
                'whisper_reading': whisper_hira,
                'expected_reading': expected_hira
            })
    
    return reading_errors

def kata_to_hira(text):
    """カタカナをひらがなに変換"""
    return ''.join(
        chr(ord(ch) - 96) if 'ァ' <= ch <= 'ヶ' else ch
        for ch in text
    )

# =============================================================================
# 比較・検出
# =============================================================================

def normalize_text(text):
    """比較用にテキストを正規化"""
    text = strip_ruby(text)  # ルビ除去
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
        
        # 95%未満の一致率なら差分として記録
        if best_ratio < 0.95 and best_match:
            differences.append({
                'chunk': chunk_num,
                'original': orig,
                'transcribed': best_match,
                'ratio': best_ratio
            })
    
    return differences

# =============================================================================
# Geminiエンジン: MP3 + 原文を直接渡して読み間違い検出
# =============================================================================

def _run_gemini_mode(gemini_client, input_file, mp3_file, novel_text, output_dir, gemini_model=None):
    """Geminiに音声+原文を渡して読み間違いを直接検出する（モデル自動フォールバック対応）"""
    from google import genai
    from google.genai import types
    
    if not mp3_file:
        print("❌ Geminiモードには --mp3 が必要です")
        sys.exit(1)
    
    print("\n" + "=" * 70)
    print("🤖 Geminiモード: 音声と原文を直接比較")
    print("=" * 70)
    
    mp3_path = Path(mp3_file)
    if not mp3_path.exists():
        print(f"❌ MP3が見つかりません: {mp3_file}")
        sys.exit(1)
    
    mp3_size_mb = mp3_path.stat().st_size / (1024 * 1024)
    print(f"   MP3: {mp3_path.name} ({mp3_size_mb:.1f}MB)")
    print(f"   原文: {len(novel_text):,}文字")
    
    # MP3が大きい場合はチャンク分割
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(mp3_file)
        total_sec = len(audio) / 1000
        print(f"   再生時間: {total_sec:.0f}秒")
    except Exception as e:
        print(f"⚠️ pydub読み込みエラー: {e}")
        total_sec = 0
    
    # Geminiに渡すプロンプト
    prompt = f"""あなたは日本語TTS音声の品質チェック専門家です。
添付のMP3音声ファイルを注意深く聴き、以下の「原文テキスト」と比較してください。

━━━━━━━━━━━━━━━━━━━━━━
■ タスク
━━━━━━━━━━━━━━━━━━━━━━
音声が原文の漢字を **間違った読み方** で読んでいる箇所を特定してください。

━━━━━━━━━━━━━━━━━━━━━━
■ 検出すべきエラー（＝報告対象）
━━━━━━━━━━━━━━━━━━━━━━
1. **漢字の読み間違い**: 音声が漢字を別の読みで読んでいる
   例: 「進学校」を「しんがくこう」ではなく「しんがっこう」と読む
   例: 「取り柄」を「とりえ」ではなく別の読みで読む
   例: 「初老」を「しょろう」ではなく別の読みで読む
2. **文章の読み飛ばし**: 原文にある文が丸ごと読まれていない
3. **文章の追加**: 原文にない文が音声に含まれている

━━━━━━━━━━━━━━━━━━━━━━
■ エラーではない（＝報告しないでください）
━━━━━━━━━━━━━━━━━━━━━━
以下は正常であり、報告してはいけません：
- 人名が正しく読まれている場合（例:「桃田」→「ももた」は正しい）
- 固有名詞が一般的な読みで読まれている場合
- 漢字↔ひらがなの表記揺れ（「分かった」と「わかった」は同じ）
- 句読点・カッコの有無の違い
- 「……」等の記号表現
- 数字表記の違い（「3」と「三」は同じ）
- 音声の抑揚やイントネーションの問題

━━━━━━━━━━━━━━━━━━━━━━
■ 重要な注意
━━━━━━━━━━━━━━━━━━━━━━
- **本当に間違っている箇所だけ** を報告してください
- 確信が持てない場合は報告しないでください
- 正しい読みを「間違い」として報告するのはNGです

━━━━━━━━━━━━━━━━━━━━━━
■ 出力形式
━━━━━━━━━━━━━━━━━━━━━━
JSON配列で返してください。読み間違いがない場合は空配列 [] を返してください。
```json
[
  {{"original": "原文の該当箇所（前後の文脈含む）", "spoken": "実際に音声で聞こえた内容", "type": "エラー種別", "note": "何が間違いなのか具体的に"}},
]
```
type: misread（読み間違い）, skipped（読み飛ばし）, added（追加読み）

━━━━━━━━━━━━━━━━━━━━━━
■ 原文テキスト
━━━━━━━━━━━━━━━━━━━━━━
{novel_text}
"""
    
    # MP3をアップロードしてGeminiに送信
    # フォールバック対応: 指定モデル → 候補モデルの順に試行
    FALLBACK_MODELS = ["gemini-2.0-flash-lite", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]
    
    if gemini_model:
        models_to_try = [gemini_model]
    else:
        models_to_try = FALLBACK_MODELS
    
    all_errors = []
    
    # MP3ファイルを読み込み
    with open(mp3_file, "rb") as f:
        audio_data = f.read()
    
    success = False
    for model_name in models_to_try:
        print(f"\n⏳ Gemini ({model_name}) に音声を送信して分析中...")
        
        try:
            response = gemini_client.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=audio_data, mime_type="audio/mpeg"),
                            types.Part.from_text(text=prompt),
                        ],
                    ),
                ],
            )
            
            result_text = response.text.strip()
            
            # JSON抽出
            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
            if json_match:
                all_errors = json.loads(json_match.group())
                print(f"\n📊 Gemini検出結果 ({model_name}): {len(all_errors)} 件の読み間違い")
            else:
                print(f"\n📊 Gemini検出結果 ({model_name}): 読み間違いなし")
            
            success = True
            break  # 成功したらループ終了
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                print(f"   ⚠️ {model_name}: クォータ超過、次のモデルを試行...")
                continue
            else:
                print(f"\n❌ Gemini APIエラー ({model_name}): {e}")
                print("   💡 --engine whisper で従来方式に切り替えできます")
                sys.exit(1)
    
    if not success:
        print(f"\n❌ すべてのGeminiモデルでクォータ超過です")
        print("   💡 --engine whisper で従来方式に切り替えできます")
        print("   💡 または有料プランへの切り替えをご検討ください")
        print("   💡 https://ai.google.dev/gemini-api/docs/rate-limits")
        sys.exit(1)
    
    # =================================================================
    # レポート出力
    # =================================================================
    
    report_path = os.path.join(output_dir, "reading_errors_report.txt")
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("📚 TTS読み間違い検出レポート（Geminiエンジン）\n")
        f.write(f"入力ファイル: {input_file}\n")
        f.write(f"MP3ファイル: {mp3_file}\n")
        f.write(f"検出日時: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        f.write(f"検出された読み間違い: {len(all_errors)} 箇所\n\n")
        f.write("-" * 80 + "\n\n")
        
        for i, err in enumerate(all_errors, 1):
            original = err.get("original", "?")
            spoken = err.get("spoken", "?")
            err_type = err.get("type", "?")
            note = err.get("note", "")
            
            type_label = {
                "misread": "読み間違い",
                "skipped": "読み飛ばし",
                "added": "追加読み",
                "mispronounced": "発音エラー"
            }.get(err_type, err_type)
            
            f.write(f"【{i}】{type_label}\n")
            f.write(f"  原文: {original}\n")
            f.write(f"  音声: {spoken}\n")
            if note:
                f.write(f"  備考: {note}\n")
            f.write("\n")
    
    print(f"\n📄 レポート出力: {report_path}")
    
    # 画面にも表示
    print("\n" + "=" * 70)
    print("🔍 検出された読み間違い")
    print("=" * 70)
    
    if all_errors:
        for i, err in enumerate(all_errors, 1):
            original = err.get("original", "?")
            spoken = err.get("spoken", "?")
            note = err.get("note", "")
            print(f"\n【{i}】原文: {original}")
            print(f"      音声: {spoken}")
            if note:
                print(f"      備考: {note}")
    else:
        print("\n✅ 読み間違いは検出されませんでした！")
    
    print("\n" + "=" * 70)
    print("🎉 Gemini分析完了！")
    print("=" * 70)
    print(f"\n詳細は {report_path} を確認してください。")


# =============================================================================
# メイン処理
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="📚 TTS読み間違い検出ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方の例:
  python detect_reading_errors.py novels/小説.txt                     # 新規TTS生成して比較
  python detect_reading_errors.py novels/小説.txt --mp3 mp3/既存.mp3  # 既存MP3のWhisper比較
        """
    )
    
    parser.add_argument("input", help="入力テキストファイルのパス")
    parser.add_argument("--mp3", help="既存MP3ファイルのパス（指定時はTTS生成をスキップ）")
    parser.add_argument("--voice", default="fable", help="TTS音声タイプ (デフォルト: fable)")
    parser.add_argument("--model", default="tts-1", help="TTSモデル (デフォルト: tts-1)")
    parser.add_argument("--chunk-size", type=int, default=4000, help="チャンク最大サイズ (デフォルト: 4000)")
    parser.add_argument("--engine", choices=["whisper", "gemini"], default="gemini", help="検出エンジン (デフォルト: gemini)")
    parser.add_argument("--gemini-model", default=None, help="Geminiモデル名 (デフォルト: 自動選択)")
    
    args = parser.parse_args()
    
    INPUT_FILE = args.input
    MP3_FILE = args.mp3
    TTS_MODEL = args.model
    TTS_VOICE = args.voice
    MAX_CHUNK_SIZE = args.chunk_size
    ENGINE = args.engine
    OUTPUT_DIR = str(Path(__file__).parent)
    
    # バナー
    print("\n" + "=" * 70)
    print("📚 TTS読み間違い検出ツール")
    if ENGINE == "gemini":
        print("   エンジン: Gemini（音声直接比較）")
    elif MP3_FILE:
        print("   エンジン: Whisper（既存MP3比較）")
    else:
        print("   エンジン: Whisper（TTS生成→比較）")
    print("=" * 70)
    
    # APIキー取得
    client = None
    gemini_client = None
    
    if ENGINE == "gemini":
        GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            print("❌ GEMINI_API_KEY が設定されていません")
            sys.exit(1)
        try:
            from google import genai
            gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            print("✅ Gemini クライアント初期化完了")
        except ImportError:
            print("❌ google-genaiがインストールされていません")
            print("   pip install google-genai を実行してください")
            sys.exit(1)
    
    # Whisper用 or TTS生成用にOpenAIクライアントも準備
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            print("✅ OpenAI クライアント初期化完了")
        except ImportError:
            if ENGINE == "whisper":
                print("❌ openaiライブラリがインストールされていません")
                sys.exit(1)
    elif ENGINE == "whisper":
        print("❌ Whisperモードには OPENAI_API_KEY が必要です")
        sys.exit(1)
    
    # =================================================================
    # テキスト読み込み
    # =================================================================
    
    print(f"\n📁 テキストファイルを読み込み中...")
    print(f"   ファイル: {INPUT_FILE}")
    
    if not os.path.exists(INPUT_FILE):
        print(f"❌ ファイルが見つかりません: {INPUT_FILE}")
        sys.exit(1)
    
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
    
    if novel_text is None:
        print("❌ ファイルのエンコーディングを検出できませんでした")
        sys.exit(1)
    
    # テキストの前処理
    novel_text = novel_text.strip()
    novel_text = re.sub(r'\r\n', '\n', novel_text)
    novel_text = re.sub(r'\n{3,}', '\n\n', novel_text)
    
    print(f"📊 テキスト情報: {len(novel_text):,} 文字")
    
    # テキスト分割
    chunks = split_text_into_chunks(novel_text, MAX_CHUNK_SIZE)
    total_chars = sum(len(chunk) for chunk in chunks)
    total_chunks = len(chunks)
    print(f"📦 {total_chunks} チャンクに分割")
    
    # =================================================================
    # エンジン分岐
    # =================================================================
    
    if ENGINE == "gemini":
        # =============================================================
        # Geminiモード: MP3 + 原文を直接Geminiに渡して読み間違い検出
        # =============================================================
        _run_gemini_mode(gemini_client, INPUT_FILE, MP3_FILE, novel_text, OUTPUT_DIR, gemini_model=args.gemini_model)
        return
    
    # =================================================================
    # Whisperモード（従来方式）
    # ステップ1: 音声準備（TTS生成 or 既存MP3分割）
    # =================================================================
    
    audio_files_map = {}
    
    if MP3_FILE:
        # --- 既存MP3モード ---
        print("\n" + "=" * 70)
        print("📂 ステップ1: 既存MP3をチャンク分割")
        print("=" * 70)
        
        if not os.path.exists(MP3_FILE):
            print(f"❌ MP3ファイルが見つかりません: {MP3_FILE}")
            sys.exit(1)
        
        try:
            from pydub import AudioSegment
        except ImportError:
            print("❌ pydubが必要です: pip install pydub")
            sys.exit(1)
        
        print(f"   MP3: {MP3_FILE}")
        audio = AudioSegment.from_mp3(MP3_FILE)
        total_duration_ms = len(audio)
        total_duration_sec = total_duration_ms / 1000
        print(f"   再生時間: {total_duration_sec:.0f}秒")
        
        # テキストのチャンク文字数比率に基づいてMP3を分割
        # （各チャンクの文字数に比例して時間配分）
        temp_dir = tempfile.mkdtemp()
        chunk_char_counts = [len(c) for c in chunks]
        total_char_count = sum(chunk_char_counts)
        
        current_ms = 0
        for i, char_count in enumerate(chunk_char_counts):
            # このチャンクに割り当てる時間（文字数比率）
            chunk_duration_ms = int(total_duration_ms * char_count / total_char_count)
            end_ms = min(current_ms + chunk_duration_ms, total_duration_ms)
            
            chunk_audio = audio[current_ms:end_ms]
            output_path = os.path.join(temp_dir, f"chunk_{i+1:03d}.mp3")
            chunk_audio.export(output_path, format="mp3")
            audio_files_map[i] = output_path
            current_ms = end_ms
            
            pct = (i + 1) / total_chunks * 100
            print(f"\r   ✂️ 分割中: [{i+1}/{total_chunks}] {pct:.0f}%", end='', flush=True)
        
        print("\n✅ MP3分割完了")
    
    else:
        # --- 新規TTS生成モード ---
        print("\n" + "=" * 70)
        print("🎙️ ステップ1: TTS音声生成 (Speed Boost)")
        print("=" * 70)
        
        temp_dir = tempfile.mkdtemp()
        completed_tts = 0
        
        def tts_task(chunk, i):
            output_path = os.path.join(temp_dir, f"chunk_{i+1:03d}.mp3")
            try:
                response = client.audio.speech.create(
                    model=TTS_MODEL,
                    voice=TTS_VOICE,
                    input=chunk,
                    response_format="mp3"
                )
                response.stream_to_file(output_path)
                return i, output_path, None
            except Exception as e:
                return i, None, str(e)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(tts_task, chunk, i) for i, chunk in enumerate(chunks)]
            for future in as_completed(futures):
                i, path, error = future.result()
                if error:
                    print(f"❌ チャンク {i+1} でエラー: {error}")
                    continue
                audio_files_map[i] = path
                completed_tts += 1
                pct = completed_tts / total_chunks * 100
                print(f"\r   🚀 TTS生成中: [{completed_tts}/{total_chunks}] {pct:.1f}%", end='', flush=True)
        
        print("\n✅ 音声生成完了")
    
    audio_files = [audio_files_map[i] for i in range(total_chunks) if i in audio_files_map]
    
    # =================================================================
    # ステップ2: Whisper文字起こし (Speed Boost - 並列処理)
    # =================================================================
    
    print("\n" + "=" * 70)
    print("📝 ステップ2: Whisper文字起こし (Speed Boost)")
    print("=" * 70)
    
    transcribed_map = {}
    completed_whisper = 0
    
    def whisper_task(audio_path, i):
        try:
            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="ja",
                    response_format="text",
                    prompt="日本語の小説の朗読です。正確に書き起こしてください。"
                )
            return i, transcript, None
        except Exception as e:
            return i, "", str(e)
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(whisper_task, audio_files_map[i], i) for i in range(len(audio_files))]
        for future in as_completed(futures):
            i, transcript, error = future.result()
            if error:
                print(f"❌ チャンク {i+1} 文字起こしエラー: {error}")
            transcribed_map[i] = transcript
            completed_whisper += 1
            pct = completed_whisper / len(audio_files) * 100
            print(f"\r   🚀 文字起こし中: [{completed_whisper}/{len(audio_files)}] {pct:.1f}%", end='', flush=True)
    
    print("\n✅ 文字起こし完了")
    transcribed_texts = [transcribed_map.get(i, "") for i in range(len(chunks))]
    
    # =================================================================
    # ステップ2.5: ルビ読みチェック → スキップ
    # Whisperがルビ形式に従わないため、差分検出に一本化
    # =================================================================
    
    print("\n" + "=" * 70)
    print("🔤 ステップ2.5: ルビ読みチェック → スキップ")
    print("   ℹ️ Whisperがルビ形式に従わないため、差分検出に一本化")
    print("=" * 70)
    
    # ルビがあれば除去してプレーンテキスト化
    clean_transcribed = [strip_ruby(t) for t in transcribed_texts]
    
    # =================================================================
    # ステップ3: 差分比較・読み間違い検出
    # =================================================================
    
    print("\n" + "=" * 70)
    print("🔍 ステップ3: 読み間違い検出")
    print("=" * 70)
    
    all_differences = []
    
    for i, (orig_chunk, trans_chunk) in enumerate(zip(chunks, clean_transcribed)):
        diffs = find_differences(orig_chunk, trans_chunk, i + 1)
        all_differences.extend(diffs)
    
    # =================================================================
    # レポート出力
    # =================================================================
    
    print(f"\n📊 検出結果: {len(all_differences)} 箇所の差異")
    
    report_path = os.path.join(OUTPUT_DIR, "reading_errors_report.txt")
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("📚 TTS読み間違い検出レポート\n")
        f.write(f"入力ファイル: {INPUT_FILE}\n")
        if MP3_FILE:
            f.write(f"MP3ファイル: {MP3_FILE}\n")
        else:
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


if __name__ == "__main__":
    main()

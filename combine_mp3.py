# =============================================================================
# 🔗 MP3結合ツール
# 指定フォルダ内の chunk_*.mp3 を結合して novel_full.mp3 を作成
# =============================================================================

import os
import glob
import sys
from pydub import AudioSegment

# Windows対応: UTF-8出力設定
sys.stdout.reconfigure(encoding='utf-8')

# 設定
TEMP_DIR = os.environ.get('TEMP', r"c:\Users\natak\AppData\Local\Temp")
# もし別の場所に保存されていたら変更してください
# 例: TEMP_DIR = r"c:\Users\natak\Documents\Novel\temp_audio"

OUTPUT_FILE = r"c:\Users\natak\Documents\Novel\novel_full.mp3"

def combine_audio_files(input_dir, output_path):
    print(f"📁 検索ディレクトリ: {input_dir}")
    
    # ファイル検索
    audio_files = sorted(glob.glob(os.path.join(input_dir, "chunk_*.mp3")))
    
    if not audio_files:
        # TEMPフォルダ内で最近作成されたフォルダを探す
        print("⚠️ chunk_*.mp3 が見つかりません。最近のテンプフォルダを検索します...")
        latest_dir = max(glob.glob(os.path.join(TEMP_DIR, "tmp*")), key=os.path.getctime, default=None)
        
        if latest_dir:
            print(f"🔍 最新のテンプフォルダ: {latest_dir}")
            audio_files = sorted(glob.glob(os.path.join(latest_dir, "chunk_*.mp3")))
            
    if not audio_files:
        print("❌ 音声ファイルが見つかりませんでした。")
        return

    print(f"✅ {len(audio_files)} 個のファイルが見つかりました。結合を開始します...")

    # 結合処理
    combined = AudioSegment.empty()
    
    for i, file in enumerate(audio_files):
        print(f"   [{i+1}/{len(audio_files)}] 結合中: {os.path.basename(file)}")
        segment = AudioSegment.from_mp3(file)
        combined += segment

    # 保存
    print(f"\n💾 保存中: {output_path}")
    combined.export(output_path, format="mp3")
    
    print("\n🎉 結合完了！")

if __name__ == "__main__":
    # もし前のスクリプト実行時に一時フォルダのパスが表示されていたら、ここにコピペしてください
    # target_dir = r"C:\Users\natak\AppData\Local\Temp\tmpABCDEF"
    
    # わからない場合は、標準のTempフォルダを検索
    combine_audio_files(TEMP_DIR, OUTPUT_FILE)

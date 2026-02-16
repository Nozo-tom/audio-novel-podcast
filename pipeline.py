# =============================================================================
# 🚀 音声小説 全自動パイプライン
#
# 1つのコマンドで以下を全自動実行:
#   1. 小説テキスト読み込み
#   2. 読み間違いしそうな単語を抽出 → 読み替え辞書生成
#   3. 初回MP3生成（仮ver）
#   4. 仮MP3をWhisperでテキスト化 → 原文と比較 → 読み間違い検出
#   5. 検出結果から辞書を自動補強
#   6. 最終MP3生成（完成ver）
#   7. 小説を済フォルダへ移動
#   8. フルverを1分にカット
#   9. 1分verをfeedに登録 → GitHub push（Spotifyに配信）
#
# 使い方:
#   python pipeline.py                           # novle_input内の最古1件を処理
#   python pipeline.py novle_input/小説.txt      # 指定ファイルを処理
#   python pipeline.py --all                     # novle_input内の全ファイルを古い順に処理
#   python pipeline.py --test novle_input/小説.txt  # テスト（feed/push/移動なし）
# =============================================================================

import os
import sys
import re
import subprocess
import argparse
import glob
import time
from pathlib import Path
from datetime import datetime

# Windows対応
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).parent
NOVLE_INPUT_DIR = BASE_DIR / "novle_input"
COMPLETED_DIR = BASE_DIR / "novels" / "completed"
MP3_DIR = BASE_DIR / "mp3"

def banner(step_num, total_steps, title):
    """ステップバナーを表示"""
    print(f"\n{'='*70}")
    print(f"  📌 STEP {step_num}/{total_steps}: {title}")
    print(f"{'='*70}")

def run_script(cmd, description, timeout=600):
    """サブスクリプトを実行して結果を表示"""
    print(f"  ▸ {description}")
    print(f"  ▸ コマンド: {' '.join(cmd)}")
    print()
    
    try:
        result = subprocess.run(
            cmd, 
            cwd=str(BASE_DIR),
            capture_output=False,  # リアルタイム出力
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode != 0:
            print(f"\n  ❌ エラー（終了コード: {result.returncode}）")
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"\n  ❌ タイムアウト（{timeout}秒）")
        return False
    except Exception as e:
        print(f"\n  ❌ 実行エラー: {e}")
        return False


def find_latest_mp3(text_path):
    """テキストファイルに対応する最新のMP3を探す"""
    stem = Path(text_path).stem
    short_title = stem[:15]
    
    # mp3/ディレクトリから検索
    pattern = str(MP3_DIR / f"{short_title}_*.mp3")
    files = glob.glob(pattern)
    
    if not files:
        # フルネームでも検索
        pattern2 = str(MP3_DIR / f"{stem[:30]}*.mp3")
        files = glob.glob(pattern2)
    
    if files:
        # 最新のファイルを取得
        return max(files, key=os.path.getmtime)
    return None


def get_yaml_path(text_path):
    """テキストファイルに対応するYAMLパスを返す"""
    return str(Path(text_path).with_suffix('.yaml'))


def process_novel(text_path, test_mode=False, char_limit=None):
    """
    1つの小説を全自動パイプラインで処理する。
    
    Returns: True=成功, False=失敗
    """
    total_steps = 6 if test_mode else 9
    text_path = str(Path(text_path).resolve())
    stem = Path(text_path).stem
    title = re.sub(r'^\d{8}_', '', stem)
    
    # --limit: テキストを制限文字数で切ったテンポラリファイルを作成
    temp_text_path = None
    if char_limit:
        with open(text_path, 'r', encoding='utf-8') as f:
            full_text = f.read()
        # 改行位置で切る
        cut_pos = full_text[:int(char_limit * 1.1)].rfind('\n')
        if cut_pos > 0:
            short_text = full_text[:cut_pos]
        else:
            short_text = full_text[:char_limit]
        
        temp_dir = Path(text_path).parent
        temp_text_path = str(temp_dir / f"_limit_test_{stem}.txt")
        with open(temp_text_path, 'w', encoding='utf-8') as f:
            f.write(short_text)
        text_path = temp_text_path
        print(f"\n  ✂️ テスト用に{len(short_text)}文字にカット")
    
    yaml_path = get_yaml_path(text_path)
    
    print("\n" + "█" * 70)
    print(f"  🚀 パイプライン開始: {title}")
    if test_mode:
        print(f"  🧪 テストモード（feed/push/移動なし）")
    if char_limit:
        print(f"  ✂️ 文字数制限: {char_limit}文字")
    print("█" * 70)
    
    start_time = time.time()
    
    # ─────────────────────────────────────────────
    # STEP 1: 読み替え辞書を生成
    # ─────────────────────────────────────────────
    banner(1, total_steps, "読み替え辞書を自動生成")
    
    if Path(yaml_path).exists():
        print(f"  ℹ️ 既存の辞書が見つかりました: {Path(yaml_path).name}")
        print(f"  ℹ️ 既存辞書を使用します（再生成はスキップ）")
        
        # voiceが未設定なら主人公の性別から自動判定
        import yaml as _yaml
        with open(yaml_path, 'r', encoding='utf-8') as f:
            existing_yaml = _yaml.safe_load(f) or {}
        if not existing_yaml.get('voice'):
            print(f"  🎭 voice未設定 → 主人公の性別を判定中...")
            try:
                with open(text_path, 'r', encoding='utf-8') as f:
                    sample_text = f.read()[:3000]
                # 女性主人公キーワード
                female_kw = ['令嬢', '姫', '聖女', 'お嬢様', '私は', '私が', '私の', 'わたし',
                             '彼女は主人公', '女主人公', 'ヒロイン', '少女', '魔女', '王女', '女神']
                male_kw = ['俺は', '俺が', '俺の', '僕は', '僕が', '僕の',
                           '勇者', '王子', '騎士', '冒険者', '少年']
                female_score = sum(sample_text.count(kw) for kw in female_kw)
                male_score = sum(sample_text.count(kw) for kw in male_kw)
                # タイトルも参照
                female_score += sum(3 for kw in ['令嬢', '姫', '聖女', '王女', '魔女', '少女', '彼女'] if kw in title)
                male_score += sum(3 for kw in ['俺', '僕', '勇者', '王子', '騎士', '少年'] if kw in title)
                
                if female_score > male_score:
                    suggested_voice = 'nova'
                    gender_label = '女性'
                else:
                    suggested_voice = 'fable'
                    gender_label = '男性'
                
                existing_yaml['voice'] = suggested_voice
                with open(yaml_path, 'w', encoding='utf-8') as f:
                    _yaml.dump(existing_yaml, f, allow_unicode=True, default_flow_style=False)
                print(f"  ✅ 主人公: {gender_label} → voice: {suggested_voice} を設定しました")
            except Exception as e:
                print(f"  ⚠️ 性別判定に失敗: {e}（デフォルトvoiceで続行）")
    else:
        ok = run_script(
            [sys.executable, "generate_corrections.py", text_path, "--mode", "deep"],
            "ディープスキャンで辞書を生成中..."
        )
        if not ok:
            print("  ⚠️ 辞書生成に失敗しましたが、辞書なしで続行します")
    
    # ─────────────────────────────────────────────
    # STEP 2: 初回MP3生成（仮ver）
    # ─────────────────────────────────────────────
    banner(2, total_steps, "初回MP3生成（仮ver）")
    
    ok = run_script(
        [sys.executable, "publish_novel.py", text_path, "--test"],
        "テストモードでMP3を生成中..."
    )
    if not ok:
        print("  ❌ MP3生成に失敗しました。パイプラインを中断します。")
        return False
    
    # 生成されたMP3を探す
    first_mp3 = find_latest_mp3(text_path)
    if not first_mp3:
        print("  ❌ 生成されたMP3が見つかりません。パイプラインを中断します。")
        return False
    
    print(f"\n  ✅ 仮MP3: {Path(first_mp3).name}")
    
    # ─────────────────────────────────────────────
    # STEP 3: Whisper比較 → 読み間違い検出
    # ─────────────────────────────────────────────
    banner(3, total_steps, "Whisper文字起こし → 読み間違い検出")
    
    ok = run_script(
        [sys.executable, "detect_reading_errors.py", text_path, "--mp3", first_mp3],
        "仮MP3をWhisperでテキスト化して原文と比較中...",
        timeout=900
    )
    if not ok:
        print("  ⚠️ 読み間違い検出に失敗しましたが、続行します")
    
    # ─────────────────────────────────────────────
    # STEP 4: 辞書を自動補強
    # ─────────────────────────────────────────────
    banner(4, total_steps, "読み間違いレポートから辞書を自動補強")
    
    report_path = str(BASE_DIR / "reading_errors_report.txt")
    if Path(report_path).exists() and Path(yaml_path).exists():
        report_path_abs = str(BASE_DIR / "reading_errors_report.txt")
        ok = run_script(
            [sys.executable, "fix_corrections_from_report.py", yaml_path, "--report", report_path_abs, "--text", text_path],
            "レポートを解析して辞書を更新中..."
        )
        if not ok:
            print("  ⚠️ 辞書補強に失敗しましたが、続行します")
    else:
        print("  ⚠️ レポートまたはYAMLが見つかりません（スキップ）")
    
    # ─────────────────────────────────────────────
    # STEP 5: 最終MP3生成（完成ver）
    # ─────────────────────────────────────────────
    banner(5, total_steps, "最終MP3生成（完成ver）")
    
    if test_mode:
        ok = run_script(
            [sys.executable, "publish_novel.py", text_path, "--test"],
            "補強した辞書で最終MP3を生成中（テストモード）..."
        )
    else:
        # 本番: MP3のみ生成（feedは後で1分版を登録）
        ok = run_script(
            [sys.executable, "publish_novel.py", text_path, "--mp3-only"],
            "補強した辞書で最終MP3を生成中..."
        )
    
    if not ok:
        print("  ❌ 最終MP3生成に失敗しました。パイプラインを中断します。")
        return False
    
    final_mp3 = find_latest_mp3(text_path)
    if not final_mp3:
        print("  ❌ 最終MP3が見つかりません。")
        return False
    
    print(f"\n  ✅ 完成MP3: {Path(final_mp3).name}")
    
    # テストモードはここまで
    if test_mode:
        banner(6, total_steps, "テストモード完了")
        elapsed = time.time() - start_time
        print(f"\n  🧪 テストモードのためここで終了")
        print(f"  📁 完成MP3: {final_mp3}")
        print(f"  ⏱️ 所要時間: {elapsed/60:.1f}分")
        return True
    
    # ─────────────────────────────────────────────
    # STEP 6: 小説を済フォルダへ移動
    # ─────────────────────────────────────────────
    banner(6, total_steps, "小説を済フォルダへ移動")
    
    COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import shutil
        dest_txt = COMPLETED_DIR / Path(text_path).name
        shutil.move(text_path, str(dest_txt))
        print(f"  ✅ {Path(text_path).name} → novels/completed/")
        
        # YAMLも移動
        if Path(yaml_path).exists():
            dest_yaml = COMPLETED_DIR / Path(yaml_path).name
            shutil.move(yaml_path, str(dest_yaml))
            print(f"  ✅ {Path(yaml_path).name} → novels/completed/")
    except Exception as e:
        print(f"  ⚠️ ファイル移動に失敗: {e}")
    
    # ─────────────────────────────────────────────
    # STEP 7: フルverを1分にカット
    # ─────────────────────────────────────────────
    banner(7, total_steps, "1分プレビュー版を作成")
    
    preview_mp3 = None
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(final_mp3)
        full_duration_sec = len(audio) / 1000
        
        preview_duration_ms = 60 * 1000
        if len(audio) > preview_duration_ms:
            preview = audio[:preview_duration_ms].fade_out(3000)
        else:
            preview = audio
            print(f"  ℹ️ 元の音声が60秒以下のため、そのまま使用")
        
        preview_filename = Path(final_mp3).stem + "_preview.mp3"
        preview_mp3 = str(Path(final_mp3).parent / preview_filename)
        preview.export(preview_mp3, format='mp3')
        
        preview_sec = len(preview) / 1000
        print(f"  ✅ プレビュー版: {preview_filename} ({preview_sec:.0f}秒)")
        print(f"  📁 フルver: {Path(final_mp3).name} ({full_duration_sec:.0f}秒)")
    except Exception as e:
        print(f"  ❌ プレビュー作成に失敗: {e}")
        preview_mp3 = final_mp3  # 失敗時はフルverを使用
    
    # ─────────────────────────────────────────────
    # STEP 8: feedに1分版を登録
    # ─────────────────────────────────────────────
    banner(8, total_steps, "RSSフィードに1分版を登録")
    
    feed_mp3 = preview_mp3 if preview_mp3 else final_mp3
    ok = run_script(
        [sys.executable, "publish_novel.py", "--feed-only", 
         "--mp3", feed_mp3,
         "--title", title],
        "1分プレビュー版をfeedに登録中..."
    )
    if not ok:
        print("  ❌ feed登録に失敗しました")
    
    # ─────────────────────────────────────────────
    # STEP 9: GitHub push
    # ─────────────────────────────────────────────
    banner(9, total_steps, "GitHubへプッシュ → Spotify配信")
    
    ok = run_script(
        ["git", "add", "docs/"],
        "docs/ をステージング中..."
    )
    if ok:
        # コミットメッセージにタイトルを含める
        commit_msg = f"Add episode: {title[:30]}"
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        if result.returncode == 0:
            print(f"  ✅ コミット完了: {commit_msg}")
            ok = run_script(
                ["git", "push"],
                "GitHubへプッシュ中..."
            )
            if ok:
                print("  ✅ Spotifyへのfeed配信完了！")
            else:
                print("  ❌ プッシュに失敗しました")
        else:
            print(f"  ❌ コミット失敗: {result.stderr.strip()}")
    
    # ─────────────────────────────────────────────
    # 完了
    # ─────────────────────────────────────────────
    elapsed = time.time() - start_time
    
    print("\n" + "█" * 70)
    print(f"  🎉 パイプライン完了: {title}")
    print(f"  ⏱️ 所要時間: {elapsed/60:.1f}分")
    print(f"  📁 フルMP3: {final_mp3}")
    if preview_mp3 and preview_mp3 != final_mp3:
        print(f"  📡 Spotify: 1分プレビュー版で配信中")
    print("█" * 70)
    
    return True


def get_input_files(input_path=None, process_all=False):
    """処理対象ファイルのリストを取得（古い順）"""
    if input_path:
        path = Path(input_path)
        if not path.exists():
            print(f"❌ ファイルが見つかりません: {input_path}")
            sys.exit(1)
        return [str(path)]
    
    # novle_inputフォルダから取得
    if not NOVLE_INPUT_DIR.exists():
        print(f"❌ {NOVLE_INPUT_DIR} が見つかりません")
        sys.exit(1)
    
    txt_files = sorted(NOVLE_INPUT_DIR.glob("*.txt"))
    
    if not txt_files:
        print("⚠️ 処理対象のファイルがありません")
        sys.exit(0)
    
    if process_all:
        return [str(f) for f in txt_files]
    else:
        # 最古の1件のみ
        return [str(txt_files[0])]


def main():
    parser = argparse.ArgumentParser(
        description="🚀 音声小説 全自動パイプライン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ワークフロー:
  1. 読み替え辞書を自動生成
  2. 初回MP3生成（仮ver）
  3. Whisper文字起こしで読み間違い検出
  4. 辞書を自動補強
  5. 最終MP3生成（完成ver）
  6. 小説を済フォルダへ移動
  7. フルverを1分にカット
  8. 1分verをfeedに登録
  9. GitHubへpush → Spotifyに配信

使い方:
  python pipeline.py                              # 最古の1件を処理
  python pipeline.py novle_input/小説.txt          # 指定ファイルを処理
  python pipeline.py --all                         # 全ファイルを古い順に処理
  python pipeline.py --test                        # テスト（STEP 1-5のみ）
        """
    )
    
    parser.add_argument("input", nargs="?", help="入力テキストファイル（省略時はnovle_input内の最古1件）")
    parser.add_argument("--all", action="store_true", help="novle_input内の全ファイルを古い順に処理")
    parser.add_argument("--test", action="store_true", help="テストモード（feed/push/移動なし）")
    parser.add_argument("--limit", type=int, help="処理文字数制限（高速テスト用、例: --limit 1000）")
    
    args = parser.parse_args()
    
    # バナー
    print("\n" + "=" * 70)
    print("  🚀 音声小説 全自動パイプライン")
    print("     小説 → 辞書生成 → 仮MP3 → 読み間違い検出 → 辞書補強")
    print("     → 完成MP3 → 1分カット → feed登録 → Spotify配信")
    print("=" * 70)
    
    # 処理対象ファイルを取得
    files = get_input_files(args.input, args.all)
    total_files = len(files)
    
    print(f"\n📚 処理対象: {total_files}件")
    for i, f in enumerate(files, 1):
        title = re.sub(r'^\d{8}_', '', Path(f).stem)
        print(f"   {i}. {title}")
    
    # 処理
    success_count = 0
    fail_count = 0
    
    for i, text_file in enumerate(files, 1):
        print(f"\n\n{'#' * 70}")
        print(f"  📖 [{i}/{total_files}] 処理中...")
        print(f"{'#' * 70}")
        
        ok = process_novel(text_file, test_mode=args.test, char_limit=args.limit)
        if ok:
            success_count += 1
        else:
            fail_count += 1
    
    # 最終サマリー
    print("\n\n" + "=" * 70)
    print("  📊 全処理完了！")
    print(f"     成功: {success_count}件 / 失敗: {fail_count}件")
    print("=" * 70)


if __name__ == "__main__":
    main()

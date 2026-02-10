# 📚 音声小説 → Spotify 自動配信ツール

テキストファイルから音声小説（MP3）を自動生成し、Spotifyへの配信準備（RSSフィード生成）まで **ワンコマンド** で実行します。

## 🚀 クイックスタート

### 1. 初回セットアップ

```bash
# 必要なライブラリをインストール
pip install openai pydub pyyaml python-dotenv mutagen

# 環境変数を設定
copy .env.example .env
# .env を開いて OPENAI_API_KEY を入力
```

### 2. 実行

```bash
# 基本的な使い方（テキスト → MP3 → RSSフィード）
python publish_novel.py "novels/小説名.txt"

# タイトルと説明を指定
python publish_novel.py "novels/小説名.txt" --title "第1話 始まり" --description "物語の始まりです"

# 音声やモデルを変更
python publish_novel.py "novels/小説名.txt" --voice cedar --model tts-1-hd

# MP3生成のみ（RSSフィード不要の場合）
python publish_novel.py "novels/小説名.txt" --mp3-only

# 既存MP3からRSSフィードだけ作る
python publish_novel.py --feed-only --mp3 "mp3/既存.mp3" --title "第2話"
```

## 📁 ファイル構成

```
Novel/
├── publish_novel.py       # メインスクリプト
├── config.yaml            # 番組設定（チームで共有）
├── .env                   # APIキー（個人ごと、Gitに入れない！）
├── .env.example           # .env のテンプレート
├── novels/                # テキストファイル置き場
│   └── 小説名.txt
├── mp3/                   # 生成されたMP3
│   └── 小説名_20260210_141603.mp3
└── feed/                  # Spotify配信用（ホスティングにアップ）
    ├── feed.xml           # RSSフィード
    ├── episodes.json      # エピソード管理データ
    ├── cover.png          # カバーアート画像
    └── 小説名_20260210.mp3  # 配信用MP3コピー
```

## ⚙️ 設定ファイル (config.yaml)

`config.yaml` で番組情報、TTS設定、読み替え辞書を管理します。

### 主要な設定項目

| 項目 | 説明 |
|------|------|
| `podcast.title` | ポッドキャスト番組名 |
| `podcast.author` | 作者名 |
| `podcast.base_url` | ホスティング先のURL |
| `tts.voice` | 音声タイプ（fable, cedar, marin 等） |
| `tts.model` | TTSモデル（tts-1, tts-1-hd, gpt-4o-mini-tts） |
| `reading_corrections` | 読み替え辞書（漢字 → ひらがな） |

## 🎙️ 使用可能な音声

| 音声 | 特徴 |
|------|------|
| `fable` ⭐ | 物語の朗読に最適、表現力豊か |
| `cedar` ⭐ | 自然で温かみのある声 |
| `marin` ⭐ | 自然で聞き取りやすい声 |
| `alloy` | 中性的でバランスの取れた声 |
| `nova` | 明るく親しみやすい女性的な声 |
| `onyx` | 力強い男性的な声 |
| `echo` | 深みのある男性的な声 |

## 📡 Spotify への配信手順

### 方法A: 無料ホスティングサービス（RSS.com）を使う ← 推奨

1. [RSS.com](https://rss.com) でアカウント作成（無料）
2. 番組情報を登録
3. `feed/` フォルダ内のMP3をアップロード
4. RSS.com が自動でRSSフィードを生成・管理
5. Spotifyに自動配信される

### 方法B: セルフホスト（GitHub Pages等）

1. GitHubリポジトリを作成、GitHub Pages を有効化
2. `feed/` フォルダの中身をリポジトリにpush
3. `config.yaml` の `base_url` にGitHub PagesのURLを設定
4. Spotify for Podcasters にRSSフィードURLを登録

## 🎨 カバーアート要件（Spotify）

| 項目 | 要件 |
|------|------|
| サイズ | 3000×3000px 推奨（最小1400×1400px） |
| 形状 | 正方形（1:1） |
| フォーマット | PNG 推奨（JPEG も可） |
| ファイルサイズ | 最大 4MB |
| テキスト | タイトルを大きく、5語以内推奨 |

## 👥 チームメンバーへの共有手順

1. このフォルダ一式を共有（Google Drive, OneDrive 等）
2. メンバーは `.env.example` → `.env` にコピーして自分のAPIキーを設定
3. `pip install openai pydub pyyaml python-dotenv mutagen` を実行
4. `python publish_novel.py "novels/テキスト.txt"` で実行！

## ❓ トラブルシューティング

- **「openai がない」エラー** → `pip install openai`
- **「pydub がない」エラー** → `pip install pydub` + [ffmpeg](https://ffmpeg.org/) のインストール
- **APIキーエラー** → `.env` の `OPENAI_API_KEY` を確認
- **文字化け** → テキストファイルをUTF-8で保存し直す

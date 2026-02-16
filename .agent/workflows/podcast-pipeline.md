---
description: 音声小説パイプラインの実行手順（1話ずつ処理）
---
// turbo-all

# 🎙️ 音声小説パイプライン ワークフロー

## 概要
`novle_input/` の小説テキストを名前昇順で1件ずつ処理し、
MP3生成 → 1分プレビュー → docs/配置 → feed.xml → GitHub push → Spotify配信 まで行う。

## 前提条件
- `.env` に `OPENAI_API_KEY` が設定済み
- `config.yaml` にポッドキャスト設定済み
- `png/` フォルダにカバー画像がある場合は自動検索される

---

## 手順

### 1. 未処理の小説を確認
```powershell
python -c "import sys;sys.stdout.reconfigure(encoding='utf-8');import os;ni=r'c:\Users\natak\Documents\Novel\novle_input';fs=sorted([f for f in os.listdir(ni) if f.endswith('.txt') and not f.startswith('_') and not f.startswith('test') and not f.startswith('gas')]);print(f'未処理: {len(fs)}件');[print(f'  {i+1}. {f}') for i,f in enumerate(fs[:10])]"
```

### 2. パイプライン実行（1件）
最初の未処理ファイルに対して実行:
```powershell
python pipeline.py
```
※ 引数なしで `novle_input/` の最古1件を自動選択
※ 指定する場合: `python pipeline.py "novle_input\YYYYMMDD_タイトル.txt"`

### 3. 処理完了を待つ
パイプラインは以下のSTEPを自動実行:
- STEP 1: 読み替え辞書を自動生成（既存YAMLがあればスキップ、voice未設定なら自動判定）
- STEP 2: 初回MP3生成（仮ver）
- STEP 3: Gemini音声分析 → 読み間違い検出
- STEP 4: 辞書を自動補強
- STEP 5: 最終MP3生成（完成ver）
- STEP 6: テキスト+YAMLを `novels/completed/` に移動
- STEP 7: フルverを1分プレビューにカット
- STEP 8: docs/に配置 + feed.xml更新（統一命名: `{日付}_{タイトル5文字}_preview.mp3`）
- STEP 9: git push → Spotify配信

### 4. git pushが失敗した場合の手動push
```powershell
git add docs/
git commit -m "Add episode: タイトル"
git push
```

### 5. 結果確認
```powershell
python -c "import sys;sys.stdout.reconfigure(encoding='utf-8');import json;eps=json.load(open(r'c:\Users\natak\Documents\Novel\docs\episodes.json','r',encoding='utf-8'));[print(f'EP{e[chr(110)+chr(117)+chr(109)+chr(98)+chr(101)+chr(114)]}: {e[chr(116)+chr(105)+chr(116)+chr(108)+chr(101)][:30]}...') for e in eps]"
```

---

## 一括処理（全件）
```powershell
python pipeline.py --all
```
※ 全ての未処理ファイルを古い順に処理

## テストモード（STEP 1-5のみ、配信なし）
```powershell
python pipeline.py --test
```

---

## 注意事項
- 1話あたり約5-8分（テキスト量による）
- APIコスト: 仮MP3 + 最終MP3 + Whisper検出 = 各話数十円〜
- voice設定: 主人公の性別から自動判定（女性→nova, 男性→fable）
- カバー画像: `png/` フォルダから日付プレフィックスで自動マッチ

## ファイル命名規則（docs/）
- MP3: `{YYYYMMDD}_{タイトル先頭5文字}_preview.mp3`
- カバー: `{YYYYMMDD}_{タイトル先頭5文字}.{png|jpg}`
- 番組カバー: `cover.jpg`

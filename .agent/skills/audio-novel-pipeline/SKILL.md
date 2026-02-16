---
name: audio-novel-pipeline
description: 音声小説パイプラインの管理・実行スキル。novle_inputのテキスト小説をMP3化してSpotifyに配信する一連の処理。
---

# 音声小説パイプライン スキル（統合）

## 概要
以下の個別スキルを組み合わせた全自動パイプライン。

## パイプライン構成

```
┌─────────────────────────────────────────────────┐
│  pipeline.py                                     │
│                                                  │
│  STEP 1 → [generate-dictionary]  辞書生成        │
│  STEP 2 → [generate-mp3]        仮MP3生成        │
│  STEP 3 → [detect-errors]       読み間違い検出    │
│  STEP 4 → [detect-errors]       辞書自動補強      │
│  STEP 5 → [generate-mp3]        最終MP3          │
│  STEP 6 → ファイル移動                           │
│  STEP 7 → [create-preview]      1分プレビュー     │
│  STEP 8 → [publish-feed]        feed登録         │
│  STEP 9 → [git-deploy]          Spotify配信      │
└─────────────────────────────────────────────────┘
```

## 全自動実行
```bash
python pipeline.py                           # 最古1件
python pipeline.py "novle_input/小説.txt"     # 指定
python pipeline.py --all                      # 全件
python pipeline.py --test                     # テスト（STEP 1-5のみ）
```

## 個別スキル呼び出し例

### 辞書だけ作り直したい
→ `generate-dictionary` スキル参照

### MP3だけ再生成（voiceを変えたい等）
→ `generate-mp3` スキル参照
```bash
python publish_novel.py "novle_input/小説.txt" --mp3-only
```

### 読み間違いを再検出したい
→ `detect-errors` スキル参照

### docs/を一括再構築（全EP分）
→ `publish-feed` スキル参照
```bash
python rebuild_docs.py --yes
```

### feedだけ更新してpush
→ `publish-feed` + `git-deploy` スキル参照
```bash
python publish_novel.py --feed-only --mp3 "mp3/XXX_preview.mp3" --title "タイトル"
git add docs/ && git commit -m "Update feed" && git push
```

## 依存関係
```
generate-dictionary ─→ generate-mp3 ─→ detect-errors ─→ generate-mp3(最終)
                                                              ↓
                                              create-preview ─→ publish-feed ─→ git-deploy
```

---
name: create-preview
description: 完成版MP3から1分プレビューを作成し、docs/にショート名で配置する。
---

# 1分プレビュー作成スキル

## 概要
完成版MP3の先頭60秒を切り出し、3秒フェードアウトを付けてプレビュー版を作成。
docs/ にショート名（`{日付}_{タイトル5文字}_preview.mp3`）でコピーする。

## 入力
- `mp3/{YYYYMMDD}_{短縮タイトル}_{日時}.mp3` — 完成版MP3

## 出力
- `mp3/{...}_preview.mp3` — プレビュー版（mp3/内）
- `docs/{YYYYMMDD}_{タイトル5文字}_preview.mp3` — 配信用コピー

## 処理（Pythonコード）
```python
from pydub import AudioSegment
audio = AudioSegment.from_mp3("mp3/YYYYMMDD_XXX.mp3")
preview = audio[:60000].fade_out(3000)
preview.export("mp3/YYYYMMDD_XXX_preview.mp3", format='mp3')
```

## 注意
- pipeline.py の STEP 7 で自動実行される
- 元MP3が60秒以下の場合はそのまま使用
- docs/ へのコピーは publish_novel.py の generate_rss_feed() で実施
- ショート名: `{日付8桁}_{タイトル先頭5文字}_preview.mp3`

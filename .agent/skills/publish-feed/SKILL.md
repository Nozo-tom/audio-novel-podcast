---
name: publish-feed
description: プレビューMP3とカバー画像をdocs/に配置し、episodes.jsonとfeed.xmlを更新する。
---

# feed登録・配信スキル

## 概要
1分プレビューMP3をdocs/に配置し、png/からカバー画像を検索して同梱。
episodes.json を更新し、feed.xml を再生成する。

## 入力
- `mp3/{...}_preview.mp3` — プレビューMP3
- `png/{YYYYMMDD}_{タイトル}.{png|jpg}` — カバー画像（自動検索）

## 出力
- `docs/{YYYYMMDD}_{タイトル5文字}_preview.mp3` — 配信用MP3
- `docs/{YYYYMMDD}_{タイトル5文字}.{png|jpg}` — カバー画像
- `docs/episodes.json` — エピソード管理データ
- `docs/feed.xml` — RSSフィード

## コマンド
```bash
# feed登録のみ（MP3生成なし）
python publish_novel.py --feed-only --mp3 "mp3/YYYYMMDD_XXX_preview.mp3" --title "タイトル"
```

## docs/一括再構築
mp3/ と png/ から全エピソードを再構築する場合:
```bash
python rebuild_docs.py --dry-run  # 計画確認
python rebuild_docs.py --yes      # 実行
```

## ファイル命名規則
- MP3: `{YYYYMMDD}_{タイトル先頭5文字}_preview.mp3`
- カバー: `{YYYYMMDD}_{タイトル先頭5文字}.{拡張子}`
- 番組カバー: `cover.jpg`

## 注意
- カバー画像は png/ から日付プレフィックスで自動マッチ
- 同一タイトルの既存エピソードは自動上書き（古いMP3/画像は削除）
- feed.xmlの各<item>に<itunes:image>でエピソード個別画像を設定

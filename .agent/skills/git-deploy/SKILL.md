---
name: git-deploy
description: docs/の変更をGitHub Pagesにpushし、Spotifyに配信する。
---

# Git デプロイスキル

## 概要
docs/ フォルダの変更を git add → commit → push し、
GitHub Pages 経由で Spotify にフィードを配信する。

## コマンド
```bash
git add docs/
git commit -m "Add episode: タイトル"
git push
```

## 確認
push後、以下のURLでfeedが更新されているか確認:
- feed.xml: https://Nozo-tom.github.io/audio-novel-podcast/feed.xml
- Spotifyへの反映は数分〜数時間

## 注意
- pipeline.py の STEP 9 で自動実行されるが、日本語コミットメッセージで失敗することがある
- 失敗した場合は手動で上記コマンドを実行
- `docs/` 以外のファイルは git add に含めない（mp3/ は .gitignore 対象）

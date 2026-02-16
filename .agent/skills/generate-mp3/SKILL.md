---
name: generate-mp3
description: 読み替え辞書を適用してテキストからMP3を生成。OpenAI TTSを使用。
---

# MP3生成スキル

## 概要
小説テキストを読み替え辞書で前処理し、OpenAI TTSでMP3音声を生成する。
CPU並列化（Core Ultra 285対応）で高速処理。

## 入力
- `novle_input/{YYYYMMDD}_{タイトル}.txt` — 小説テキスト
- `novle_input/{YYYYMMDD}_{タイトル}.yaml` — 読み替え辞書（任意）

## 出力
- `mp3/{YYYYMMDD}_{短縮タイトル}_{日時}.mp3` — 完成MP3

## コマンド
```bash
# MP3のみ生成（feed登録・push・移動なし）
python publish_novel.py "novle_input/YYYYMMDD_タイトル.txt" --mp3-only

# テスト用（MP3のみ、配信なし）
python publish_novel.py "novle_input/YYYYMMDD_タイトル.txt" --test
```

## 注意
- 1回の生成で APIコスト 数十円（テキスト量による）
- `--mp3-only` ではファイル移動・feed登録をスキップ
- voice は YAML の `voice` フィールドで制御（未指定なら config.yaml のデフォルト）
- チャンク分割 → 並列処理 → 結合の流れ

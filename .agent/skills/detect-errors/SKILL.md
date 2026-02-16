---
name: detect-errors
description: 生成したMP3の読み間違いをGeminiで検出し、読み替え辞書を自動補強する。
---

# 読み間違い検出スキル

## 概要
生成済みMP3をGemini（音声直接分析）で原文と比較し、
TTSの読み間違いを検出する。検出結果から辞書を自動補強する。

## 入力
- `mp3/{YYYYMMDD}_{短縮タイトル}_{日時}.mp3` — 生成済みMP3
- `novle_input/{YYYYMMDD}_{タイトル}.txt` — 元テキスト
- `novle_input/{YYYYMMDD}_{タイトル}.yaml` — 既存辞書

## 出力
- `reading_errors_report.txt` — 読み間違いレポート
- YAMLの corrections が自動更新される

## コマンド
```bash
# 読み間違い検出
python detect_reading_errors.py "novle_input/YYYYMMDD_タイトル.txt"

# 辞書自動補強（レポートから）
python fix_corrections_from_report.py "novle_input/YYYYMMDD_タイトル.yaml" --report reading_errors_report.txt --text "novle_input/YYYYMMDD_タイトル.txt"
```

## 注意
- Gemini API を使用（gemini-2.5-flash-lite → クォータ超過時は別モデルにフォールバック）
- `fix_corrections_from_report.py` に `KeyError: 'ratio'` バグあり（要修正）
- 検出された差異が0件なら辞書更新なし

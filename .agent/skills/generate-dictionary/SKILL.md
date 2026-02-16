---
name: generate-dictionary
description: 小説テキストから読み替え辞書（YAML）を自動生成する。主人公の性別からvoiceも自動判定。
---

# 読み替え辞書生成スキル

## 概要
小説テキストをOpenAI GPTで解析し、TTSが読み間違えやすい固有名詞・熟語の
読み替え辞書（YAML）を自動生成する。主人公の性別からvoice（男性=fable/女性=nova）も設定。

## 入力
- `novle_input/{YYYYMMDD}_{タイトル}.txt` — 小説テキスト

## 出力
- `novle_input/{YYYYMMDD}_{タイトル}.yaml` — 読み替え辞書 + voice設定

## コマンド
```bash
# ディープスキャン（推奨）
python generate_corrections.py "novle_input/YYYYMMDD_タイトル.txt" --mode deep

# 通常スキャン
python generate_corrections.py "novle_input/YYYYMMDD_タイトル.txt"
```

## 出力YAML例
```yaml
voice: nova
original_date: '20250912'
corrections:
  神崎蒼真: かんざきそうま
  桜庭花音: さくらばかのん
  幼馴染: おさななじみ
```

## 注意
- 既存YAMLがある場合は上書きされる
- voice未設定の既存YAMLがある場合、pipeline.py側でも自動補完ロジックあり
- 生成には OpenAI API を使用（数円程度）

import os
import sys
import requests
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Windows cp932 コンソール対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# .env読み込み
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

try:
    from openai import OpenAI
except ImportError:
    print("❌ openai ライブラリが必要です: pip install openai")
    sys.exit(1)

# 設定
TITLE = "悪役令嬢に転生したので破滅フラグを回避しようと思ったら、原作主人公が思ってたより策略家だった件"
AUTHOR = "桜木ひより"
TARGET_NOVEL_NAME = "20250912_悪役令嬢に転生したので破滅フラグを回避しようと思ったら、原作"

# 出力パス
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILENAME = f"{TARGET_NOVEL_NAME}.png"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_FILENAME

# バックアップ（前の画像を消さないように）
if OUTPUT_PATH.exists():
    backup_path = OUTPUT_DIR / f"{TARGET_NOVEL_NAME}_backup.png"
    shutil.copy2(OUTPUT_PATH, backup_path)

# DALL-E 3 用プロンプト (テキスト生成を指示)
PROMPT = f"""
A high-quality anime-style light novel cover illustration.
The scene depicts a beautiful noble daughter (villainess style) with long golden curly hair and sapphire blue eyes.
She wears an extremely elaborate, frilly, Victorian-rococo style dress in dark red and black.
She holds a delicate tea cup with an elegant pose, looking confident but slightly mischievous.
Background is a luxurious rose garden with a white gazebo and tea set.
Vibrant colors, sparkling effects, highly detailed masterpiece.

IMPORTANT: The image MUST include the following text clearly as the book title:
"{TITLE}"
And the author name:
"{AUTHOR}"
The text should be formatted elegantly in a Japanese style typography suitable for a light novel cover.
"""

def generate_image_dalle3(client, prompt):
    print("🎨 DALL-E 3 で画像を生成中 (テキスト描画含む)...")
    print(f"📝 指示テキスト: {TITLE}")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        print("✅ 画像生成成功！")
        return image_url
    except Exception as e:
        print(f"❌ 画像生成エラー: {e}")
        return None

def download_image(url, save_path):
    print("⬇️ 画像をダウンロード中...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        print(f"🎉 表紙画像を作成しました: {save_path}")
        return True
    except Exception as e:
        print(f"❌ ダウンロードエラー: {e}")
        return False

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    # 画像生成
    image_url = generate_image_dalle3(client, PROMPT)
    if not image_url: return
    
    # ダウンロード
    success = download_image(image_url, OUTPUT_PATH)
    
    if success:
        # 自動で開く
        os.startfile(OUTPUT_PATH)

if __name__ == "__main__":
    main()

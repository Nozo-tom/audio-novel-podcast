import os
import sys
import requests
import textwrap
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# Windows cp932 コンソール対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# .env読み込み
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print("⚠️  .env ファイルが見つかりません")

try:
    from openai import OpenAI
except ImportError:
    print("❌ openai ライブラリが必要です: pip install openai")
    sys.exit(1)

# 設定
TITLE = "悪役令嬢に転生したので破滅フラグを回避しようと思ったら、原作主人公が思ってたより策略家だった件"
AUTHOR = "桜木ひより"
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILENAME = f"cover_{int(os.times()[4])}.png"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_FILENAME

# プロンプト (英語で記述、ラノベ風・金髪碧眼令嬢・お茶会・薔薇)
PROMPT = """
A high-quality Japanese light novel cover illustration in anime style. 
The main character is a beautiful noble girl with long blonde hair and blue eyes, wearing an elegant and sophisticated dress suitable for a aristocratic academy. 
She is holding a tea cup gracefully in a luxurious European-style rose garden or tea room. 
The atmosphere is bright, sparkling, and elegant. 
Vibrant colors, detailed background, masterpiece quality. 
Avoid text, logos, or speech bubbles.
"""

def generate_image_dalle3(client, prompt):
    print("🎨 DALL-E 3 で画像を生成中...")
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

def download_image(url):
    print("⬇️ 画像をダウンロード中...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        return Image.open(BytesIO(response.content))
    except Exception as e:
        print(f"❌ ダウンロードエラー: {e}")
        return None

def add_text_to_image(image, title, author):
    print("✍️ タイトルと作者名を描画中...")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    # フォント設定 (Windows標準のメイリオを使用)
    font_path = "C:\\Windows\\Fonts\\meiryo.ttc"
    if not os.path.exists(font_path):
        font_path = "C:\\Windows\\Fonts\\msgothic.ttc" # メイリオがない場合
    
    try:
        title_font_size = 60
        author_font_size = 40
        title_font = ImageFont.truetype(font_path, title_font_size)
        author_font = ImageFont.truetype(font_path, author_font_size)
    except OSError:
        print("⚠️ 日本語フォントが見つかりません。デフォルトフォントを使用します。")
        title_font = ImageFont.load_default()
        author_font = ImageFont.load_default()

    # タイトルの折り返し処理
    # 全角文字換算で1行あたりの文字数を計算 (画像幅に合わせて調整)
    # 1024px幅なので、60pxフォントだと約15文字くらい？
    wrapped_title = textwrap.fill(title, width=14) 
    
    # テキストの色と縁取り
    text_color = (255, 255, 255) # 白
    stroke_color = (0, 0, 0) # 黒縁
    stroke_width = 4

    # タイトル描画位置 (上部)
    title_x = 50
    title_y = 50
    
    draw.multiline_text(
        (title_x, title_y), 
        wrapped_title, 
        font=title_font, 
        fill=text_color, 
        stroke_width=stroke_width, 
        stroke_fill=stroke_color,
        spacing=10
    )
    
    # 作者名描画位置 (下部右寄り)
    # テキストサイズを取得して位置調整
    bbox = draw.textbbox((0, 0), author, font=author_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    author_x = width - text_w - 50
    author_y = height - text_h - 50
    
    draw.text(
        (author_x, author_y), 
        author, 
        font=author_font, 
        fill=text_color, 
        stroke_width=stroke_width, 
        stroke_fill=stroke_color
    )
    
    return image

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ 環境変数 OPENAI_API_KEY が設定されていません")
        sys.exit(1)
        
    client = OpenAI(api_key=api_key)
    
    # 画像生成
    image_url = generate_image_dalle3(client, PROMPT)
    if not image_url: return
    
    # ダウンロード
    img = download_image(image_url)
    if not img: return
    
    # 文字入れ
    final_img = add_text_to_image(img, TITLE, AUTHOR)
    
    # 保存
    final_img.save(OUTPUT_PATH)
    print(f"🎉 表紙画像を作成しました: {OUTPUT_PATH}")
    
    # 自動で開く (Windows)
    os.startfile(OUTPUT_PATH)

if __name__ == "__main__":
    main()

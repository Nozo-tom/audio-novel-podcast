import os
import sys
import requests
import shutil
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

try:
    from openai import OpenAI
except ImportError:
    print("❌ openai ライブラリが必要です: pip install openai")
    sys.exit(1)

# 設定
TITLE = "悪役令嬢に転生したので\n破滅フラグを回避しようと思ったら、\n原作主人公が思ってたより\n策略家だった件"
AUTHOR = "桜木ひより"
TARGET_NOVEL_NAME = "20250912_悪役令嬢に転生したので破滅フラグを回避しようと思ったら、原作"

# 出力パス
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILENAME = f"{TARGET_NOVEL_NAME}.png"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_FILENAME

# バックアップ
if OUTPUT_PATH.exists():
    shutil.copy2(OUTPUT_PATH, OUTPUT_DIR / f"{TARGET_NOVEL_NAME}_old.png")

# プロンプト (文字なし、イラストのみ)
PROMPT = """
A masterpiece light novel cover illustration, anime style.
A beautiful villainess noble girl with golden ringlets and blue eyes.
She wears a luxurious dark red and black dress, sitting in a beautiful rose garden tea party.
She holds a tea cup with a confident, slightly wicked smile.
Detailed background, sparkling light, high contrast, vivid colors.
NO TEXT, NO LOGOS. Clean illustration.
"""

def generate_image_dalle3(client, prompt):
    print("🎨 DALL-E 3 でイラストを生成中 (文字なし)...")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        return response.data[0].url
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

from io import BytesIO

def draw_text_with_border(draw, text, x, y, font, text_color, border_color, border_width):
    # 縁取り
    for dx in range(-border_width, border_width + 1):
        for dy in range(-border_width, border_width + 1):
            if abs(dx) + abs(dy) == 0: continue
            draw.text((x + dx, y + dy), text, font=font, fill=border_color)
    # 本体
    draw.text((x, y), text, font=font, fill=text_color)

def add_vertical_title(image, title, author):
    print("✍️ タイトルを縦書きで合成中...")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    # フォント設定
    font_path = "C:\\Windows\\Fonts\\BIZ-UDMinchoM.ttc"
    if not os.path.exists(font_path):
        font_path = "C:\\Windows\\Fonts\\msmincho.ttc"
    
    title_size = 55
    author_size = 40
    try:
        title_font = ImageFont.truetype(font_path, title_size)
        author_font = ImageFont.truetype(font_path, author_size)
    except:
        title_font = ImageFont.load_default()
        author_font = ImageFont.load_default()

    # 右上に配置（縦書き）
    lines = title.split("\n")
    start_x = width - 80
    start_y = 50
    
    # タイトル描画
    current_x = start_x
    for line in lines:
        current_y = start_y
        for char in line:
            # 句読点の微調整
            char_draw = char
            offset_x = 0
            offset_y = 0
            if char in "、。":
                offset_x = title_size * 0.6
                offset_y = -title_size * 0.6
            
            # 縦書き描画（1文字ずつ）
            draw_text_with_border(draw, char_draw, current_x + offset_x, current_y + offset_y, 
                                  title_font, (255, 255, 255), (100, 0, 0), 4)
            
            # 文字送り
            current_y += title_size * 1.05
        
        # 行送り（左へ）
        current_x -= title_size * 1.5

    # 作者名（左下、横書き）
    author_text = f"著：{AUTHOR}"
    bbox = draw.textbbox((0,0), author_text, font=author_font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    
    ax = 50
    ay = height - h - 50
    
    # 背景帯
    draw.rectangle([ax - 10, ay - 10, ax + w + 10, ay + h + 10], fill=(0,0,0,180))
    draw_text_with_border(draw, author_text, ax, ay, author_font, (255, 255, 255), (0,0,0), 0)

    return image

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    # 1. 画像生成（文字なし）
    image_url = generate_image_dalle3(client, PROMPT)
    if not image_url: return
    
    # 2. ダウンロード
    img = download_image(image_url)
    if not img: return
    
    # 3. 文字合成（Python制御で綺麗に）
    final_img = add_vertical_title(img, TITLE, AUTHOR)
    
    # 保存
    final_img.save(OUTPUT_PATH)
    print(f"🎉 完成: {OUTPUT_PATH}")
    os.startfile(OUTPUT_PATH)

if __name__ == "__main__":
    main()

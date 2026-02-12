import os
import sys
import requests
import textwrap
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

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
TITLE = "俺が憧れの\n氷室さんの\n秘密を知ったら\n異能力事件に\n巻き込まれた件"
AUTHOR = "桜木ひより"
TARGET_NOVEL_NAME = "20250913_俺が憧れの氷室さんの秘密を知ったら異能力事件に巻き込まれた件"
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_FILENAME = f"{TARGET_NOVEL_NAME}.png"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_FILENAME

# プロンプト (文字なし、イラストのみ)
PROMPT = """
A masterpiece light novel cover illustration, anime style.
A beautiful Japanese high school girl with long black straight hair and cool, sharp eyes (cool beauty).
She wears a standard high school uniform (blazer or sailor suit).
She is standing in a school classroom at sunset (warm orange and purple light).
In her hand, she is magically floating a beautiful, sparkling structure made of ice crystals (like an ice rose).
Magical ice particles and frost effects surround her hand, contrasting with the warm sunset light.
NO TEXT, NO LOGOS. Clean illustration. High quality, detailed art.
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

def create_gradient_text_mask(size, font, text, position):
    # テキストの形をしたマスクを作成
    mask = Image.new('L', size, 0)
    draw = ImageDraw.Draw(mask)
    draw.text(position, text, font=font, fill=255)
    return mask

def draw_text_with_style(image, text, position, font, rotation_angle=0):
    # キャンバス準備
    width, height = image.size
    
    # テキスト用のレイヤー
    text_layer = Image.new('RGBA', (width, height), (0,0,0,0))
    draw = ImageDraw.Draw(text_layer)
    
    # 1. 影 (Shadow)
    shadow_offset = (5, 5)
    shadow_color = (0, 0, 50, 180) # 濃い紺色の影
    draw.text((position[0] + shadow_offset[0], position[1] + shadow_offset[1]), 
              text, font=font, fill=shadow_color)
    
    # 2. 縁取り (Border)
    border_color = (255, 255, 255) # 白フチ
    border_width = 8
    
    # 高速な縁取り描画（円形に太らせる）
    for dx in range(-border_width, border_width + 1):
        for dy in range(-border_width, border_width + 1):
            if dx*dx + dy*dy <= border_width*border_width:
                 draw.text((position[0]+dx, position[1]+dy), text, font=font, fill=border_color)

    # 3. 本体（グラデーション風）
    # グラデーション画像を作成 (上:水色 -> 下:青)
    gradient = Image.new('RGBA', (width, height), color=0)
    g_draw = ImageDraw.Draw(gradient)
    
    # 簡易グラデーション（青系）
    for y in range(height):
        # 0(上) -> 255(下)
        alpha = int(255 * (y / height))
        r = 0
        g = int(200 * (1 - y/height)) # 上は水色っぽく
        b = 255
        g_draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    
    # テキストマスクで切り抜き
    mask = Image.new('L', (width, height), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.text(position, text, font=font, fill=255)
    
    gradient.putalpha(mask)
    
    # レイヤー合成
    # まず影と縁取りがあるレイヤーに、グラデーション文字を乗せる
    text_layer.alpha_composite(gradient)
    
    return Image.alpha_composite(image.convert('RGBA'), text_layer)

def add_designed_title(image, title, author):
    print("✍️ タイトルをロゴデザイン風に合成中...")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    # フォント設定 (ゴシック体を優先)
    font_path = "C:\\Windows\\Fonts\\meiryo.ttc" # メイリオ
    if not os.path.exists(font_path):
        font_path = "C:\\Windows\\Fonts\\msgothic.ttc"
    
    title_size = 80
    author_size = 40
    try:
        title_font = ImageFont.truetype(font_path, title_size)
        author_font = ImageFont.truetype(font_path, author_size)
    except:
        title_font = ImageFont.load_default()
        author_font = ImageFont.load_default()

    # 右上に大きく配置（傾きやサイズを変えて動きを出す）
    lines = title.split("\n")
    start_x = 50
    start_y = 50
    
    image = image.convert('RGBA')
    
    current_y = start_y
    for i, line in enumerate(lines):
        # 行ごとに少しずらす
        offset_x = 30 * (i % 2) # ジグザグ
        
        # 特に強調したい単語のサイズを変えるなどの処理は複雑なので、
        # 今回は行ごとの処理に留める
        
        # 色味：氷異能系なので「青〜白」のグラデーション文字にしたい
        # ここでは draw_text_with_style 関数を使って描画
        
        # 描画位置
        pos = (start_x + offset_x, current_y)
        
        # グラデーション文字を描画して合成
        image = draw_text_with_style(image, line, pos, title_font)
        
        current_y += title_size * 1.2
        
    # 作者名（左下、シンプルの帯）
    d = ImageDraw.Draw(image)
    author_text = f"著：{AUTHOR}"
    bbox = d.textbbox((0,0), author_text, font=author_font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    
    ax = 50
    ay = height - h - 50
    
    d.rectangle([ax - 10, ay - 10, ax + w + 10, ay + h + 10], fill=(0,0,0,200)) # 黒帯
    d.text((ax, ay), author_text, font=author_font, fill=(255, 255, 255))

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
    
    # 3. 文字合成（デザイン重視）
    final_img = add_designed_title(img, TITLE, AUTHOR)
    
    # 保存
    final_img.save(OUTPUT_PATH)
    print(f"🎉 完成: {OUTPUT_PATH}")
    os.startfile(OUTPUT_PATH)

if __name__ == "__main__":
    main()

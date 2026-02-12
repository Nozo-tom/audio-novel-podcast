import os
import sys
import requests
import shutil
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
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

# ベース画像のパス (DALL-E生成用)
BASE_IMAGE_PATH = OUTPUT_DIR / f"{TARGET_NOVEL_NAME}_base.png"

# バリエーション定義
VARIANTS = [
    {
        "name": "mincho",
        "desc": "明朝体 (王道シリアス)",
        "font_candidates": ["C:\\Windows\\Fonts\\BIZ-UDMinchoM.ttc", "C:\\Windows\\Fonts\\msmincho.ttc"],
        "text_color": (255, 255, 255),
        "border_color": (0, 50, 100), # 濃い青
    },
    {
        "name": "gothic",
        "desc": "ゴシック体 (現代異能バトル)",
        "font_candidates": ["C:\\Windows\\Fonts\\meiryo.ttc", "C:\\Windows\\Fonts\\msgothic.ttc"],
        "text_color": (255, 255, 255),
        "border_color": (0, 0, 0), # 黒
    },
    {
        "name": "serif_bold",
        "desc": "太字明朝/教科書体 (学園ミステリー)",
        "font_candidates": ["C:\\Windows\\Fonts\\HGRPP1.TTC", "C:\\Windows\\Fonts\\HGRGY.TTC", "C:\\Windows\\Fonts\\constan.ttf"], # 創英角ポップか行書かコンスタディア
        "text_color": (230, 240, 255), # 薄い水色
        "border_color": (20, 20, 80), # 紺色
    }
]

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
    print("🎨 DALL-E 3 でベースイラストを生成中...")
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

def download_image(url, save_path):
    print("⬇️ 画像をダウンロード中...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"❌ ダウンロードエラー: {e}")
        return False

def draw_text_with_border(draw, text, x, y, font, text_color, border_color, border_width):
    for dx in range(-border_width, border_width + 1):
        for dy in range(-border_width, border_width + 1):
            if abs(dx) + abs(dy) == 0: continue
            draw.text((x + dx, y + dy), text, font=font, fill=border_color)
    draw.text((x, y), text, font=font, fill=text_color)

def create_cover_variant(base_image_path, variant_config):
    name = variant_config["name"]
    desc = variant_config["desc"]
    print(f"🔨 デザイン作成中: {desc}")
    
    try:
        image = Image.open(base_image_path).convert("RGBA")
    except Exception as e:
        print(f"❌ 画像読み込みエラー: {e}")
        return None

    draw = ImageDraw.Draw(image)
    width, height = image.size

    # フォント選択
    font_path = None
    for f in variant_config["font_candidates"]:
        if os.path.exists(f):
            font_path = f
            break
    
    if not font_path:
        font_path = "C:\\Windows\\Fonts\\msmincho.ttc" # Fallback
    
    # フォントサイズ
    title_size = 60
    author_size = 40
    try:
        title_font = ImageFont.truetype(font_path, title_size)
    except:
        title_font = ImageFont.load_default()
    try:
        author_font = ImageFont.truetype(font_path, author_size)
    except:
        author_font = ImageFont.load_default()

    # タイトル描画 (右、縦書き)
    lines = TITLE.split("\n")
    start_x = width - 100
    start_y = 50
    
    current_x = start_x
    for line in lines:
        current_y = start_y
        for char in line:
            # 句読点調整
            char_draw = char
            offset_x = 0
            offset_y = 0
            if char in "、。":
                offset_x = title_size * 0.6
                offset_y = -title_size * 0.6
            elif char in "っゃゅょ":
                 offset_x = title_size * 0.1
                 offset_y = -title_size * 0.1

            draw_text_with_border(
                draw, char_draw, current_x + offset_x, current_y + offset_y, 
                title_font, variant_config["text_color"], variant_config["border_color"], 4
            )
            current_y += title_size * 1.05
        current_x -= title_size * 1.5

    # 作者名 (左下、横書き)
    author_text = f"著：{AUTHOR}"
    bbox = draw.textbbox((0,0), author_text, font=author_font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    
    ax = 50
    ay = height - h - 50
    
    # 帯
    draw.rectangle([ax - 10, ay - 10, ax + w + 10, ay + h + 10], fill=(0,0,0,180))
    draw.text((ax, ay), author_text, font=author_font, fill=(255, 255, 255))
    
    # 保存
    output_filename = f"{TARGET_NOVEL_NAME}_{name}.png"
    save_path = OUTPUT_DIR / output_filename
    image.save(save_path)
    return save_path

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    # 1. ベース画像の準備 (なければ生成)
    if not BASE_IMAGE_PATH.exists():
        image_url = generate_image_dalle3(client, PROMPT)
        if not image_url: return
        download_image(image_url, BASE_IMAGE_PATH)
    else:
        print(f"ℹ️ 既存のベース画像を使用します: {BASE_IMAGE_PATH.name}")

    # 2. バリエーション作成
    created_files = []
    for var in VARIANTS:
        path = create_cover_variant(BASE_IMAGE_PATH, var)
        if path:
            created_files.append(path)

    # 3. 結果表示
    print("\n✨ 3パターンの表紙を作成しました！")
    for p in created_files:
        print(f"📁 {p.name}")
        os.startfile(p)

if __name__ == "__main__":
    main()

import os
import sys
import requests
import textwrap
import argparse
from io import BytesIO
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter

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
TARGET_NOVEL = r"c:\Users\natak\Documents\Novel\novels\completed\20250912_悪役令嬢に転生したので破滅フラグを回避しようと思ったら、原作.txt"
TITLE = "悪役令嬢に転生したので破滅フラグを回避しようと思ったら、\n原作主人公が思ってたより策略家だった件"
AUTHOR = "桜木ひより"

# 画像出力パス（小説と同じベース名で保存）
novel_path = Path(TARGET_NOVEL)
OUTPUT_FILENAME = f"{novel_path.stem}.png"
OUTPUT_PATH = Path(__file__).parent / "images" / OUTPUT_FILENAME
Path(__file__).parent.joinpath("images").mkdir(exist_ok=True)


# ラノベ風プロンプト
PROMPT = """
A stunning anime-style light novel cover illustration.
The scene depicts a beautiful noble daughter (villainess style) with long golden curly hair and sapphire blue eyes.
She wears an extremely elaborate, frilly, Victorian-rococo style dress in dark red and black.
She holds a delicate tea cup with an elegant pose, looking confident but slightly mischievous.
Background is a luxurious rose garden with a white gazebo and tea set.
Vibrant colors, sparkling effects, highly detailed masterpiece.
NO TEXT on the image itself (I will add it later).
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

def draw_text_with_effects(draw, pos, text, font, fill_color, stroke_color, stroke_width, shadow_offset=None, shadow_color=None):
    x, y = pos
    # 影
    if shadow_offset:
        sx, sy = shadow_offset
        draw.text((x + sx, y + sy), text, font=font, fill=shadow_color)
    
    # 縁取り（簡易版: 周囲に描画）
    for adj_x in range(-stroke_width, stroke_width+1):
        for adj_y in range(-stroke_width, stroke_width+1):
            draw.text((x+adj_x, y+adj_y), text, font=font, fill=stroke_color)

    # 本体
    draw.text((x, y), text, font=font, fill=fill_color)

def create_logo_style_title(image, title, author):
    print("✍️ タイトルロゴ風テキストを描画中...")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    
    # フォント設定 (MS明朝を使用、なければデフォルト)
    # 太字のBIZ-UDMinchoMがあればそれを使うと見栄えが良い
    font_candidates = [
        "C:\\Windows\\Fonts\\BIZ-UDMinchoM.ttc",
        "C:\\Windows\\Fonts\\msmincho.ttc",
        "C:\\Windows\\Fonts\\meiryo.ttc"
    ]
    
    font_path = None
    for f in font_candidates:
        if os.path.exists(f):
            font_path = f
            print(f"   フォント: {Path(f).name} を使用")
            break
            
    if not font_path:
        print("⚠️ 適切な日本語フォントが見つかりません。デフォルトを使用します。")
        font_path = None

    # タイトル設定
    try:
        title_size = 70
        author_size = 40
        if font_path:
            title_font = ImageFont.truetype(font_path, title_size)
            author_font = ImageFont.truetype(font_path, author_size)
        else:
            title_font = ImageFont.load_default()
            author_font = ImageFont.load_default()
    except Exception:
         title_font = ImageFont.load_default()
         author_font = ImageFont.load_default()

    # タイトルレイアウト
    # 上部に帯を入れるか、文字に強力な縁取りを入れて視認性を確保
    # 2行に分ける
    lines = title.split('\n')
    
    # 全体の高さ計算
    line_heights = []
    max_line_width = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        if w > max_line_width: max_line_width = w
    
    total_h = sum(line_heights) + 15 * (len(lines) - 1)
    
    start_y = 50
    current_y = start_y
    
    # タイトル描画（グラデーション風は難しいので、白文字＋ピンク縁取り＋ドロップシャドウでラノベ風に）
    main_color = (255, 255, 255)       # 白
    border_color = (180, 50, 100)      # 深いピンク/赤紫
    shadow_color = (50, 0, 20, 128)    # 半透明の影（PILのdraw.textはalpha対応が微妙なので黒で代用）

    for line in lines:
        # 中央寄せ
        bbox = draw.textbbox((0, 0), line, font=title_font)
        w = bbox[2] - bbox[0]
        x = (width - w) // 2
        
        # 影 (右下)
        draw.text((x + 6, current_y + 6), line, font=title_font, fill=(0,0,0))
        
        # 縁取り (太め)
        stroke_w = 6
        for dx in range(-stroke_w, stroke_w+1):
            for dy in range(-stroke_w, stroke_w+1):
                if dx*dx + dy*dy <= stroke_w*stroke_w: # 円形に近づける
                     draw.text((x+dx, current_y+dy), line, font=title_font, fill=border_color)

        # 本体
        draw.text((x, current_y), line, font=title_font, fill=main_color)
        
        current_y += line_heights[lines.index(line)] + 25 # 行間広め

    # 作者名（右下）
    author_text = f"著：{AUTHOR}"
    bbox = draw.textbbox((0, 0), author_text, font=author_font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    
    ax = width - w - 40
    ay = height - h - 40
    
    # 作者名の背景帯（半透明黒）で読みやすくする
    overlay = Image.new('RGBA', image.size, (0,0,0,0))
    draw_overlay = ImageDraw.Draw(overlay)
    padding = 10
    draw_overlay.rectangle(
        [ax - padding, ay - padding, ax + w + padding, ay + h + padding],
        fill=(0, 0, 0, 160)
    )
    image = Image.alpha_composite(image.convert('RGBA'), overlay)
    
    # 作者名描画（再取得が必要）
    draw = ImageDraw.Draw(image)
    draw.text((ax, ay), author_text, font=author_font, fill=(255, 255, 255))
    
    return image

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    
    print(f"🎯 ターゲット小説: {Path(TARGET_NOVEL).name}")
    print(f"💾 出力ファイル名: {OUTPUT_FILENAME}")
    
    # 画像生成
    image_url = generate_image_dalle3(client, PROMPT)
    if not image_url: return
    
    # ダウンロード
    img = download_image(image_url)
    if not img: return
    
    # 文字入れ
    final_img = create_logo_style_title(img, TITLE, AUTHOR)
    
    # 保存
    final_img.save(OUTPUT_PATH)
    print(f"🎉 表紙画像を作成しました: {OUTPUT_PATH}")
    
    # 自動で開く
    os.startfile(OUTPUT_PATH)

if __name__ == "__main__":
    main()

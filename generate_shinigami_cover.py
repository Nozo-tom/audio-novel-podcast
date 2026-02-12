import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import base64

# Windows文字化け対策
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# .env読み込み
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ===== 設定 =====
NOVEL_PATH = Path(__file__).parent / "novel.txt"
OUTPUT_DIR = Path(__file__).parent / "images"
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_PATH = OUTPUT_DIR / "cover.png"

# ===== GPT用指示書 (王道2Dアニメ・中華風排除Ver.) =====
SYSTEM_PROMPT = """
You are an elite Japanese light novel cover art director.
Your goal: Transform the novel into a commercially viable, 2D anime-style cover (Modern TV anime aesthetic).

STRICT ART STYLE (Based on high-end 2D light novel illustrations):
1. **Pure 2D Japanese Anime**: Modern TV anime style with clean, delicate lineart. NO 3D, NO semi-realism.
2. **Color Palette**: Bright, warm, and vibrant colors. Dreamy soft lighting with sparkling particles.
3. **Light Novel Style Eyes**: The eyes must be the focal point. Large, expressive, with complex multi-colored gradients, sparkling star-like highlights, and intricate iris patterns. Sharp, delicate eyelashes and soft gradients around the eyelids. 
4. **Moe Aesthetic**: Round cute facial proportions, small delicate nose, soft blush, radiant "pure anime" expressions. High character appeal.
5. **NO ORIENTAL/CHINESE MOTIFS**: Strictly avoid high collars, silk patterns, oriental architecture, or martial arts styles.
6. **Setting**: Western-style fantasy/medieval European isekai background.
7. **Framing**: Character's faces and important details must be FULLY IN FRAME, centrally composed, and not cropped.

WORKFLOW:
1. Summarize theme (Cooking, Isekai, Warmth/Family) and characters.
2. Select TEMPLATE A to E. 
3. Include ONE strong symbolic element: e.g., an old recipe book, a steaming delicious Japanese-style dish, or a fantasy kitchen utensil.
4. Output ONLY the final DALL-E prompt in English.

REQUIRED KEYWORDS:
Modern Japanese anime illustration, radiant sparkle, soft cel shading, 2D anime look, cute expressions, vibrant colors, bookstore display quality, professional anime key visual, high character appeal.
"""

def generate_cover_prompt(client, novel_text):
    text_3000 = novel_text[:3000]

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text_3000}
        ]
    )

    return response.choices[0].message.content


def generate_image(client, prompt):
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        response_format="b64_json"
    )

    image_base64 = response.data[0].b64_json
    return base64.b64decode(image_base64)


def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY が設定されていません")
        return

    if not NOVEL_PATH.exists():
        print("❌ novel.txt が見つかりません")
        return

    client = OpenAI(api_key=api_key)

    print("📖 小説読み込み...")
    novel_text = NOVEL_PATH.read_text(encoding="utf-8")

    print("🧠 カバープロンプト生成中...")
    cover_prompt = generate_cover_prompt(client, novel_text)

    print("🎨 画像生成中...")
    image_bytes = generate_image(client, cover_prompt)

    with open(OUTPUT_PATH, "wb") as f:
        f.write(image_bytes)

    print(f"🎉 完成: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

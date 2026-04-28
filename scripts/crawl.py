import os
import json
import asyncio
import time
import requests
import google.generativeai as genai
from twikit import Client
from datetime import datetime, timezone

# ===== 設定 =====
HASHTAGS = ["#AIart", "#AIイラスト", "#AIphotography", "#StableDiffusion", "#midjourney"]
LANGUAGES = ["ja", "en"]
MAX_PER_TAG = 40   # 1タグあたり取得件数
OUTPUT = "docs/posts.json"

PROMPT = """この画像を見て判定してください。
「アニメ・イラスト・マンガ調」要素が薄く、「実写写真に近いリアル表現」であればYES。
アニメ調・セルシェード・線画・典型的な漫画的キャラクターはNO。
回答は YES または NO の1語のみ。"""

# ===== Gemini =====
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash-lite")

def judge_image(image_url: str) -> bool:
    try:
        img_bytes = requests.get(image_url, timeout=15).content
        resp = model.generate_content([
            PROMPT,
            {"mime_type": "image/jpeg", "data": img_bytes}
        ])
        return "YES" in resp.text.upper()
    except Exception as e:
        print(f"judge error: {e}")
        return False

# ===== X =====
async def crawl():
    client = Client('en-US')
    await client.login(
        auth_info_1=os.environ["X_USERNAME"],
        auth_info_2=os.environ["X_EMAIL"],
        password=os.environ["X_PASSWORD"]
    )

    results = []
    seen = set()

    for tag in HASHTAGS:
        for lang in LANGUAGES:
            query = f"{tag} lang:{lang} filter:images -filter:retweets"
            print(f"Searching: {query}")
            try:
                tweets = await client.search_tweet(query, "Latest", count=MAX_PER_TAG)
            except Exception as e:
                print(f"search error: {e}")
                continue

            for t in tweets:
                if t.id in seen:
                    continue
                seen.add(t.id)
                if not t.media:
                    continue
                image_urls = [m.get("media_url_https") for m in t.media if m.get("type") == "photo"]
                if not image_urls:
                    continue

                # 1枚目で判定
                if not judge_image(image_urls[0]):
                    continue

                results.append({
                    "id": t.id,
                    "url": f"https://twitter.com/{t.user.screen_name}/status/{t.id}",
                    "user": t.user.screen_name,
                    "text": t.text[:200],
                    "image": image_urls[0],
                    "lang": lang,
                    "tag": tag,
                    "created_at": t.created_at,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
                time.sleep(2)  # Gemini RPM対策

    # 既存posts.jsonとマージ（最大200件・新しい順）
    existing = []
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as f:
            existing = json.load(f)
    by_id = {p["id"]: p for p in existing}
    for r in results:
        by_id[r["id"]] = r
    merged = sorted(by_id.values(), key=lambda x: x.get("fetched_at", ""), reverse=True)[:200]

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(merged)} posts")

if __name__ == "__main__":
    asyncio.run(crawl())

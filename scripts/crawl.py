import os
import json
import time
import requests
import google.generativeai as genai
from tweety import TwitterAsync
from datetime import datetime, timezone
import asyncio

# ===== 設定 =====
HASHTAGS = ["#AIart", "#AIイラスト", "#AIphotography", "#StableDiffusion", "#midjourney"]
LANGUAGES = ["ja", "en"]
MAX_PER_TAG = 40
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

# ===== X (tweety-ns) =====
async def crawl():
    app = TwitterAsync("session")
    await app.sign_in(
        os.environ["X_USERNAME"],
        os.environ["X_PASSWORD"],
        extra=os.environ.get("X_EMAIL")
    )

    results = []
    seen = set()

    for tag in HASHTAGS:
        for lang in LANGUAGES:
            query = f"{tag} lang:{lang} filter:images -filter:retweets"
            print(f"Searching: {query}")
            try:
                search = await app.search(query, pages=1, wait_time=2, filter_=None)
            except Exception as e:
                print(f"search error: {e}")
                continue

            count = 0
            for tweet in search:
                if count >= MAX_PER_TAG:
                    break
                tid = str(tweet.id)
                if tid in seen:
                    continue
                seen.add(tid)

                # 画像取得
                media = getattr(tweet, "media", None) or []
                image_urls = []
                for m in media:
                    mtype = getattr(m, "type", "") or getattr(m, "media_type", "")
                    url = getattr(m, "media_url_https", None) or getattr(m, "media_url", None)
                    if mtype == "photo" and url:
                        image_urls.append(url)
                if not image_urls:
                    continue

                if not judge_image(image_urls[0]):
                    continue

                user = tweet.author
                screen_name = getattr(user, "screen_name", None) or getattr(user, "username", "unknown")

                results.append({
                    "id": tid,
                    "url": f"https://twitter.com/{screen_name}/status/{tid}",
                    "user": screen_name,
                    "text": (tweet.text or "")[:200],
                    "image": image_urls[0],
                    "lang": lang,
                    "tag": tag,
                    "created_at": str(getattr(tweet, "created_on", "") or getattr(tweet, "date", "")),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
                count += 1
                time.sleep(2)

    # マージ
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
    print(f"Saved {len(merged)} posts (added {len(results)} new)")

if __name__ == "__main__":
    asyncio.run(crawl())

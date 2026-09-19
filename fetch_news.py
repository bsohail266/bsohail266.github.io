import os
import json
import requests
import feedparser
from google import genai

# Setup Gemini API Client
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret is missing in GitHub Repository Settings.")

client = genai.Client(api_key=api_key)
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Verified functional automotive RSS feeds
RSS_FEEDS = [
    "https://www.motor1.com/rss/news/all/",
    "https://auto.economictimes.indiatimes.com/rss/auto-technology",
    "https://auto.economictimes.indiatimes.com/rss/auto-components"
]

def fetch_rss_articles():
    collected_items = []
    # Add User-Agent header so feeds don't block GitHub Actions runners
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for url in RSS_FEEDS:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            parsed = feedparser.parse(response.content)
            print(f"Fetched {len(parsed.entries)} entries from {url}")

            for entry in parsed.entries[:5]:  # Top 5 per feed
                collected_items.append({
                    "title": getattr(entry, 'title', ''),
                    "url": getattr(entry, 'link', ''),
                    "summary": getattr(entry, 'summary', '')
                })
        except Exception as exc:
            print(f"Skipping feed {url}: {exc}")
            continue

    print(f"Total articles collected for AI processing: {len(collected_items)}")
    return collected_items

def summarize_with_gemini(items):
    prompt = f"""
    You are an expert Body in White (BIW) structural engineer.
    Analyze these news items and select up to 18 relevant articles.
    Return ONLY valid JSON without markdown fences or extra text, using this exact structure:

    {{
      "biw_news": [
        {{
          "title": "Article Title",
          "summary": "2-sentence engineering summary focused on BIW, materials, structural design, or joining technologies.",
          "url": "Original URL",
          "category": "Structural Engineering"
        }}
      ]
    }}

    Articles to analyze:
    {json.dumps(items, ensure_ascii=False)}
    """

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt
    )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "", 1).strip()

    return json.loads(text)

def main():
    target_path = "bodyinwhite.in/news.json"
    
    try:
        raw_items = fetch_rss_articles()
        if raw_items:
            result = summarize_with_gemini(raw_items)
        else:
            print("No items fetched from RSS feeds.")
            result = {"biw_news": []}
    except Exception as exc:
        print(f"Failed during AI processing: {exc}")
        result = {"biw_news": []}

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Successfully written output to {target_path}")

if __name__ == "__main__":
    main()

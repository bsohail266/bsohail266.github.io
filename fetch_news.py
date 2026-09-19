import os
import json
import requests
import feedparser
from google import genai

# Setup Gemini Client
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret is not configured in GitHub Repository Settings.")

client = genai.Client(api_key=api_key)
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Define news source feeds
RSS_FEEDS = [
    "https://www.autoblog.com/rss.xml",
    "https://www.automotive-news.com/rss",
    "https://www.greencarcongress.com/rss20.xml",
    "https://www.automotiveworld.com/feed/",
    "https://www.sae.org/news/rss",
    "https://www.autobeat.com/feed/",
    "https://www.compositesworld.com/rss/news"
]

def fetch_rss_articles():
    collected_items = []
    for url in RSS_FEEDS:
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "").lower()
            if "xml" not in content_type and "rss" not in content_type:
                continue

            parsed = feedparser.parse(response.content)
            for entry in parsed.entries[:3]:  # Top 3 per feed
                collected_items.append({
                    "title": getattr(entry, 'title', ''),
                    "url": getattr(entry, 'link', ''),
                    "summary": getattr(entry, 'summary', '')
                })
        except Exception as exc:
            print(f"Skipping feed {url}: {exc}")
            continue
    return collected_items

def summarize_with_gemini(items):
    prompt = f"""
    You are an expert Body in White (BIW) and automotive structural engineer.
    Analyze these news items and select up to 18 relevant articles.
    Return ONLY valid JSON with this exact key structure:

    {{
      "biw_news": [
        {{
          "title": "Article Title",
          "summary": "2-sentence engineering summary focused on BIW, materials, or joining.",
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
    # Save target path relative to script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "news.json")

    try:
        raw_items = fetch_rss_articles()
        if raw_items:
            result = summarize_with_gemini(raw_items)
        else:
            result = {"biw_news": []}
    except Exception as exc:
        print(f"Failed to generate AI news: {exc}")
        result = {"biw_news": []}

    # Guarantee news.json exists so Git never throws pathspec 128
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Successfully wrote {output_path}")

if __name__ == "__main__":
    main()

   

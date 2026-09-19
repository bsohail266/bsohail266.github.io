import os
import json
import requests
import feedparser
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret is missing in GitHub Repository Settings.")

client = genai.Client(api_key=api_key)

# Active Gemini models supported on standard API keys
PRIMARY_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
FALLBACK_MODEL = "gemini-2.0-flash"

RSS_FEEDS = [
    "https://www.motor1.com/rss/news/all/",
    "https://www.autocar.co.uk/rss",
    "https://www.autocarpro.in/rssfeeds",
    "https://auto.economictimes.indiatimes.com/rss/auto-technology",
    "https://auto.economictimes.indiatimes.com/rss/auto-components",
    "https://auto.economictimes.indiatimes.com/rss/topstories",
    "https://www.carsuk.net/feed/"
]

def extract_image_url(entry):
    """Extract lead image URL from media tags or enclosures in RSS entries."""
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            if media.get('medium') == 'image' or media.get('type', '').startswith('image/'):
                return media.get('url')
            if 'url' in media:
                return media.get('url')

    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return enc.get('href')

    return "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80"

def fetch_rss_articles():
    collected_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }

    for url in RSS_FEEDS:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            parsed = feedparser.parse(response.content)
            print(f"Fetched {len(parsed.entries)} entries from {url}")

            for entry in parsed.entries[:10]:
                img_url = extract_image_url(entry)
                collected_items.append({
                    "title": getattr(entry, 'title', ''),
                    "url": getattr(entry, 'link', ''),
                    "summary": getattr(entry, 'summary', ''),
                    "image_url": img_url
                })
        except Exception as exc:
            print(f"Skipping feed {url}: {exc}")
            continue

    print(f"Total articles collected: {len(collected_items)}")
    return collected_items

def summarize_with_gemini(articles):
    prompt = f"""
    You are an automotive engineering editor for bodyinwhite.in.
    Analyze the following list of raw automotive news articles and select EXACTLY 6 articles.
    
    Prioritize topics related to Body in White (BIW), lightweight structures, EV platforms, battery integration, manufacturing, or crash safety. If fewer than 6 strictly BIW articles exist, include broader automotive technology and new vehicle platform announcements to reach EXACTLY 6 articles.

    For each of the 6 selected items, retain its original `image_url` field from the input provided.

    Return EXACTLY a valid JSON object matching this schema without markdown code blocks:
    {{
      "biw_news": [
        {{
          "title": "Concise Technical Title",
          "url": "Article URL",
          "summary": "2-3 sentence summary focusing on structural or automotive engineering impact.",
          "image_url": "Original Image URL",
          "category": "Structural Engineering"
        }}
      ]
    }}

    CRITICAL INSTRUCTION: You MUST return EXACTLY 6 items in the `biw_news` array.

    Raw Articles Input:
    {json.dumps(articles, indent=2)}
    """

    for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            print(f"Generating 6 BIW news items with model: {model}")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Model {model} failed: {e}")

    raise RuntimeError("All Gemini model attempts failed.")

if __name__ == "__main__":
    raw_articles = fetch_rss_articles()
    if not raw_articles:
        print("No articles fetched from RSS feeds.")
        exit(1)

    news_data = summarize_with_gemini(raw_articles)

    # Save to root folder
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(news_data, f, indent=2)

    # Save to subfolder if it exists in your repository structure
    if os.path.exists("bodyinwhite.in"):
        with open("bodyinwhite.in/news.json", "w", encoding="utf-8") as f:
            json.dump(news_data, f, indent=2)

    print("Successfully generated news.json with 6 cards.")

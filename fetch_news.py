import os
import json
import requests
import feedparser
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret is missing in GitHub Repository Settings.")

client = genai.Client(api_key=api_key)

# Default to gemini-3.6-flash with gemini-2.5-flash as backup
PRIMARY_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODEL = "gemini-2.5-flash"

RSS_FEEDS = [
    # General Automotive & High-Volume Tech News
    "https://www.autoblog.com/rss.xml",
    "https://www.motor1.com/rss/news/all/",
    "https://www.motorauthority.com/rss-feeds",
    
    # Industry, Economics & Regional Market Feeds
    "https://auto.economictimes.indiatimes.com/rss/topstories",
    "https://auto.economictimes.indiatimes.com/rss/auto-technology",
    "https://auto.economictimes.indiatimes.com/rss/auto-components",
    
    # Structural, EV Platform & OEM Technical Press
    "https://automotive.einnews.com/rss/category/automotive",
    "https://feeds.highgearmedia.com/?site=TheCarConnection"
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

    # Fallback image if no media tag exists in the feed entry
    return "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80"

def fetch_rss_articles():
    collected_items = []
    # Using a modern Browser User-Agent to bypass 403 Forbidden blocks
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

            # Grab top 10 items per feed
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

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(news_data, f, indent=2)

    print("Successfully generated news.json with 6 cards.")
def summarize_with_gemini(items):
    prompt = f"""
    You are an expert Body in White (BIW) structural engineer.
    Analyze these news items and select up to 18 relevant articles.
    Return ONLY valid JSON without markdown code blocks, using this exact structure:

    {{
      "biw_news": [
        {{
          "title": "Article Title",
          "summary": "2-sentence engineering summary focused on BIW, materials, structural design, or joining.",
          "url": "Original URL",
          "image_url": "EXACT image_url provided in input data",
          "category": "Structural Engineering"
        }}
      ]
    }}

    CRITICAL INSTRUCTION: You MUST include the exact 'image_url' string from each input item in your returned JSON objects.

    Articles to analyze:
    {json.dumps(items, ensure_ascii=False)}
    """

    try:
        response = client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=prompt
        )
    except Exception as exc:
        print(f"Model '{PRIMARY_MODEL}' failed ({exc}). Retrying with '{FALLBACK_MODEL}'...")
        response = client.models.generate_content(
            model=FALLBACK_MODEL,
            contents=prompt
        )

    text = response.text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "", 1).strip()

    return json.loads(text)

def main():
    target_path = "bodyinwhite.in/news.json"
    raw_items = fetch_rss_articles()
    
    if not raw_items:
        raise RuntimeError("No articles could be fetched from the configured RSS feeds.")

    result = summarize_with_gemini(raw_items)

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Successfully updated {target_path}")

if __name__ == "__main__":
    main()

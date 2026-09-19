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

import re

# 6 distinct, high-quality fallback images related to Body in White & vehicle structures
BIW_FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80", # Sports coupe chassis
    "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=80", # Industrial laser welding
    "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=800&q=80", # Electric vehicle drivetrain
    "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=800&q=80", # Automotive body assembly
    "https://images.unsplash.com/photo-1558441719-aa34ff529280?auto=format&fit=crop&w=800&q=80", # Structural battery platform
    "https://images.unsplash.com/photo-1517524008697-84bbe3c3fd98?auto=format&fit=crop&w=800&q=80"  # EV battery / aluminum chassis
]

def clean_url(url):
    """Ensure image URLs are absolute and well-formed."""
    if not url:
        return None
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None

def extract_image_url(entry, index=0):
    """Extract lead image from RSS entry tags, HTML content, or select a unique fallback."""
    # 1. Try RSS Media Content tags
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            url = clean_url(media.get('url'))
            if url:
                return url

    # 2. Try RSS Enclosures
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                url = clean_url(enc.get('href'))
                if url:
                    return url

    # 3. Try parsing <img> tag from HTML description/summary content
    content_to_search = ""
    if hasattr(entry, 'summary'):
        content_to_search += entry.summary
    if hasattr(entry, 'description'):
        content_to_search += entry.description

    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_to_search, re.IGNORECASE)
    if img_match:
        url = clean_url(img_match.group(1))
        if url and not url.endswith('.gif'): # Skip tracking pixels
            return url

    # 4. Fallback to a unique engineering image per slot
    return BIW_FALLBACK_IMAGES[index % len(BIW_FALLBACK_IMAGES)]

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

    # Validate image URLs and assign unique slot fallbacks if missing or broken
    biw_list = news_data.get("biw_news", [])
    for idx, item in enumerate(biw_list):
        cleaned = clean_url(item.get("image_url"))
        if not cleaned or cleaned.endswith(".gif"):
            item["image_url"] = BIW_FALLBACK_IMAGES[idx % len(BIW_FALLBACK_IMAGES)]
        else:
            item["image_url"] = cleaned

    # Save to root folder
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(news_data, f, indent=2)

    # Save to subfolder if it exists in your repository structure
    if os.path.exists("bodyinwhite.in"):
        with open("bodyinwhite.in/news.json", "w", encoding="utf-8") as f:
            json.dump(news_data, f, indent=2)

    print("Successfully generated news.json with 6 cards.")

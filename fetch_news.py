import os
import json
import re
import time
import requests
import feedparser
from google import genai

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY secret is missing in GitHub Repository Settings.")

client = genai.Client(api_key=api_key)

# Cascade list including 3.6-flash with reliable production fallbacks
MODEL_CASCADES = [
    "gemini-3.6-flash",
    os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

RSS_FEEDS = [
    "https://www.motor1.com/rss/news/all/",
    "https://www.autocar.co.uk/rss",
    "https://www.autocarpro.in/rssfeeds",
    "https://auto.economictimes.indiatimes.com/rss/auto-technology",
    "https://auto.economictimes.indiatimes.com/rss/auto-components",
    "https://auto.economictimes.indiatimes.com/rss/topstories",
    "https://www.carsuk.net/feed/",
    "https://group.mercedes-benz.com/en/",
    "https://www.bmwgroup.com/en/company.html",
    "https://www.tatamotors.com",
    "https://www.mahindra.com/our-business/automotive"
]

# 6 distinct, high-quality fallback images related to Body in White & vehicle structures
BIW_FALLBACK_IMAGES = [
    "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80", # Card 1
    "https://images.unsplash.com/photo-1581092160607-ee22621dd758?auto=format&fit=crop&w=800&q=80", # Card 2
    "https://images.unsplash.com/photo-1563720223185-11003d516935?auto=format&fit=crop&w=800&q=80", # Card 3
    "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=800&q=80", # Card 4
    "https://images.unsplash.com/photo-1558441719-aa34ff529280?auto=format&fit=crop&w=800&q=80", # Card 5
    "https://images.unsplash.com/photo-1517524008697-84bbe3c3fd98?auto=format&fit=crop&w=800&q=80"  # Card 6
]

def clean_url(url):
    """Ensure image URLs are absolute and well-formed."""
    if not url:
        return None
    url = str(url).strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None

def extract_image_url(entry, index=0):
    """Extract lead image from RSS entry tags, HTML content, or select a unique fallback."""
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            url = clean_url(media.get('url'))
            if url:
                return url

    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                url = clean_url(enc.get('href'))
                if url:
                    return url

    content_to_search = ""
    if hasattr(entry, 'summary'):
        content_to_search += entry.summary
    if hasattr(entry, 'description'):
        content_to_search += entry.description

    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content_to_search, re.IGNORECASE)
    if img_match:
        url = clean_url(img_match.group(1))
        if url and not url.endswith('.gif'):
            return url

    return BIW_FALLBACK_IMAGES[index % len(BIW_FALLBACK_IMAGES)]

def fetch_rss_articles():
    collected_items = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    for url in RSS_FEEDS:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            parsed = feedparser.parse(response.content)
            print(f"Fetched {len(parsed.entries)} entries from {url}")

            for idx, entry in enumerate(parsed.entries[:10]):
                img_url = extract_image_url(entry, index=idx)
                
                # Basic cleaning of RSS HTML summary tag text
                summary_raw = getattr(entry, 'summary', '')
                clean_summary = re.sub('<[^<]+?>', '', summary_raw).strip()[:200]
                
                collected_items.append({
                    "title": getattr(entry, 'title', '').strip(),
                    "url": getattr(entry, 'link', '').strip(),
                    "summary": clean_summary,
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

    # Cascade through available models
    for model in MODEL_CASCADES:
        # Retry up to 2 times for temporary 503 capacity spikes
        for attempt in range(2):
            try:
                print(f"Attempting Gemini generation (Model: {model}, Attempt: {attempt + 1})...")
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                parsed_json = json.loads(response.text)
                if "biw_news" in parsed_json and len(parsed_json["biw_news"]) > 0:
                    print(f"Successfully generated news using model: {model}")
                    return parsed_json
            except Exception as e:
                print(f"Model {model} attempt {attempt + 1} failed: {e}")
                time.sleep(2) # Short delay before retry or fallback

    print("WARNING: All Gemini model attempts failed. Returning fallback raw RSS news slice.")
    
    # Graceful fallback: construct standard 6-card payload straight from RSS feeds
    fallback_cards = []
    for idx, item in enumerate(articles[:6]):
        fallback_cards.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "summary": item.get("summary") or "Automotive news update from RSS feed.",
            "image_url": item.get("image_url") or BIW_FALLBACK_IMAGES[idx % len(BIW_FALLBACK_IMAGES)],
            "category": "Automotive News"
        })
    return {"biw_news": fallback_cards}

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

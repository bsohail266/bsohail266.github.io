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
    "https://rss.app/feeds/9L2XDsRAmES6aHKD.xml",
    "https://rss.app/feeds/kZGAHISKoHrqHrp0.xml",
    "https://rss.app/feeds/EJIBllUyZPHThgh5.xml",
    "https://rss.app/feeds/FOEoWZL08pNjAFUp.xml",
    "https://rss.app/feeds/G7fBOGsCJ3GmEiRk.xml",
    "https://rss.app/feeds/Wpco9Bejny1LC9x0.xml",
    "https://rss.app/feeds/7ngZlU746jTraEA3.xml",
    "https://rss.app/feeds/qZrT6qTg8fmQtQlq.xml",
    "https://rss.app/feeds/iv5K1yNqQGrlZ58k.xml"
]

# 6 distinct, local fallback images mapped strictly to Cards 1 through 6
BIW_FALLBACK_IMAGES = [
    "Revolution-Body-Battery-Engineering.jpg",          # Card 1 Fallback
    "WATT-EV-Donut-Lab-Lightweight-Aluminium-Torqu.jpg",  # Card 2 Fallback
    "Lightweight-Materials.jpg",                       # Card 3 Fallback
    "safety-benchmark.jpg",                            # Card 4 Fallback
    "digital-twin-automotive.png",                     # Card 5 Fallback
    "tata-sierra-ev.jpg"                               # Card 6 Fallback
]

import re
from urllib.parse import urlparse, urljoin

# Keywords commonly found in ad banners, thumbnails, or non-lead images
JUNK_IMAGE_KEYWORDS = [
    'logo', 'avatar', 'icon', 'banner', 'ad-', '-ad', 'advertisement',
    'placeholder', 'share', 'facebook', 'twitter', 'linkedin', 'tracker',
    'pixel', 'button', 'widget', 'author', 'profile', 'comment'
]

def clean_url(url, base_url=""):
    """
    Sanitizes URLs, converts relative paths to HTTPS, and filters out junk/ad images.
    """
    if not url or not isinstance(url, str):
        return None

    cleaned = url.strip()

    # 1. Reject base64 data URIs or inline SVG assets
    if cleaned.startswith('data:') or cleaned.endswith('.svg'):
        return None

    # 2. Filter out junk keywords (logos, ads, tracking pixels)
    url_lower = cleaned.lower()
    if any(keyword in url_lower for keyword in JUNK_IMAGE_KEYWORDS):
        return None

    # 3. Handle protocol-relative URLs (e.g., //cdn.site.com/image.jpg)
    if cleaned.startswith('//'):
        cleaned = 'https:' + cleaned

    # 4. Handle relative paths (e.g., /wp-content/uploads/car.jpg)
    elif cleaned.startswith('/') and base_url:
        cleaned = urljoin(base_url, cleaned)

    # 5. Enforce HTTPS protocol for http:// URLs
    elif cleaned.startswith('http://'):
        cleaned = 'https://' + cleaned[7:]

    # Ensure URL starts with valid HTTPS protocol
    if not cleaned.startswith('https://'):
        return None

    # 6. Strip aggressive tracking/cropping query params if image ends in standard extension
    parsed = urlparse(cleaned)
    if parsed.netloc and parsed.path:
        if any(parsed.path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            cleaned = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    return cleaned

def extract_image_url(entry, index=0):
    """Extract lead image from RSS entry tags, HTML content, or select a unique fallback."""
    # 1. Check <media:content> tags
    if hasattr(entry, 'media_content') and entry.media_content:
        for media in entry.media_content:
            url = media.get('url', '')
            is_image_type = media.get('medium') == 'image' or media.get('type', '').startswith('image/')
            has_image_ext = any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp'])
            
            if is_image_type or has_image_ext:
                cleaned = clean_url(url)
                if cleaned:
                    return cleaned

    # 2. Check <enclosure> tags
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                cleaned = clean_url(enc.get('href'))
                if cleaned:
                    return cleaned

    # 3. Check <media:thumbnail> tags
    if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
        for thumb in entry.media_thumbnail:
            cleaned = clean_url(thumb.get('url'))
            if cleaned:
                return cleaned

    # 4. Search HTML content in summary/description (matches src, data-src, or data-original)
    content_to_search = ""
    if hasattr(entry, 'summary'):
        content_to_search += entry.summary
    if hasattr(entry, 'description'):
        content_to_search += entry.description

    if content_to_search:
        # Regex captures standard src= as well as lazy-loaded data-src= attributes
        img_match = re.search(r'<img[^>]+(?:src|data-src|data-original-src)=["\']([^"\']+)["\']', content_to_search, re.IGNORECASE)
        if img_match:
            raw_url = img_match.group(1)
            # Exclude tracking pixels, badges, and gifs
            if not raw_url.lower().endswith('.gif') and 'tracker' not in raw_url.lower():
                cleaned = clean_url(raw_url)
                if cleaned:
                    return cleaned

    # 5. Guaranteed local fallback if no valid RSS image found
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
    You are the Lead Automotive Structural & BIW Engineering Editor for bodyinwhite.in.
    Analyze the following list of raw automotive news articles and select EXACTLY 6 articles using a strict priority hierarchy.

    --- SELECTION HIERARCHY & WEIGHTING ---
    You must evaluate each article and prioritize them based on the following tiers:

    TIER 1 (HIGHEST PRIORITY - Include as many as exist):
    - Body in White (BIW), body structure, chassis design, spaceframe, monocoque architecture.
    - Sheet metal stamping, hot stamping, press hardening, casting (megacasting / gigacasting).
    - Joining technologies: Laser welding, SPR (Self-Piercing Riveting), structural adhesives, spot welding.
    - Lightweight materials: Ultra-High-Strength Steel (UHSS/AHSS), aluminum extrusions, carbon fiber (CFRP).
    - Crashworthiness, structural safety, Euro NCAP body deformation, roll-cage design.

    TIER 2 (MEDIUM PRIORITY - Use only if Tier 1 articles are fewer than 6):
    - EV platforms, skateboard chassis architecture, cell-to-body (CTB), cell-to-chassis (CTC) integration.
    - Suspension hardpoints, subframes, battery pack structural enclosures/trays.
    - Advanced manufacturing, body shop automation, press line technology.

    TIER 3 (FALLBACK ONLY - Use only if Tier 1 and Tier 2 combined are fewer than 6):
    - Broader automotive technology, general EV launches, powertrains, and OEM platform strategy.

    --- INSTRUCTIONS ---
    1. Sort and pick the top 6 highest-scoring articles following Tier 1 -> Tier 2 -> Tier 3 order.
    2. Rewrite the title to sound technical, precise, and professional for a structural engineering reader.
    3. Ensure the summary (2-3 sentences) explicitly highlights the engineering, structural, or material significance of the story.
    4. Retain the exact original `image_url` field from the input provided.
    5. CRITICAL INSTRUCTION: You MUST return EXACTLY 6 items in the `biw_news` array.

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

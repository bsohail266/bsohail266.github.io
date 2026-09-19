import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET

# Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Public RSS feeds focusing on automotive engineering & manufacturing
RSS_FEEDS = [
    "https://www.greencarcongress.com/rss20.xml",
    "https://www.automotiveworld.com/feed/",
    "https://www.sae.org/news/rss",
    "https://www.autobeat.com/feed/",
    "https://www.compositesworld.com/rss/news"
]

def fetch_rss_items():
    items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for url in RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                tree = ET.fromstring(response.read())
                channel = tree.find('channel')
                if channel is not None:
                    # Pull top 10 items per feed to ensure enough coverage for 18 items
                    for item in channel.findall('item')[:10]:
                        title = item.find('title').text if item.find('title') is not None else ""
                        desc = item.find('description').text if item.find('description') is not None else ""
                        link = item.find('link').text if item.find('link') is not None else ""
                        
                        # Clean HTML tags out of raw RSS description
                        clean_desc = re.sub('<[^<]+?>', '', desc) if desc else ""
                        items.append(f"Title: {title}\nSummary: {clean_desc[:300]}\nLink: {link}\n---")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            
    return "\n".join(items)

def summarize_with_gemini(raw_news):
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are an expert Body in White (BIW) automotive structural design engineer.
    Analyze the raw news snippets below and curate exactly 18 items, divided into 3 distinct sections of 6 items each.

    Raw News:
    {raw_news}

    Respond ONLY with a valid JSON object. Do not include markdown code block formatting (like ```json).
    The JSON object must have three main keys: "biw_news", "biw_features", and "biw_engineering".
    Each key must contain an array of exactly 6 objects.

    Structure requirements:
    1. "biw_news": 6 general automotive market news items impacting BIW, platforms, OEMs, and vehicle updates.
    2. "biw_features": 6 items focused on new architectural features (e.g., Giga-casting, skateboard platforms, crash structures, structural battery integration).
    3. "biw_engineering": 6 technical items focused on manufacturing, materials, and joining technology (e.g., AHSS, aluminum, laser welding, stamping, multi-material strategies).

    Each individual article object must have these exact keys:
    - "title": A concise 4-7 word headline focused on BIW engineering.
    - "description": A 2-sentence technical summary highlighting structural or manufacturing impact.
    - "tag": A short category tag (e.g., "Giga-Casting", "Lightweighting", "Laser Welding", "Crash Safety").
    - "link": The original source link.
    """

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}]
    }).encode('utf-8')

    req = urllib.request.Request(endpoint, data=payload, headers={'Content-Type': 'application/json'})
    
    with urllib.request.urlopen(req) as response:
        result = json.loads(response.read().decode('utf-8'))
        text_response = result['candidates'][0]['content']['parts'][0]['text']
        
        # Clean any accidental markdown code wrap
        cleaned = re.sub(r'```json|```', '', text_response).strip()
        return json.loads(cleaned)

def main():
    print("Fetching RSS feeds...")
    raw_news = fetch_rss_items()
    
    if not raw_news:
        print("No news items retrieved.")
        return

    print("Processing 18 news items across 3 categories with Gemini AI...")
    try:
        processed_news = summarize_with_gemini(raw_news)
        with open("news.json", "w", encoding="utf-8") as f:
            json.dump(processed_news, f, indent=2)
        print("Successfully generated news.json with 18 items.")
    except Exception as e:
        print(f"Failed to process news: {e}")

if __name__ == "__main__":
    main()

import os
import json
import datetime
import traceback
import instaloader
import requests
from flask import Flask, render_template, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from bs4 import BeautifulSoup
from mistralai import Mistral
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Update the Limiter initialization
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["10 per minute"]
)
limiter.init_app(app)

# Ensure downloads and logs directories exist
DOWNLOAD_FOLDER = 'downloads'
LOGS_FOLDER = 'logs'
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(LOGS_FOLDER, exist_ok=True)

# Initialize the Mistral client securely
API_KEY = "fb7cL6YvR3KAgcY9I1kjp4qx4m78iK1M"
MODEL = "mistral-large-latest"
client = Mistral(api_key=API_KEY)

def safe_get_post_info(post):
    """
    Safely extract post information with robust error handling
    """
    try:
        return {
            "post_id": str(post.mediaid),
            "timestamp": str(post.date_utc),
            "caption": post.caption or "",
            "likes": post.likes or 0,
            "is_video": post.is_video,
            "media_type": post.typename or 'Unknown'
        }
    except Exception as e:
        return {
            "error": "Post extraction failed",
            "details": str(e),
            "trace": traceback.format_exc()
        }

def log_analysis(username, posts_data):
    """
    Enhanced logging with more context and error handling
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(LOGS_FOLDER, f"{username}_analysis_{timestamp}.json")
    
    try:
        with open(log_filename, 'w', encoding='utf-8') as f:
            json.dump({
                "username": username,
                "timestamp": timestamp,
                "total_posts": len(posts_data),
                "posts": posts_data
            }, f, ensure_ascii=False, indent=4)
        return log_filename
    except Exception as log_error:
        print(f"Logging failed: {log_error}")
        return None

def advanced_amazon_search(product_name):
    """
    Enhanced product search combining both old and new search strategies
    for better results
    """
    clean_name = ' '.join(product_name.split())
    search_url = f"https://www.amazon.in/s?k={'+'.join(clean_name.split())}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.amazon.in/"
    }
    
    try:
        with requests.Session() as session:
            response = session.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            product_selectors = [
                'a.a-link-normal.s-underline-text.s-underline-link-text.s-link-style.a-text-normal[href*="/dp/"]',
                'a.a-link-normal.s-no-outline[href*="/dp/"]',
                'div.s-result-item a.a-link-normal[href*="/dp/"]',
                'a.a-link-normal.s-image[href*="/dp/"]',
                'a.a-link-normal.s-underline-text[href*="/dp/"]',
                'a.a-no-hover.a-link-normal[href*="/dp/"]'
            ]
            
            for selector in product_selectors:
                products = soup.select(selector)
                for product in products[:5]:
                    href = product.get('href', '')
                    if href and '/dp/' in href:
                        full_link = f"https://www.amazon.in{href}" if not href.startswith('http') else href
                        verify_response = session.head(full_link, headers=headers, timeout=5)
                        if verify_response.status_code == 200:
                            return full_link
            
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '')
                if '/dp/' in href:
                    full_link = f"https://www.amazon.in{href}" if not href.startswith('http') else href
                    return full_link
                    
        return None
            
    except Exception as e:
        print(f"Advanced search error for {product_name}: {e}")
        return None

def generate_gift_suggestions(posts_data):
    """
    Enhanced AI-powered gift suggestion generation with improved search
    """
    try:
        chat_response = client.chat.complete(
            model=MODEL,
            messages=[{
                "role": "user", 
                "content": f"""
                Analyze these Instagram posts and generate 15-20 unique, 
                personalized gift suggestions that reflect the user's interests:
                {json.dumps(posts_data, indent=2)}
                """
            }]
        )
        
        raw_suggestions = chat_response.choices[0].message.content.split('\n')
        curated_suggestions = []
        
        for suggestion in raw_suggestions:
            suggestion = suggestion.strip()
            if suggestion:
                product_link = advanced_amazon_search(suggestion)
                curated_suggestions.append((suggestion, product_link or "Link not found"))
                if len(curated_suggestions) >= 15:
                    break
        
        return curated_suggestions
    except Exception as e:
        print(f"Gift suggestion generation error: {e}")
        return []

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def index():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        
        try:
            L = instaloader.Instaloader()
            profile = instaloader.Profile.from_username(L.context, username)
            
            posts_data = []
            download_path = os.path.join(DOWNLOAD_FOLDER, username)
            os.makedirs(download_path, exist_ok=True)
            
            # Limit to 20 most recent posts
            for post in list(profile.get_posts())[:20]:  # <-- Added limit here
                try:
                    L.download_post(post, target=username)
                    post_info = safe_get_post_info(post)
                    posts_data.append(post_info)
                except Exception as post_error:
                    posts_data.append({
                        "error": "Individual post download failed",
                        "details": str(post_error)
                    })
            
            log_file = log_analysis(username, posts_data)
            products_with_links = generate_gift_suggestions(posts_data)
            
            return render_template('gift_suggestions.html', products=products_with_links)
        
        except instaloader.exceptions.ProfileNotExistsException:
            return jsonify({"error": "Profile not found"}), 404
        except instaloader.exceptions.PrivateProfileNotFollowedException:
            return jsonify({"error": "Private profile"}), 403
        except Exception as e:
            return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500
    
    return render_template('index.html')

@app.errorhandler(429)
def ratelimit_handler(e):
    """
    Handle rate limiting errors
    """
    return jsonify({
        "error": "Too many requests. Please try again later.",
        "description": str(e)
    }), 429

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

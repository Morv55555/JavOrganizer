import requests
from bs4 import BeautifulSoup
import re
import logging
from urllib.parse import urljoin
import time

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- Constants ---
BASE_URL = "https://www.javlibrary.com"
SEARCH_URL_TEMPLATE = f"{BASE_URL}/en/vl_searchbyid.php?keyword={{code}}"
# REMOVED: USER_AGENT constant
# REMOVED: CF_CLEARANCE constant
REVERSE_NAME = True
SCRAPER_SLEEP_DURATION = 5 # Seconds to wait after scraping this site


# --- Helper to check for Cloudflare challenge ---
def _is_cloudflare_challenge(response_text):
    soup_check = BeautifulSoup(response_text, 'html.parser')
    title_tag = soup_check.find('title')
    if title_tag and ("cloudflar" in title_tag.text.lower() or "attention required" in title_tag.text.lower() or "just a moment..." in title_tag.text.lower()):
        return True
    if "challenge-platform" in response_text.lower() or "verify you are human" in response_text.lower():
        return True
    return False

def extract_text_from_div(soup, div_id):
    div = soup.find('div', id=div_id)
    if div:
        td = div.find('td', class_='text')
        if td:
            return td.get_text(strip=True)
    return None

def extract_link_text_from_div(soup, div_id):
    div = soup.find('div', id=div_id)
    if div:
        td = div.find('td', class_='text')
        if td:
            a_tag = td.find('a')
            if a_tag:
                return a_tag.get_text(strip=True)
    return None


# --- URL Finder Function ---
def get_javlibrary_url_from_id(id_str, user_agent=None, cf_clearance_token=None): # Added user_agent and cf_clearance_token
    if not id_str:
        logging.warning("Empty ID string provided.")
        return None

    session = requests.Session() # Create new session for this request
    headers = {}
    if user_agent:
        headers['User-Agent'] = user_agent
    else:
        logging.warning("Javlibrary: No User-Agent provided for URL finding.")
        # Fallback or let it fail if UA is critical
        headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


    session.headers.update(headers)

    if cf_clearance_token:
        session.cookies.set('cf_clearance', cf_clearance_token, domain='.javlibrary.com')
    else:
        logging.warning("Javlibrary: No CF Clearance token provided for URL finding. Expect CF challenge.")

    search_url = SEARCH_URL_TEMPLATE.format(code=id_str)
    try:
        resp = session.get(search_url, timeout=20, allow_redirects=True)
        
        if _is_cloudflare_challenge(resp.text):
            logging.warning(f"Javlibrary: Cloudflare challenge detected when searching for ID: {id_str}")
            return "CF_CHALLENGE"

        if resp.status_code == 200:
            if "/?v=" in resp.url:
                logging.info(f"Direct movie page found: {resp.url}")
                return resp.url
            else:
                logging.warning(f"Search did not lead to a direct movie page for ID: {id_str}. URL: {resp.url}")
                return None 
        else:
            logging.error(f"Failed to fetch search page. Status: {resp.status_code}, URL: {search_url}")
            logging.error(f"Response text (first 300 chars): {resp.text[:300]}")
            return None
    except requests.RequestException as e:
        logging.error(f"Error fetching search page: {e}")
        return None

# --- Scraper Function ---
def scrape_javlibrary(url, user_agent=None, cf_clearance_token=None):
    if not url:
        logging.error("No URL provided to scraper.")
        return None
    
    if url == "CF_CHALLENGE": 
        logging.debug("scrape_javlibrary received CF_CHALLENGE status directly.")
        return "CF_CHALLENGE"

    session = requests.Session()
    headers = {}
    if user_agent:
        headers['User-Agent'] = user_agent
    else:
        logging.warning("Javlibrary: No User-Agent provided for scraping. Using a default.")
        headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    headers['Accept-Language'] = 'en-US,en;q=0.5'
    session.headers.update(headers)

    if cf_clearance_token:
        session.cookies.set('cf_clearance', cf_clearance_token, domain='.javlibrary.com')
    else:
        logging.warning("Javlibrary: No CF Clearance token provided for scraping. Expect CF challenge.")
        
    try:
        response = session.get(url, timeout=25)
        if _is_cloudflare_challenge(response.text):
            logging.warning(f"Javlibrary: Cloudflare challenge detected on page: {url}")
            return "CF_CHALLENGE"
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Failed to fetch page {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    data = {'source': 'javlibrary', 'url': url}

    # --- ID ---
    # Get ID from the dedicated div first. This is the most reliable source for the ID.
    actual_id = extract_text_from_div(soup, 'video_id')
    data['id'] = actual_id 
    
    if not actual_id:
        logging.warning(f"Javlibrary: Could not determine actual ID from 'video_id' div for URL: {url}. Title processing will use raw title.")

    # --- Title and Title Raw ---
    raw_title_from_h3_link = ""
    title_element_h3_a = soup.select_one("h3.post-title.text a") # Corrected selector name for clarity
    if title_element_h3_a:
        raw_title_from_h3_link = title_element_h3_a.get_text(strip=True)

    # Process the title
    processed_title = raw_title_from_h3_link # Default to raw if ID stripping fails or no ID
    
    if actual_id and raw_title_from_h3_link: # Only proceed if we have an ID and a raw title
        # Check if the raw title string starts with the actual_id
        if raw_title_from_h3_link.startswith(actual_id):
            # Remove the ID part from the beginning of the raw title
            temp_title_after_id_removal = raw_title_from_h3_link[len(actual_id):].strip()
            
            # Now, remove a leading separator (like " - " or just "-") if it exists
            # We need to be careful here not to remove a hyphen that's part of the actual title
            # This logic assumes the ID is followed by a distinct separator if one is used by Javlibrary in this H3 context
            
            # Common separators Javlibrary might use after the ID in the H3 text:
            # " - " (space-hyphen-space)
            # "-" (just hyphen, if spaces are already stripped by .strip() above)
            # " " (a single space if no hyphen)
            
            # Let's try to match specific patterns for removal
            if temp_title_after_id_removal.startswith(" - "):
                processed_title = temp_title_after_id_removal[3:].strip() # Remove " - "
            elif temp_title_after_id_removal.startswith("-"):
                processed_title = temp_title_after_id_removal[1:].strip() # Remove "-"
            elif temp_title_after_id_removal.startswith("—"): # Em-dash
                processed_title = temp_title_after_id_removal[1:].strip() # Remove "—"
            else:
                # If none of the specific separators are found right after the ID,
                # then temp_title_after_id_removal (which is raw_title - ID) is likely the correct title.
                # Or, it could be that the ID and Title are just space-separated in the H3.
                # .strip() already handled leading spaces on temp_title_after_id_removal.
                processed_title = temp_title_after_id_removal 
            
            logging.info(f"[scrape_javlibrary] Original H3 Text: '{raw_title_from_h3_link}'. Known ID: '{actual_id}'. Title after ID removal: '{temp_title_after_id_removal}'. Final Processed Title: '{processed_title}'")
        else:
            # This case means the H3 title text does NOT start with the known ID.
            # This would be unusual if Javlibrary is consistent.
            logging.warning(f"[scrape_javlibrary] Raw H3 title '{raw_title_from_h3_link}' does NOT start with known ID '{actual_id}'. Using raw H3 title as processed title.")
            processed_title = raw_title_from_h3_link # Fallback to the full H3 text
    elif not actual_id:
        logging.warning(f"[scrape_javlibrary] No actual_id found. Using raw H3 title for processed title: '{raw_title_from_h3_link}'")
        processed_title = raw_title_from_h3_link # Fallback if no ID

    data['title_raw'] = processed_title.strip()
    data['title'] = processed_title.strip() # Ensure final title is stripped

    # --- Release Date & Year ---
    data['release_date'] = extract_text_from_div(soup, 'video_date')
    if data['release_date']:
        try: 
            data['release_year'] = data['release_date'].split('-')[0]
        except Exception: 
            data['release_year'] = None
    else: 
        data['release_year'] = None

    # --- Director ---
    data['director'] = extract_link_text_from_div(soup, 'video_director')

    # --- Runtime ---
    runtime_text = None
    runtime_div = soup.find('div', id='video_length')
    if runtime_div:
        runtime_span = runtime_div.find('span', class_='text')
        if runtime_span: 
            runtime_text = runtime_span.get_text(strip=True)
            runtime_match = re.search(r'(\d+)', runtime_text) # Extract numbers
            if runtime_match:
                data['runtime'] = runtime_match.group(1)
            else:
                data['runtime'] = None 
        else: data['runtime'] = None
    else: data['runtime'] = None
    
    # --- Maker (Studio) ---
    data['maker'] = extract_link_text_from_div(soup, 'video_maker')

    # --- Label ---
    data['label'] = extract_link_text_from_div(soup, 'video_label')
    
    # --- Genres ---
    data['genres'] = []
    genres_div = soup.find('div', id='video_genres')
    if genres_div:
        genres_td = genres_div.find('td', class_='text')
        if genres_td: 
            data['genres'] = [a.text.strip() for a in genres_td.find_all('a')]

    # --- Poster URL (Cover URL) ---
    poster_url_val = None 
    poster_div = soup.find('div', id='video_jacket')
    if poster_div:
        img_tag = poster_div.find('img', id='video_jacket_img')
        if img_tag and img_tag.get('src'): 
            poster_url_val = urljoin(url, img_tag['src'])
    data['cover_url'] = poster_url_val
    
    # --- Cast (Actresses) ---
    data['actresses'] = []
    cast_div = soup.find('div', id='video_cast')
    if cast_div:
        cast_td = cast_div.find('td', class_='text')
        if cast_td:
            cast_spans = cast_td.find_all('span', class_='cast')
            for cast_span in cast_spans:
                actress_name = None
                alias_names_list = [] # Initialize as list
                star_a = cast_span.select_one('span.star a')
                if star_a: 
                    actress_name = star_a.get_text(strip=True)
                
                alias_elements = cast_span.select('span.alias')
                alias_names_list = [alias.get_text(strip=True) for alias in alias_elements]

                if actress_name: 
                    if REVERSE_NAME and ' ' in actress_name:
                        # Handle names like "FirstName LastName" vs "LastName FirstName"
                        # This simple reverse might not be perfect for all name structures.
                        actress_name = ' '.join(reversed(actress_name.split(' ', 1)))
                    
                    # For now, store aliases separately if your main app can use them.
                    # If you need them appended to the name, that logic would go here.
                    data['actresses'].append({'name': actress_name, 'aliases': alias_names_list})

    if not data['actresses']:
        data['actresses'].append({'name': "Unknown", 'aliases': []})

    # --- Screenshot URLs ---
    data['screenshot_urls'] = []
    preview_div = soup.find('div', class_='previewthumbs')
    if preview_div:
        screenshot_tags = preview_div.find_all('a')
        for tag in screenshot_tags:
            href = tag.get('href')
            if href:
                data['screenshot_urls'].append(urljoin(url, href)) # Ensure absolute URLs
    
    # Final check
    if not data.get('id') and not data.get('title'): 
        logging.warning(f"Javlibrary: Scraped page {url} but ID and processed Title are critically missing.")
        return None 

    logging.info(f"Scraped data: ID='{data.get('id')}', Processed Title='{data.get('title')}', Raw Title='{data.get('title_raw')}'")
    
    logging.debug(f"Sleeping for {SCRAPER_SLEEP_DURATION} seconds after scraping Javlibrary...")
    time.sleep(SCRAPER_SLEEP_DURATION)
    
    return data

# --- Testing ---
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    
    test_user_agent = input("Enter User-Agent for testing Javlibrary: ")
    test_cf_token = input("Enter CF Clearance token for testing Javlibrary: ")

    if not test_user_agent or not test_cf_token:
        print("User-Agent and CF Token are required for testing.")
    else:
        test_ids = ['ABF-217'] 
        for test_id in test_ids:
            print(f"\n--- Testing ID: {test_id} ---")
            # Assuming get_javlibrary_url_from_id is defined and works
            url_result = get_javlibrary_url_from_id(test_id, user_agent=test_user_agent, cf_clearance_token=test_cf_token)
            
            if url_result == "CF_CHALLENGE": print("Javlibrary Test: Received CF Challenge during URL finding.")
            elif url_result:
                print(f"Javlibrary Test: Found URL: {url_result}")
                data_result = scrape_javlibrary(url_result, user_agent=test_user_agent, cf_clearance_token=test_cf_token)
                if data_result == "CF_CHALLENGE": print("Javlibrary Test: Received CF Challenge during scraping.")
                elif data_result:
                    print(f"Title (Processed): {data_result.get('title')}")
                    print(f"Title (Raw): {data_result.get('title_raw')}")
                    print(f"ID: {data_result.get('id')}")
                else: print("Javlibrary Test: Failed to scrape data (not a CF challenge, or no data found).")
            else: print("Javlibrary Test: Could not find movie URL (not a CF challenge).")
            print("-" * 40)
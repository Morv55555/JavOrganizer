# In r18dev_scraper.py

import requests
import logging
import html

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- User Agent ---
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'

# --- URL Finder Function (get_r18dev_url_from_id - no changes) ---
def get_r18dev_url_from_id(id_str):
    logging.debug(f"Attempting to find R18.Dev URL for ID: '{id_str}'")
    if not id_str: logging.warning("Received empty ID string."); return None
    search_id = id_str
    search_url = f"https://r18.dev/videos/vod/movies/detail/-/dvd_id={search_id}/json"
    combined_url = None
    try:
        logging.debug(f"Performing GET on URL: {search_url}")
        response = requests.get(search_url, headers={'User-Agent': USER_AGENT}, timeout=20)
        response.raise_for_status()
        data = response.json()
        content_id = data.get('content_id')
        if content_id:
            combined_url = f"https://r18.dev/videos/vod/movies/detail/-/combined={content_id}/json"
            logging.info(f"Found R18.Dev content_id '{content_id}' for ID '{id_str}'. Combined URL: {combined_url}")
        else: logging.warning(f"No content_id found for ID '{id_str}' at {search_url}. Response: {data}")
    except requests.exceptions.RequestException as e: logging.error(f"Error during R18.Dev URL search for '{id_str}': {e}")
    except ValueError as e: logging.error(f"Error decoding JSON response for '{id_str}': {e}")
    except Exception as e: logging.error(f"An unexpected error occurred during R18.Dev URL search for '{id_str}': {e}")
    return combined_url

# --- Data Scraper Function ---
def scrape_r18dev(url):
    """
    Scrapes data from the R18.Dev combined API URL.
    """
    logging.debug(f"Attempting to scrape R18.Dev data from URL: {url}")
    if not url or '/combined=' not in url:
        logging.error(f"Invalid R18.Dev combined URL provided: {url}")
        return None

    try:
        logging.debug(f"Performing GET on URL: {url}")
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=25)
        response.raise_for_status()
        webRequest = response.json()
        logging.info(f"Successfully scraped R18.Dev data for URL: {url}")

    except requests.exceptions.RequestException as e: logging.error(f"Error during R18.Dev data scrape for '{url}': {e}"); return None
    except ValueError as e: logging.error(f"Error decoding JSON response for '{url}': {e}"); return None
    except Exception as e: logging.error(f"An unexpected error occurred during R18.Dev data scrape for '{url}': {e}"); return None

        # --- Extract data ---
    data = {}
    # --- Basic Info (no change) ---
    data['source'] = 'r18dev'
    data['url'] = url
    data['content_id'] = webRequest.get('content_id')
    data['id'] = webRequest.get('dvd_id')
    # --- Title Handling (no change) ---
    title_en = webRequest.get('title_en') or webRequest.get('title')
    title_ja = webRequest.get('title_ja')
    data['title'] = html.unescape(title_en).strip() if title_en else None
    data['title_raw'] = data['title']
    data['originaltitle'] = html.unescape(title_ja).strip() if title_ja else None
    # --- Description (no change) ---
    description = webRequest.get('comment_en')
    data['description'] = html.unescape(description).strip() if description else None
    # --- Dates (no change) ---
    release_date_str = webRequest.get('release_date', '').split(' ')[0]
    data['release_date'] = release_date_str if release_date_str else None
    data['release_year'] = release_date_str.split('-')[0] if release_date_str and '-' in release_date_str else None
    # --- Runtime (no change) ---
    data['runtime'] = str(webRequest.get('runtime_mins')) if webRequest.get('runtime_mins') is not None else None
    # --- Credits (director and maker no change) ---
    data['director'] = None; directors = webRequest.get('directors')
    if directors and isinstance(directors, list) and len(directors) > 0: director_info = directors[0]; data['director'] = director_info.get('name_romaji') or director_info.get('name_kanji')
    final_maker = None # Default to None
    maker_en = webRequest.get('maker_name_en') # Get English name

    if maker_en is not None: # Check if key exists
        # Process English name (unescape, ensure string, strip)
        processed_en = html.unescape(str(maker_en)).strip()
        if processed_en: # Check if not empty after processing
            final_maker = processed_en
            logging.debug(f"  Using English maker: '{final_maker}'")

    # Fallback to Japanese name ONLY if English name wasn't found or was empty
    if final_maker is None:
        maker_ja = webRequest.get('maker_name_ja') # Get Japanese name
        if maker_ja is not None: # Check if key exists
            # Process Japanese name (unescape, ensure string, strip)
            processed_ja = html.unescape(str(maker_ja)).strip()
            if processed_ja: # Check if not empty after processing
                final_maker = processed_ja
                logging.debug(f"  Fallback to Japanese maker: '{final_maker}'")
        else:
             logging.debug("  English maker was invalid, and Japanese maker key ('maker_name_ja') not found.")
    elif maker_en is None:
        logging.debug("  English maker key ('maker_name_en') not found.")


    data['maker'] = final_maker # Assign the final result (could be None)

    # --- >>> ADJUSTED Label Logic <<< ---
    label_en = webRequest.get('label_name_en')
    label_ja = webRequest.get('label_name_ja')
    final_label = None # Default to None

    if label_en:
        processed = html.unescape(label_en).strip()
        if processed: # Check if not empty after processing
            final_label = processed

    if final_label is None and label_ja: # Only check ja if en didn't yield a result
        processed = html.unescape(label_ja).strip()
        if processed: # Check if not empty after processing
            final_label = processed

    data['label'] = final_label
    # --- >>> END ADJUSTMENT <<< ---

    # --- >>> ADJUSTED Series Logic <<< ---
    series_en = webRequest.get('series_name_en')
    series_ja = webRequest.get('series_name_ja')
    final_series = None # Default to None

    if series_en:
        processed = html.unescape(series_en).strip()
        if processed: # Check if not empty after processing
            final_series = processed

    if final_series is None and series_ja: # Only check ja if en didn't yield a result
        processed = html.unescape(series_ja).strip()
        if processed: # Check if not empty after processing
            final_series = processed

    data['series'] = final_series
    # --- >>> END ADJUSTMENT <<< ---

    # --- Actresses (corrected) ---
    data['actresses'] = []
    actresses_list_from_api = webRequest.get('actresses')

    if actresses_list_from_api and isinstance(actresses_list_from_api, list):
        for actor_data in actresses_list_from_api: # Iterate through each item
            if isinstance(actor_data, dict):
                final_actress_name = None
                
                # Try Romaji name first
                name_romaji = actor_data.get('name_romaji')
                if name_romaji:
                    processed_romaji = html.unescape(str(name_romaji)).strip()
                    if processed_romaji:
                        final_actress_name = processed_romaji
                
                # Fallback to Kanji name if Romaji was not found or empty
                if not final_actress_name:
                    name_kanji = actor_data.get('name_kanji')
                    if name_kanji:
                        processed_kanji = html.unescape(str(name_kanji)).strip()
                        if processed_kanji:
                            final_actress_name = processed_kanji
                
                if final_actress_name:
                    data['actresses'].append({'name': final_actress_name})
                else:
                    logging.debug(f"  Skipping actress - no valid Romaji or Kanji name found for data: {actor_data.get('id')}")
            else:
                logging.warning(f"  Skipping item in actresses list because it's not a dictionary: {actor_data}")
        logging.info(f"Finished processing actresses. Added {len(data['actresses'])} actresses.")
    elif actresses_list_from_api is not None:
        logging.warning(f"Expected 'actresses' to be a list, but got type {type(actresses_list_from_api)}. Value: {actresses_list_from_api}")
    else:
        logging.debug("No 'actresses' key found in API response or it was null.")
        
    # --- Genres (no change) ---
    data['genres'] = [] # Initialize empty list
    categories = webRequest.get('categories') # Get the list of category dictionaries

    if categories and isinstance(categories, list):
        logging.debug(f"Processing {len(categories)} categories found.")
        for category in categories:
            final_genre = None # Reset for each category item

            if isinstance(category, dict): # Ensure the item is a dictionary
                # --- Prioritize English Name ---
                name_en = category.get('name_en')
                if name_en is not None: # Check if key exists
                    # Process (unescape HTML entities, remove leading/trailing whitespace)
                    processed_en = html.unescape(str(name_en)).strip()
                    if processed_en: # Check if not empty after processing
                        final_genre = processed_en
                        logging.debug(f"  Using English genre: '{final_genre}'")

                # --- Fallback to Japanese Name ---
                # Only proceed if English name wasn't found or was empty after processing
                if final_genre is None:
                    name_ja = category.get('name_ja')
                    if name_ja is not None: # Check if key exists
                        # Process (unescape HTML entities, remove leading/trailing whitespace)
                        processed_ja = html.unescape(str(name_ja)).strip()
                        if processed_ja: # Check if not empty after processing
                            final_genre = processed_ja
                            logging.debug(f"  Fallback to Japanese genre: '{final_genre}'")

                # --- Add to list if a valid genre was found ---
                if final_genre:
                    # Optional: check for duplicates before adding if needed, but usually not necessary
                    # if final_genre not in data['genres']:
                    data['genres'].append(final_genre)
                else:
                    logging.debug(f"  Skipping category item - no valid English or Japanese name found: {category}")

            else:
                logging.warning(f"  Skipping item in categories list because it's not a dictionary: {category}")

        logging.info(f"Finished processing categories. Found {len(data['genres'])} genres: {data['genres']}")

    elif categories is not None:
        # Log if 'categories' key exists but isn't a list
        logging.warning(f"Expected 'categories' to be a list, but got type {type(categories)}. Value: {categories}")
    else:
        # Log if 'categories' key is missing entirely
        logging.debug("No 'categories' key found in API response.")

    # --- Images (No change needed - URLs are language-agnostic) ---
    data['cover_url'] = webRequest.get('jacket_full_url')
    logging.debug(f"Cover URL from API ('jacket_full_url'): {data['cover_url']}")
    data['folder_image_constructed_url'] = None
    '''
    data['folder_image_constructed_url'] = webRequest.get('jacket_thumb_url')
    if data['folder_image_constructed_url']:
        logging.info(f"Found Folder URL (jacket_thumb_url): {data['folder_image_constructed_url']}")
    else:
        logging.debug(f"API key 'jacket_thumb_url' not found or is null for {data.get('id')}")
    '''

    # --- Screenshots (no change from provided code) ---
    data['screenshot_urls'] = []
    gallery_list = webRequest.get('gallery')
    logging.debug(f"[R18 Scraper] Raw Gallery data received: {gallery_list}")
    if gallery_list and isinstance(gallery_list, list):
        valid_images = []
        for item in gallery_list:
            if isinstance(item, dict): img_url = item.get('image_full')
            if isinstance(img_url, str) and img_url: valid_images.append(img_url)
            else: logging.warning(f"[R18 Scraper] Item in gallery is not a dictionary: {item}")
        if valid_images:
            data['screenshot_urls'] = valid_images
            logging.info(f"[R18 Scraper] Found {len(data['screenshot_urls'])} valid screenshot URLs from gallery list.")
            logging.debug(f"[R18 Scraper] Screenshots: {data['screenshot_urls']}")
        else: logging.warning(f"[R18 Scraper] 'gallery' list found for {data.get('id')} but contained no valid 'image_full' URLs after processing.")
    elif gallery_list is not None: logging.warning(f"[R18 Scraper] Expected 'gallery' to be a list, but got type {type(gallery_list)} for {data.get('id')}. Value: {gallery_list}")
    else: logging.warning(f"[R18 Scraper] No 'gallery' key found in API response for {data.get('id')}.")

    # --- Default values (no change) ---
    data.setdefault('rating', None); data.setdefault('votes', None); data.setdefault('mpaa', None); data.setdefault('tagline', None)
    # Ensure 'set' defaults to the potentially updated series value
    data.setdefault('set', data.get('series'))
    data.setdefault('download_all', False)
    data.setdefault('poster_manual_url', None); data.setdefault('folder_manual_url', None)

    logging.debug(f"Finished scraping R18.Dev data for ID: {data.get('id')}")
    return data

# --- Direct Execution Block for Testing ---
# ... (Keep the testing block as is) ...
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    logging.info("Running r18dev_scraper.py directly for testing with DEBUG logging...")
    test_ids = ["EBOD-969", "SSIS-001", "MIDE-750", "JUQ-137", "DASS-603", "NonExistentID-123"]
    for test_id in test_ids:
        print(f"\n--- Testing ID: {test_id} ---")
        found_url = get_r18dev_url_from_id(test_id)
        if found_url:
            print(f"Found URL: {found_url}")
            print("Attempting to scrape data...")
            scraped_data = scrape_r18dev(found_url)
            if scraped_data:
                print("Scraping successful:")
                print(f"  ID: {scraped_data.get('id')}")
                print(f"  Cover URL: {scraped_data.get('cover_url')}")
                print(f"  Folder URL (jacket_thumb): {scraped_data.get('folder_image_constructed_url')}")
                print(f"  Screenshots: {scraped_data.get('screenshot_urls')}") # Check this output
            else: print("Scraping failed for the found URL.")
        else: print("Could not find URL for this ID.")
        print("-" * 30)
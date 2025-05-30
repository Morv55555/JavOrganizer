# In r18devja_scraper.py
# This scraper is designed to prioritize JAPANESE language fields from the R18.Dev API.

import requests
import logging
import html

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- User Agent ---
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'

# --- URL Finder Function (Renamed, logic identical) ---
def get_r18devja_url_from_id(id_str):
    """Finds the R18.Dev combined API URL based on the DVD ID."""
    logging.debug(f"Attempting to find R18.Dev JA URL for ID: '{id_str}'")
    if not id_str:
        logging.warning("Received empty ID string.")
        return None
    search_id = id_str
    # The search URL itself doesn't change based on language preference
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
            logging.info(f"Found R18.Dev JA content_id '{content_id}' for ID '{id_str}'. Combined URL: {combined_url}")
        else:
            logging.warning(f"No content_id found for ID '{id_str}' at {search_url}. Response: {data}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during R18.Dev JA URL search for '{id_str}': {e}")
    except ValueError as e: # Changed from json.JSONDecodeError for broader compatibility
        logging.error(f"Error decoding JSON response for '{id_str}': {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during R18.Dev JA URL search for '{id_str}': {e}")
    return combined_url

# --- Data Scraper Function (Renamed and Modified for JA Only) ---
def scrape_r18devja(url):
    """
    Scrapes data from the R18.Dev combined API URL, prioritizing JAPANESE fields.
    """
    logging.debug(f"Attempting to scrape R18.Dev JA data from URL: {url}")
    if not url or '/combined=' not in url:
        logging.error(f"Invalid R18.Dev JA combined URL provided: {url}")
        return None

    try:
        logging.debug(f"Performing GET on URL: {url}")
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=25)
        response.raise_for_status()
        webRequest = response.json()
        logging.info(f"Successfully scraped R18.Dev JA data for URL: {url}")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error during R18.Dev JA data scrape for '{url}': {e}")
        return None
    except ValueError as e: # Changed from json.JSONDecodeError
        logging.error(f"Error decoding JSON response for '{url}': {e}")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during R18.Dev JA data scrape for '{url}': {e}")
        return None

    # --- Helper Function for Processing ---
    def process_ja_field(value):
        if value is None:
            return None
        processed = html.unescape(str(value)).strip()
        return processed if processed else None # Return None if empty after processing

    # --- Extract data ---
    data = {}
    # --- Basic Info (No change) ---
    data['source'] = 'r18devja' # Set source to indicate Japanese preference
    data['url'] = url
    data['content_id'] = webRequest.get('content_id')
    data['id'] = webRequest.get('dvd_id')

    # --- >>> Title Logic (JA Only) <<< ---
    title_ja = process_ja_field(webRequest.get('title_ja'))
    data['title'] = title_ja # Use JA title for the main 'title' field
    data['title_raw'] = title_ja # Raw is also the JA title
    data['originaltitle'] = title_ja # Original title is explicitly the JA title
    logging.debug(f"  Using Japanese title: '{data['title']}'")

    # --- >>> Description Logic (JA Only - Assuming comment_ja exists) <<< ---
    # Note: API might not always provide comment_ja, field could be None
    description_ja = process_ja_field(webRequest.get('comment_ja'))
    data['description'] = description_ja
    if description_ja:
        logging.debug(f"  Using Japanese description (comment_ja). Length: {len(description_ja)}")
    else:
        logging.debug("  Japanese description (comment_ja) not found or empty.")


    # --- Dates (No change) ---
    release_date_str = webRequest.get('release_date', '').split(' ')[0]
    data['release_date'] = release_date_str if release_date_str else None
    data['release_year'] = release_date_str.split('-')[0] if release_date_str and '-' in release_date_str else None

    # --- Runtime (No change) ---
    data['runtime'] = str(webRequest.get('runtime_mins')) if webRequest.get('runtime_mins') is not None else None

    # --- >>> Director Logic (JA - Kanji Only) <<< ---
    data['director'] = None
    directors = webRequest.get('directors')
    if directors and isinstance(directors, list) and len(directors) > 0:
        director_info = directors[0]
        if isinstance(director_info, dict):
            # Prioritize Kanji name
            director_kanji = process_ja_field(director_info.get('name_kanji'))
            if director_kanji:
                data['director'] = director_kanji
                logging.debug(f"  Using Japanese director (kanji): '{data['director']}'")
            else:
                logging.debug("  Japanese director name (kanji) not found or empty.")
        else:
            logging.warning(f"  Director item is not a dictionary: {director_info}")

    # --- >>> Maker Logic (JA Only) <<< ---
    maker_ja = process_ja_field(webRequest.get('maker_name_ja'))
    data['maker'] = maker_ja
    if maker_ja:
        logging.debug(f"  Using Japanese maker: '{data['maker']}'")
    else:
        logging.debug("  Japanese maker name (maker_name_ja) not found or empty.")

    # --- >>> Label Logic (JA Only) <<< ---
    label_ja = process_ja_field(webRequest.get('label_name_ja'))
    data['label'] = label_ja
    if label_ja:
        logging.debug(f"  Using Japanese label: '{data['label']}'")
    else:
        logging.debug("  Japanese label name (label_name_ja) not found or empty.")

    # --- >>> Series Logic (JA Only) <<< ---
    series_ja = process_ja_field(webRequest.get('series_name_ja'))
    data['series'] = series_ja
    if series_ja:
        logging.debug(f"  Using Japanese series: '{data['series']}'")
    else:
        logging.debug("  Japanese series name (series_name_ja) not found or empty.")


    # --- >>> Actresses Logic (JA - Kanji Only) <<< ---
    # Note: name_kanji might not always be present for actresses in the API
    data['actresses'] = []
    actresses_list_from_api = webRequest.get('actresses') # Renamed for clarity
    if actresses_list_from_api and isinstance(actresses_list_from_api, list):
        logging.debug(f"Processing {len(actresses_list_from_api)} potential actresses found.")
        for actor_data in actresses_list_from_api: # Iterate through each item in the list
            if isinstance(actor_data, dict):
                # Prioritize Kanji name
                actor_kanji_name = process_ja_field(actor_data.get('name_kanji'))
                if actor_kanji_name: # Check if a valid Kanji name was processed
                    data['actresses'].append({'name': actor_kanji_name})
                    logging.debug(f"  Added Japanese actress (kanji): '{actor_kanji_name}'")
                else:
                    # Optionally log if Romaji was present but Kanji wasn't, or just that Kanji was missing
                    actor_romaji_name_for_log = actor_data.get('name_romaji')
                    logging.debug(f"  Skipping actress - Japanese name (kanji) not found/empty. Romaji was: '{actor_romaji_name_for_log}' for data: {actor_data.get('id')}")
            else:
                 logging.warning(f"  Skipping item in actresses list because it's not a dictionary: {actor_data}")
        logging.info(f"Finished processing actresses. Added {len(data['actresses'])} with Japanese (Kanji) names.")
    elif actresses_list_from_api is not None:
        logging.warning(f"Expected 'actresses' to be a list, but got type {type(actresses_list_from_api)}. Value: {actresses_list_from_api}")
    else:
        logging.debug("No 'actresses' key found in API response or it was null.")


    # --- >>> Genres Logic (JA Only) <<< ---
    data['genres'] = []
    categories = webRequest.get('categories')

    if categories and isinstance(categories, list):
        logging.debug(f"Processing {len(categories)} categories found for JA names.")
        for category in categories:
            final_genre_ja = None
            if isinstance(category, dict):
                # Only use Japanese Name
                name_ja = process_ja_field(category.get('name_ja'))
                if name_ja:
                    final_genre_ja = name_ja
                    logging.debug(f"  Using Japanese genre: '{final_genre_ja}'")

                # Add to list if valid Japanese genre was found
                if final_genre_ja:
                    data['genres'].append(final_genre_ja)
                else:
                    logging.debug(f"  Skipping category item - no valid Japanese name found: {category}")
            else:
                logging.warning(f"  Skipping item in categories list because it's not a dictionary: {category}")
        logging.info(f"Finished processing categories. Found {len(data['genres'])} Japanese genres: {data['genres']}")
    elif categories is not None:
        logging.warning(f"Expected 'categories' to be a list, but got type {type(categories)}. Value: {categories}")
    else:
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
    # --- Screenshots (No change needed - URLs are language-agnostic) ---
    data['screenshot_urls'] = []
    gallery_list = webRequest.get('gallery')
    logging.debug(f"[R18 JA Scraper] Raw Gallery data received: {gallery_list}")
    if gallery_list and isinstance(gallery_list, list):
        valid_images = []
        for item in gallery_list:
            if isinstance(item, dict):
                img_url = item.get('image_full')
                if isinstance(img_url, str) and img_url:
                    valid_images.append(img_url)
            # Log skipped items if needed
            # else: logging.warning(f"[R18 JA Scraper] Item in gallery is not a dictionary: {item}")
        if valid_images:
            data['screenshot_urls'] = valid_images
            logging.info(f"[R18 JA Scraper] Found {len(data['screenshot_urls'])} valid screenshot URLs from gallery list.")
            logging.debug(f"[R18 JA Scraper] Screenshots: {data['screenshot_urls']}")
        else:
            logging.warning(f"[R18 JA Scraper] 'gallery' list found for {data.get('id')} but contained no valid 'image_full' URLs after processing.")
    elif gallery_list is not None:
        logging.warning(f"[R18 JA Scraper] Expected 'gallery' to be a list, but got type {type(gallery_list)} for {data.get('id')}. Value: {gallery_list}")
    else:
        logging.warning(f"[R18 JA Scraper] No 'gallery' key found in API response for {data.get('id')}.")

    # --- Default values (No change) ---
    data.setdefault('rating', None)
    data.setdefault('votes', None)
    data.setdefault('mpaa', None)
    data.setdefault('tagline', None)
    # Ensure 'set' defaults to the potentially Japanese series value
    data.setdefault('set', data.get('series'))
    # --- Default values (no change) ---
    data.setdefault('download_all', False)
    data.setdefault('poster_manual_url', None)
    data.setdefault('folder_manual_url', None)

    logging.debug(f"Finished scraping R18.Dev JA data for ID: {data.get('id')}")
    return data

# --- Direct Execution Block for Testing (Updated) ---
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG) # Set root logger level
    logging.info("Running r18devja_scraper.py directly for testing with DEBUG logging...")

    # Test IDs - Use IDs known to have JA fields
    test_ids = ["EBOD-969", "SSIS-001", "MIDE-750", "JUQ-137", "IPX-408", "NonExistentID-123"]

    for test_id in test_ids:
        print(f"\n--- Testing ID: {test_id} ---")
        found_url = get_r18devja_url_from_id(test_id) # Use the renamed function
        if found_url:
            print(f"Found URL: {found_url}")
            print("Attempting to scrape data (JA Preference)...")
            scraped_data = scrape_r18devja(found_url) # Use the renamed function
            if scraped_data:
                print("Scraping successful:")
                print(f"  ID: {scraped_data.get('id')}")
                print(f"  Source: {scraped_data.get('source')}") # Should be r18devja
                print(f"  Title (JA): {scraped_data.get('title')}")
                print(f"  Original Title (JA): {scraped_data.get('originaltitle')}")
                print(f"  Description (JA - length): {len(scraped_data.get('description', '')) if scraped_data.get('description') else 'None'}")
                print(f"  Director (Kanji): {scraped_data.get('director')}")
                print(f"  Maker (JA): {scraped_data.get('maker')}")
                print(f"  Label (JA): {scraped_data.get('label')}")
                print(f"  Series (JA): {scraped_data.get('series')}")
                print(f"  Actresses (Kanji): {scraped_data.get('actresses')}")
                print(f"  Genres (JA): {scraped_data.get('genres')}")
                print(f"  Cover URL: {scraped_data.get('cover_url')}")
                print(f"  Folder URL (jacket_thumb): {scraped_data.get('folder_image_constructed_url')}")
                print(f"  Screenshots count: {len(scraped_data.get('screenshot_urls', []))}")
            else:
                print("Scraping failed for the found URL.")
        else:
            print("Could not find URL for this ID.")
        print("-" * 30)
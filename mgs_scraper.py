# START OF FILE mgs_scraper.py

import requests
from bs4 import BeautifulSoup, Tag, NavigableString # Keep BS4 import
import re
import logging
import html
from urllib.parse import urljoin
from datetime import datetime
import time

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- User Agent & Headers ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.mgstage.com/'
}

# --- Helper to create session ---
def _create_mgs_session():
    session = requests.Session()
    session.cookies.set('adc', '1', domain='www.mgstage.com')
    session.headers.update(HEADERS)
    return session

# --- URL Finder Function (Assumed Working) ---
def get_mgs_url_from_id(id_str):
    # ... (Keep the working version from previous steps) ...
    logging.debug(f"--- Starting MGS URL search for ID: '{id_str}' ---")
    if not id_str: logging.warning("Received empty ID string."); return None
    session = _create_mgs_session(); search_id_normalized = id_str.strip().upper()
    search_url = f"https://www.mgstage.com/search/cSearch.php?search_word={requests.utils.quote(search_id_normalized)}"
    target_url = None; max_retries = 1; retry_delay = 3
    for attempt in range(max_retries + 1):
        try:
            logging.info(f"Attempt {attempt + 1}: MGS search for '{search_id_normalized}' URL: {search_url}")
            response = session.get(search_url, timeout=25)
            logging.debug(f"MGS Search status: {response.status_code}")
            if response.status_code == 403: logging.error(f"403 Forbidden on search. Headers: {response.request.headers}"); continue
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            possible_links = soup.find_all('a', href=re.compile(r'/product/product_detail/([A-Z0-9_-]+)/?', re.IGNORECASE))
            if not possible_links: logging.warning(f"No product links found for '{search_id_normalized}' (attempt {attempt + 1})."); continue
            logging.debug(f"Found {len(possible_links)} potential product links.")
            matched_result_found = False
            for link_tag in possible_links:
                href = link_tag.get('href');
                if not href: continue # Added check if href is None
                id_match = re.search(r'/product/product_detail/([A-Z0-9_-]+)/?', href, re.IGNORECASE)
                extracted_id_from_link = id_match.group(1).strip().upper() if id_match else None
                if extracted_id_from_link and extracted_id_from_link == search_id_normalized:
                     target_url = urljoin("https://www.mgstage.com", href)
                     if not target_url.endswith('/'): target_url += '/'
                     logging.info(f"MGS Exact Match Found (via link href)! ID: '{extracted_id_from_link}', URL: {target_url}")
                     matched_result_found = True; break
            if matched_result_found: break
            else: logging.warning(f"No exact match in links on attempt {attempt + 1} for '{search_id_normalized}'.")
        except requests.exceptions.RequestException as e:
            logging.error(f"MGS search attempt {attempt + 1} failed: {e}")
            if attempt < max_retries: time.sleep(retry_delay)
            else: logging.error("Max retries reached for MGS search."); return None
        except Exception as e: logging.error(f"Unexpected error during MGS search attempt {attempt + 1}: {e}", exc_info=True); return None
    if not target_url: logging.warning(f"No exact URL match ultimately found for ID '{search_id_normalized}' on MGS.")
    logging.debug(f"--- Finished MGS URL search for ID: '{id_str}'. Result: {target_url} ---")
    return target_url


# --- Data Scraper Function (REVISED v8 - Corrected Syntax Error) ---
def scrape_mgs(url):
    logging.debug(f"Attempting to scrape MGS data from URL: {url}")
    if not url: logging.error("Invalid MGS URL provided."); return None

    session = _create_mgs_session()

    try:
        logging.info(f"Performing GET on MGS URL: {url}")
        response = session.get(url, timeout=25)
        logging.debug(f"MGS Detail page status: {response.status_code}")
        if response.status_code == 403: logging.error(f"403 Forbidden on Detail Page. Headers: {response.request.headers}")
        response.raise_for_status()
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
    except requests.exceptions.RequestException as e: logging.error(f"Error during MGS data scrape for '{url}': {e}"); return None
    except Exception as e: logging.error(f"An unexpected error occurred during MGS data scrape for '{url}': {e}", exc_info=True); return None

    data = {}
    data['source'] = 'mgs'
    data['url'] = url

    # --- Title ---
    title_tag = soup.find('title')
    scraped_title = html.unescape(title_tag.text.strip()) if title_tag else None
    
    if scraped_title:
        logging.debug(f"Title before cleanup: '{scraped_title}'")

        # Rule 1: Original cleanup for " - MGステージアダルト動画..."
        # Using a non-capturing group (?:...) for the content after the known suffix start.
        pattern_mgstage_suffix = r'\s*-\s*MGステージアダルト動画(?:.*)?$' # Made (?:.*) optional with ?
        original_title_before_mgstage = scraped_title
        scraped_title = re.sub(pattern_mgstage_suffix, '', scraped_title, flags=re.IGNORECASE).strip()
        if scraped_title != original_title_before_mgstage:
            logging.debug(f"Title after MGStage suffix cleanup: '{scraped_title}'")

        # Rule 2: New cleanup for "エロ動画・アダルトビデオ -MGS動画＜プレステージ グループ＞..."
        # This pattern is designed to be more flexible with internal spacing and hyphen types.
        # Part 1: "エロ動画・アダルトビデオ"
        # Separator: optional whitespace, a hyphen character, optional whitespace
        # Part 2: "MGS動画＜プレステージ グループ＞"
        # The entire match, along with anything after it, will be removed.
        
        # Literal parts of the phrase:
        prestige_part1 = re.escape("エロ動画・アダルトビデオ")
        prestige_part2 = re.escape("MGS動画＜プレステージ グループ＞") # Note: space in "プレステージ グループ" is handled by re.escape

        # Flexible hyphen pattern: matches common hyphens U+002D, U+2010, U+FF0D
        hyphen_pattern = r"[-‐－]" 

        # Combine into the full pattern for the prestige key phrase:
        # It looks for part1, then flexible_separator, then part2.
        flexible_prestige_key_phrase_pattern = rf"{prestige_part1}\s*{hyphen_pattern}\s*{prestige_part2}"
        
        # Pattern to remove the key phrase and anything that follows it,
        # preceded by optional whitespace.
        pattern_prestige_suffix_full = r'\s*(?:' + flexible_prestige_key_phrase_pattern + r')(?:.*)?$' # Made (?:.*) optional with ?

        original_title_before_prestige = scraped_title
        scraped_title = re.sub(pattern_prestige_suffix_full, '', scraped_title, flags=re.IGNORECASE).strip()
        if scraped_title != original_title_before_prestige:
            logging.debug(f"Title after Prestige suffix cleanup: '{scraped_title}'")
        
    data['title'] = scraped_title
    data['title_raw'] = scraped_title 
    data['originaltitle'] = scraped_title
    logging.debug(f"Final Title: {data['title']}")

    # --- Description ---
    data['description'] = None
    desc_container = soup.select_one('div.detail_txt.introduction')
    if desc_container: desc_p = desc_container.find('p')
    else: desc_p = soup.select_one('p.txt.introduction')
    if desc_p:
        for br in desc_p.find_all("br"): br.replace_with("\n")
        data['description'] = html.unescape(desc_p.get_text(strip=True))
        logging.debug("Found description.")
    else: logging.warning("Could not find description using known selectors.")

    if data.get('description'):
        logging.debug(f"Description found (Length Before Cleanup: {len(data['description'])}). Applying cleanup...")
        original_desc = data['description']
        cleaned_desc = original_desc

        # --- Define Regex Patterns for Cleanup ---
        # Pattern 1: Match the specific example structure: 【期間限定！...】 including content inside.
        # This is tricky as content varies. Let's try matching the start/end markers.
        # Match from 【期間限定！ to 】 possibly spanning multiple lines.
        pattern_timed_sale = r'(?s)\s*【期間限定！.*?】\s*'

        # Pattern 2: Match similar promotional blocks that might use different brackets or keywords.
        # Example: Blocks starting with ※注意事項 or similar markers. (Needs refinement based on examples)
        pattern_notes = r'(?s)\s*※(注意事項|Notes):?.*?$' # Matches from ※注意事項 to end of string (or adjust end condition)

        # Pattern 3: General pattern for text within full-width brackets 【】 or half-width [] that seems promotional
        # Look for keywords like ポイント (point), プレゼント (present), 期間 (period), 限定 (limited), 円分 (yen equivalent)
        pattern_bracket_promo = r'(?s)\s*(?:【|\[)[^【】\[\]]*(?:ポイント|プレゼント|期間|限定|円分)[^【】\[\]]*?(?:】|\])\s*'


        # --- Apply Patterns Sequentially ---
        logging.debug("Applying pattern_timed_sale...")
        cleaned_desc = re.sub(pattern_timed_sale, ' ', cleaned_desc, flags=re.IGNORECASE)

        logging.debug("Applying pattern_notes...")
        cleaned_desc = re.sub(pattern_notes, ' ', cleaned_desc, flags=re.IGNORECASE | re.MULTILINE)

        logging.debug("Applying pattern_bracket_promo...")
        cleaned_desc = re.sub(pattern_bracket_promo, ' ', cleaned_desc, flags=re.IGNORECASE)


        # --- Final Whitespace Cleanup ---
        cleaned_desc = re.sub(r'\s+', ' ', cleaned_desc).strip()

        if cleaned_desc != original_desc:
            logging.info(f"Cleaned description. Original Length: {len(original_desc)}, New Length: {len(cleaned_desc)}")
            if not cleaned_desc: # Check if cleanup made it empty
                    logging.warning("Description became empty after cleanup.")
                    data['description'] = None
            else:
                    data['description'] = cleaned_desc
        else:
            logging.debug("Description cleanup patterns did not alter the text.")
            # Ensure original value (which might be None) is kept if no changes
            data['description'] = original_desc

    elif not data.get('description'):
        logging.warning("Could not find description using known selectors.")

    # --- Detail Extraction (TH -> TD Sibling Method) ---
    def _find_td_via_th(soup_obj, header_text_pattern):
        try:
            th_tag = soup_obj.find('th', string=re.compile(r'^\s*' + re.escape(header_text_pattern) + r'\s*[:：]?\s*$', re.IGNORECASE))
            if th_tag:
                td_tag = th_tag.find_next_sibling('td')
                if td_tag: return td_tag
                else: logging.debug(f"Found TH '{header_text_pattern}' but no next TD sibling.")
            else: logging.debug(f"Could not find TH matching pattern '{header_text_pattern}'.")
        except Exception as e: logging.error(f"Error finding TD for TH '{header_text_pattern}': {e}")
        return None
    def get_detail_text_from_td(td_tag): return html.unescape(td_tag.get_text(strip=True)) if td_tag else None
    def get_first_link_text_from_td(td_tag):
        if td_tag: link = td_tag.find('a'); return html.unescape(link.text.strip()) if link and link.text and link.text.strip() else None
        return None
    def get_all_link_texts_from_td(td_tag):
        if td_tag: links = td_tag.find_all('a'); return [html.unescape(a.text.strip()) for a in links if a.text and a.text.strip()]
        return []

    id_td = _find_td_via_th(soup, '品番'); data['id'] = get_detail_text_from_td(id_td)
    release_td = _find_td_via_th(soup, '配信開始日'); release_str = get_detail_text_from_td(release_td)
    runtime_td = _find_td_via_th(soup, '収録時間'); runtime_str = get_detail_text_from_td(runtime_td)
    maker_td = _find_td_via_th(soup, 'メーカー'); data['maker'] = get_first_link_text_from_td(maker_td)
    label_td = _find_td_via_th(soup, 'レーベル'); data['label'] = get_first_link_text_from_td(label_td)
    series_td = _find_td_via_th(soup, 'シリーズ'); data['series'] = get_first_link_text_from_td(series_td)
    director_td = _find_td_via_th(soup, '監督'); data['director'] = get_detail_text_from_td(director_td)
    if not data['director']: data['director'] = get_first_link_text_from_td(director_td)
    genre_td = _find_td_via_th(soup, 'ジャンル'); data['genres'] = get_all_link_texts_from_td(genre_td)
    actress_td = _find_td_via_th(soup, '出演'); actress_names = get_all_link_texts_from_td(actress_td)
    data['actresses'] = [{'name': name} for name in actress_names]

    # --- Parse Date and Runtime ---
    data['release_date'] = None; data['release_year'] = None
    if release_str:
        try: dt_obj = datetime.strptime(release_str, '%Y/%m/%d'); data['release_date'] = dt_obj.strftime('%Y-%m-%d'); data['release_year'] = dt_obj.strftime('%Y')
        except Exception as e: logging.warning(f"Date parse error for '{release_str}': {e}")
    data['runtime'] = None
    if runtime_str:
        runtime_match = re.search(r'(\d+)', runtime_str)
        if runtime_match: data['runtime'] = runtime_match.group(1)

    logging.debug(f"ID (TH->TD): {data['id']}") # Check this!

    # --- Rating ---
    data['rating'] = None; data['votes'] = None
    review_p = soup.select_one('p.review')
    if review_p:
        try:
            rate_span = review_p.select_one('span.rate')
            votes_span = review_p.select_one('span.review_num')
            rating_val = None
            votes_val = None

            if rate_span:
                try:
                    rating_val = float(rate_span.text.strip()) * 2
                except ValueError:
                    logging.warning(f"Could not parse rating value '{rate_span.text}'")
                    # Keep rating_val as None

            if votes_span:
                votes_match = re.search(r'\((\d+)\)', votes_span.text)
                if votes_match:
                    try:
                        votes_val = int(votes_match.group(1))
                    except ValueError:
                        logging.warning(f"Could not parse votes value '{votes_span.text}'")
                        # Keep votes_val as None

            data['rating'] = round(rating_val, 2) if rating_val is not None else None
            data['votes'] = votes_val
            logging.debug(f"Rating: {data['rating']}, Votes: {data['votes']}")

        except Exception as e:
            logging.warning(f"Error processing review block for rating/votes: {e}")
    else:
        logging.debug("Rating/Review block 'p.review' not found.")


    # --- Images ---
    data['cover_url'] = None # Initialize before try block
    data['screenshot_urls'] = [] # Initialize before try block
    try: # Add try block around image selectors
        cover_link = soup.select_one('a.link_magnify[href*=".jpg"]')
        if cover_link:
            data['cover_url'] = cover_link.get('href')
        else:
            img_tag = soup.select_one('img#package_image[src*=".jpg"]')
            if img_tag:
                data['cover_url'] = img_tag.get('src')
            else:
                logging.warning("Could not find cover image link or img tag.")
        logging.debug(f"Cover URL: {data['cover_url']}")

        screenshot_tags = soup.select('a.sample_image[href*=".jpg"]')
        data['screenshot_urls'] = [a.get('href') for a in screenshot_tags if a.get('href')]
        logging.debug(f"Screenshots: {len(data['screenshot_urls'])} found")

    except Exception as e: # Catch potential errors during selection/attribute access
        logging.error(f"Error extracting images: {e}")
    # --- End of try block for images ---


    data['folder_image_constructed_url'] = None

    # --- Final Defaults ---
    data.setdefault('content_id', data.get('id'))
    data.setdefault('mpaa', None); data.setdefault('tagline', None); data.setdefault('set', data.get('series'))
    data.setdefault('folder_name', None); data.setdefault('download_all', False); data.setdefault('poster_manual_url', None); data.setdefault('folder_manual_url', None)

    # --- Final Check ---
    if not data.get('id'):
        logging.error(f"Failed to scrape required ID field from {url} using TH -> TD Sibling method. Aborting scrape.")
        html_snippet = html_content[:3000]
        logging.debug(f"--- HTML Snippet for Failed ID Scrape ({url}) ---\n{html_snippet}\n--- End HTML Snippet ---")
        return None

    logging.info(f"Scraping complete for MGS URL: {url}. ID: {data.get('id')}, Title: {data.get('title')}")
    return data

# --- Direct Execution Block for Testing ---
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    logging.info("Running mgs_scraper.py directly for testing with DEBUG logging...")
    test_ids = ["SIRO-5000", "SQTE-500", "AKB-051", "ABF-217", "NonExistentID-999", "SSIS-001", "MIDE-900"]
    for test_id in test_ids:
        print(f"\n--- Testing MGS ID: {test_id} ---")
        found_url = get_mgs_url_from_id(test_id)
        if found_url:
            print(f"Found URL: {found_url}")
            print("Attempting to scrape data...")
            scraped_data = scrape_mgs(found_url)
            if scraped_data:
                print("Scraping successful:")
                print(f"  ID: {scraped_data.get('id')}")
                print(f"  Title: {scraped_data.get('title')}")
                print(f"  Maker: {scraped_data.get('maker')}")
                # ... (rest of print statements) ...
                print(f"  Label: {scraped_data.get('label')}")
                print(f"  Series: {scraped_data.get('series')}")
                print(f"  Director: {scraped_data.get('director')}")
                print(f"  Release Date: {scraped_data.get('release_date')}")
                print(f"  Runtime: {scraped_data.get('runtime')}")
                print(f"  Rating: {scraped_data.get('rating')}, Votes: {scraped_data.get('votes')}")
                print(f"  Genres: {scraped_data.get('genres')}")
                print(f"  Actresses: {scraped_data.get('actresses')}")
                print(f"  Cover URL: {scraped_data.get('cover_url')}")
                print(f"  Screenshots: {len(scraped_data.get('screenshot_urls', []))} found")
            else: print("Scraping failed for the found URL.")
        else: print("Could not find URL for this ID.")
        print("-" * 30)

# END OF FILE mgs_scraper.py
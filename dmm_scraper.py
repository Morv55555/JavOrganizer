# START OF FILE dmm_scraper.py

import requests
from bs4 import BeautifulSoup
import re
import logging
import json
from urllib.parse import urljoin
from lxml import html

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] %(message)s')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# --- Helper Functions ---
def get_content_id(url):
    """Extracts the content ID (cid) from a DMM URL."""
    match = re.search(r'cid=([^/]+)', url)
    return match.group(1) if match else None

def get_id(content_id):
    """Converts a DMM content ID (e.g., abc00123 or h_1814nmsl00003) into a standard ID format (e.g., ABC-123 or NMSL-003)."""
    if not content_id: return None
    logging.debug(f"Original content_id for get_id: {content_id}")

    # Clean prefixes commonly found in CIDs but not part of the standard ID
    # Added ^h_\d+_? to handle cases like h_1814nmsl00003
    prefixes_to_clean = [
        'h_086', 'h_113', 'h_068', 'h_729', # Specific known h_ prefixes
        r'^h_\d+_?',                     # Generic h_ followed by digits (and optional _)
        r'^\d+'                         # Generic leading digits (e.g., 118abf118)
    ]
    cleaned_cid_for_id = content_id.lower() # Work with lowercase
    prefix_removed = False
    for prefix_pattern in prefixes_to_clean:
        original_len = len(cleaned_cid_for_id)
        # Use re.sub for pattern matching and removal
        if prefix_pattern == r'^\d+':
             # Remove leading digits only if they are followed by letters
             cleaned_cid_for_id = re.sub(r'^\d+(?=[a-zA-Z])', '', cleaned_cid_for_id)
        else:
             # Use re.match to ensure pattern is at the beginning
             match = re.match(prefix_pattern, cleaned_cid_for_id)
             if match:
                 cleaned_cid_for_id = cleaned_cid_for_id[len(match.group(0)):] # Remove the matched part

        if len(cleaned_cid_for_id) < original_len:
            logging.debug(f"Removed prefix matching '{prefix_pattern}'. Remaining: '{cleaned_cid_for_id}'")
            prefix_removed = True
            break # Stop after removing one prefix pattern

    if not prefix_removed:
        logging.debug("No prefixes removed.")

    logging.debug(f"CID after prefix cleaning: '{cleaned_cid_for_id}'")

    # Standard ID formatting logic
    # Now apply to the potentially cleaned CID (e.g., nmsl00003)
    match = re.match(r'([a-z_]+)(\d+)(.*)$', cleaned_cid_for_id, re.IGNORECASE) # Allow underscore in prefix
    if match:
        prefix_id = match.group(1).upper().replace('_', '') # Remove underscores from prefix part
        number_id = match.group(2).lstrip('0')
        # Ensure at least 3 digits if it's purely numeric, otherwise keep original length after stripping zeros
        if number_id.isdigit() or not number_id: # Handle empty string case from lstrip
             number_id = number_id.zfill(3)
        suffix_id = match.group(3).upper()
        formatted_id = f"{prefix_id}-{number_id}{suffix_id}"
        logging.debug(f"Formatted ID: {formatted_id}")
        return formatted_id
    else:
        # Fallback if standard pattern doesn't match after cleaning
        fallback_id = cleaned_cid_for_id.upper()
        logging.debug(f"Standard pattern didn\'t match, using fallback: {fallback_id}")
        return fallback_id


# --- URL Finder Function ---
def get_dmm_url_from_id(id_str):
    """
    Searches DMM using an ID string, finds relevant links, and returns the best match URL.
    Logs detailed info to console only.
    """
    logging.debug(f"--- Starting URL search for ID: '{id_str}' ---")
    if not id_str: logging.warning("Received empty ID string."); return None

    headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
    session = requests.Session()
    session.cookies.set('age_check_done', '1', domain='dmm.co.jp')

    content_id = None; target_digital_cid = None; target_dvd_cid = None
    id_pattern = re.compile(r'([a-zA-Z0-9]+)-?(\d+)([a-zA-Z]*)', re.IGNORECASE)
    match = id_pattern.match(id_str)
    if match:
        prefix = match.group(1).lower(); number_part = match.group(2); suffix = match.group(3).lower()
        padded_number = number_part.zfill(5)
        target_digital_cid = f"{prefix}{padded_number}{suffix}"
        target_dvd_cid = f"{prefix}{number_part}{suffix}" # Use original number part for DVD target
        logging.info(f"Parsed ID '{id_str}' -> Prefix: '{prefix}', Num: '{number_part}', Suffix: '{suffix}'")
        logging.info(f"Generated Target CIDs -> Digital (Padded): '{target_digital_cid}', DVD (Unpadded): '{target_dvd_cid}'")
    else:
        raw_id = id_str.lower().replace('-', '')
        target_digital_cid = raw_id
        target_dvd_cid = raw_id # Fallback uses same ID for both targets
        logging.warning(f"Could not parse ID '{id_str}' using standard pattern. Using fallback targets: '{raw_id}'")

    if not target_digital_cid: logging.error("Failed to generate a target digital CID."); return None

    search_term = target_digital_cid # Primary search uses padded ID
    search_url = f"https://www.dmm.co.jp/search/=/searchstr={requests.utils.quote(search_term)}/"
    logging.info(f"Attempting primary search with term: '{search_term}' URL: {search_url}")
    response = None
    try:
        response = session.get(search_url, headers=headers, timeout=25)
        logging.info(f"Primary search request completed. Status: {response.status_code}, URL: {response.url}")
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Primary search failed for '{search_term}': {e}")
        if target_dvd_cid and target_dvd_cid != target_digital_cid:
            search_term = target_dvd_cid # Fallback search uses unpadded ID
            search_url = f"https://www.dmm.co.jp/search/=/searchstr={requests.utils.quote(search_term)}/"
            logging.info(f"Attempting fallback search with term: '{search_term}' URL: {search_url}")
            try:
                response = session.get(search_url, headers=headers, timeout=25)
                logging.info(f"Fallback search request completed. Status: {response.status_code}, URL: {response.url}")
                response.raise_for_status()
            except requests.exceptions.RequestException as e_fallback:
                logging.error(f"Fallback search also failed for '{search_term}': {e_fallback}"); return None
        else:
            logging.debug("No different DVD CID for fallback, or primary search failed with no fallback needed.")
            return None

    if not response: logging.error("Search response object is unexpectedly None after attempts."); return None

    logging.debug(f"Search successful (using term '{search_term}'). Parsing HTML.")
    soup = BeautifulSoup(response.text, 'html.parser')
    all_links = soup.find_all('a', href=True)
    logging.info(f"Found {len(all_links)} total links.")

    relevant_links = []
    for link in all_links:
        href = link['href']
        if re.search(r'/(?:digital/videoa|mono/dvd)/-/detail/', href) and 'cid=' in href:
            relevant_links.append(href)

    logging.info(f"Filtered to {len(relevant_links)} potential detail links.")
    if not relevant_links: logging.warning(f"No relevant detail links found for '{search_term}'."); return None

    logging.debug(f"Filtering {len(relevant_links)} links by comparing extracted CID to target CIDs...")
    digital_matches = []; dvd_matches = []

    for i, href in enumerate(relevant_links):
        cid_match = re.search(r'[/?&]cid=([^/?&]+)', href)
        if not cid_match: continue

        extracted_cid_raw = cid_match.group(1).lower()
        logging.debug(f"  Link {i}: '{href}' - Extracted CID Raw='{extracted_cid_raw}'")

        match_found_for_this_link = False

        if '/digital/videoa/-/detail/' in href:
            # 1. Try direct match with the PADDED target
            if extracted_cid_raw == target_digital_cid:
                digital_matches.append(href)
                logging.info(f"--> Digital Match (Direct): Raw Extracted '{extracted_cid_raw}' == Target Digital '{target_digital_cid}'. Link: {href}")
                match_found_for_this_link = True
            else:
                # 2. If direct failed, try cleaning the extracted raw CID and compare again with PADDED target
                cleaned_extracted_cid = re.sub(r'^\w*?(?=[a-zA-Z]+\d)', '', extracted_cid_raw)
                if not cleaned_extracted_cid: cleaned_extracted_cid = extracted_cid_raw # Safety
                logging.debug(f"    Digital direct failed. Cleaned: '{cleaned_extracted_cid}'. Comparing vs Target Digital '{target_digital_cid}'...")
                if cleaned_extracted_cid == target_digital_cid:
                    digital_matches.append(href)
                    logging.info(f"--> Digital Match (Cleaned): Cleaned Extracted '{cleaned_extracted_cid}' == Target Digital '{target_digital_cid}'. Link: {href}")
                    match_found_for_this_link = True

        elif '/mono/dvd/-/detail/' in href:
            # 1. Try direct match with the UNPADDED target
            if target_dvd_cid and extracted_cid_raw == target_dvd_cid:
                 dvd_matches.append(href)
                 logging.info(f"--> DVD Match (Direct): Raw Extracted '{extracted_cid_raw}' == Target DVD '{target_dvd_cid}'. Link: {href}")
                 match_found_for_this_link = True
            else:
                 # 2. If direct failed, CLEAN the extracted raw CID and compare with UNPADDED target
                 cleaned_extracted_cid = re.sub(r'^\w*?(?=[a-zA-Z]+\d)', '', extracted_cid_raw)
                 if not cleaned_extracted_cid: cleaned_extracted_cid = extracted_cid_raw # Safety
                 logging.debug(f"    DVD direct failed. Cleaned: '{cleaned_extracted_cid}'. Comparing vs Target DVD '{target_dvd_cid}'...")
                 if target_dvd_cid and cleaned_extracted_cid == target_dvd_cid:
                     dvd_matches.append(href)
                     logging.info(f"--> DVD Match (Cleaned): Cleaned Extracted '{cleaned_extracted_cid}' == Target DVD '{target_dvd_cid}'. Link: {href}")
                     match_found_for_this_link = True

        if not match_found_for_this_link:
             logging.debug(f"    No match for this link.")

    selected_url = None
    if digital_matches:
        selected_url = digital_matches[0]
        logging.info(f"Selected final URL (Digital Priority): {selected_url}")
    elif dvd_matches:
        selected_url = dvd_matches[0]
        logging.info(f"Selected final URL (DVD Fallback): {selected_url}")
    else:
        logging.warning(f"Found relevant links, but no CID match for Target Digital '{target_digital_cid}' or Target DVD '{target_dvd_cid}' after direct and cleaned comparisons.")

    if selected_url and not selected_url.startswith('http'):
        base_url = "https://www.dmm.co.jp/"
        selected_url = urljoin(base_url, selected_url)
        logging.debug(f"Made URL absolute: {selected_url}")

    logging.debug(f"--- Finished URL search for ID: '{id_str}'. Result: {selected_url} ---")
    return selected_url


# --- Scraper Function ---
def scrape_dmm(url, scrape_actress=False): # scrape_actress argument is not used, can be removed if desired
    """
    Scrapes details from a given DMM product page URL.
    Prioritizes AWS image URL for cover, falls back to page scraping.
    """
    PLACEHOLDERS = ['----', 'なし', 'None']

    headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
    session = requests.Session()
    session.cookies.set('age_check_done', '1', domain='dmm.co.jp')
    if '/en/' in url: session.cookies.set('ckcy', '2', domain='dmm.co.jp'); session.cookies.set('cklg', 'en', domain='dmm.co.jp')

    try:
        response = session.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        logging.info(f"Successfully fetched DMM page: {url} (Status: {response.status_code})")
    except requests.exceptions.RequestException as e: logging.error(f"Failed to retrieve DMM page '{url}': {e}"); return None

    html_content = response.text
    soup = BeautifulSoup(html_content, 'lxml')
    tree = html.fromstring(html_content)
    data = {}
    data['source'] = 'dmm_en' if '/en/' in url else 'dmm_jp'
    data['url'] = url
    data['content_id'] = get_content_id(url)
    data['id'] = get_id(data['content_id'])

    # --- Title ---
    title_tag = soup.select_one('h1#title')
    scraped_title = title_tag.text.strip() if title_tag else None
    if not scraped_title:
        title_element = tree.xpath('/html/body/div/main/div/div[2]/div/div[1]/h1/span/text()')
        if title_element:
            scraped_title = title_element[0].strip()

    data['title'] = scraped_title; data['title_raw'] = scraped_title; data['originaltitle'] = scraped_title
    logging.debug(f"Scraped Title: {data['title']}")

    # --- Description ---
    data['description'] = None # Reset before trying methods
    json_ld_script = soup.find('script', type='application/ld+json')
    if json_ld_script:
        try:
            # Basic cleaning first
            json_content = json_ld_script.string.replace('"', '"').replace('\n', ' ').replace('\\/', '/')
            json_data = json.loads(json_content)
            if isinstance(json_data, list): json_data = json_data[0] # Handle list wrapper
            if isinstance(json_data, dict): # Ensure it's a dict
                desc = json_data.get('description')
                if desc and isinstance(desc, str): # Check if key exists and is string
                    # Don't need replace('\', '') here if done before parsing
                    cleaned_desc = re.sub(r'\s+', ' ', desc).strip() # Consolidate whitespace
                    if cleaned_desc and cleaned_desc not in PLACEHOLDERS:
                         data['description'] = cleaned_desc
                         logging.debug("Scraped Description from JSON-LD")
                    else:
                         logging.debug("JSON-LD description empty or placeholder.")
            else:
                logging.debug("Parsed JSON-LD was not a dictionary.")
        except Exception as e:
            logging.warning(f"Error processing JSON-LD: {e}")

    # Fallback if JSON-LD failed or didn't yield description
    if not data.get('description'):
        # Original fallback logic using the combined selector
        desc_div = soup.find('div', class_=re.compile(r'product-info__description|\bmg-b20\b.*\blh4\b'))
        if desc_div:
            try: # Add try-except around div processing
                for element_to_remove in desc_div.find_all(['span', 'a'], class_=re.compile(r'link-showmore|readmore', re.IGNORECASE)):
                    element_to_remove.decompose()
                desc_text = desc_div.get_text(separator=' ', strip=True)
                # Check if valid text found
                if desc_text and desc_text not in PLACEHOLDERS:
                    cleaned_desc = re.sub(r'\s+', ' ', desc_text).strip() # Consolidate whitespace
                    if cleaned_desc: # Check again after cleanup
                        data['description'] = cleaned_desc
                        logging.debug("Scraped Description from fallback div")
                    else:
                         logging.debug("Fallback div description empty after cleanup.")
                else:
                    logging.debug("Found placeholder or empty text in description div.")
            except Exception as e:
                logging.warning(f"Error processing fallback description div: {e}")
        # else: # Log if div not found (optional, can be noisy)
        #     logging.debug("Fallback description div not found.")


    # --- >>> POST-SCRAPING REGEX CLEANUP (APPLIED AFTER EITHER METHOD) <<< ---
    if data.get('description'):
        original_desc_length = len(data['description'])
        logging.debug(f"Applying post-scraping regex cleanup to description (Length: {original_desc_length})...")
        current_desc = data['description'] # Work on a temporary variable

        # Pattern 1: Remove "詳しくはこちら をご覧ください。" and surrounding whitespace
        pattern1 = r'\s*?詳しくはこちら\s*?をご覧ください。\s*?'
        current_desc = re.sub(pattern1, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 1 ('詳しくはこちら...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc) # Update length for next check

        # Pattern 2: Remove "特典・セット商品情報..." sale blocks
        pattern2 = r'(?s)(\s*?(?:特典|セット商品|キャンペーン|セール|SALE)情報.*?キャンペーン終了後.*?あらかじめご了承ください。\s*)'
        current_desc = re.sub(pattern2, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 2 ('特典・セット商品情報...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc)

        # Pattern 3: Remove "「コンビニ受取」対象商品です。" and surrounding whitespace
        pattern3 = r'\s*?「コンビニ受取」\s*?対象商品です。\s*?'
        current_desc = re.sub(pattern3, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 3 ('コンビニ受取...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc)

        # --- ADDED NEW PATTERNS ---
        # Pattern 4: Remove "特典・ 特典付き商品・セット商品について"
        pattern4 = r'\s*?特典・\s*?特典付き商品・セット商品について\s*?'
        current_desc = re.sub(pattern4, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 4 ('特典・ 特典付き商品...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc)

        # Pattern 5: Remove "※この作品は成人に制服のコスプレをさせています。"
        pattern5 = r'\s*?※この作品は成人に制服のコスプレをさせています。\s*?'
        current_desc = re.sub(pattern5, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 5 ('※この作品は成人に制服...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc)

        # Pattern 6: Remove "※この作品の出演者は全て19歳以上の成人です。"
        pattern6 = r'\s*?※この作品の出演者は全て19歳以上の成人です。\s*?'
        current_desc = re.sub(pattern6, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 6 ('※この作品の出演者は全て19歳...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc)

        # Pattern 7: Remove "（All performers in this work are adults over the age of 19.）"
        # Need to escape parentheses
        pattern7 = r'\s*?（All performers in this work are adults over the age of 19\.）\s*?' # Corrected: Use full-width parens （ and ）
        current_desc = re.sub(pattern7, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 7 ('（All performers...）'). New length: {len(current_desc)}") # Updated log message slightly
            original_desc_length = len(current_desc)

        # Pattern 8: Remove "「予約商品の価格保証」対象商品です。"
        pattern8 = r'\s*?「予約商品の価格保証」対象商品です。\s*?'
        current_desc = re.sub(pattern8, ' ', current_desc, flags=re.IGNORECASE)
        if len(current_desc) < original_desc_length:
            logging.debug(f"  Removed pattern 8 ('「予約商品の価格保証」...'). New length: {len(current_desc)}")
            original_desc_length = len(current_desc)
        # --- END ADDED NEW PATTERNS ---


        # --- Final Cleanup: Consolidate whitespace and trim again ---
        current_desc = re.sub(r'\s+', ' ', current_desc).strip()
        logging.debug(f"  Description after final whitespace cleanup (Length: {len(current_desc)}).")

        # Check if cleanup resulted in empty string or placeholder
        if not current_desc or current_desc in PLACEHOLDERS:
            logging.warning("Description became empty or a placeholder after regex cleanup. Setting to None.")
            data['description'] = None
        else:
            data['description'] = current_desc # Assign cleaned value back
    # --- >>> END REGEX CLEANUP <<< ---


    # --- Final check and warning if still no description ---
    if not data.get('description'):
        logging.warning(f"Could not find valid description using any method for {url}.")

    # --- Release Date & Runtime ---
    data['release_date'] = None; data['runtime'] = None
    info_table = soup.find('table', class_=re.compile(r'product-info-table|\bmg-b20\b'))
    if info_table:
        rows = info_table.find_all('tr')
        for row in rows:
             cells = row.find_all('td');
             if len(cells) == 2:
                 key_element = cells[0]; value_cell = cells[1]; key = key_element.get_text(strip=True); value_text = value_cell.get_text(strip=True)
                 if re.search(r'発売日|配信開始日|Release Date', key, re.IGNORECASE):
                     date_match = re.search(r'(\d{4}/\d{2}/\d{2})', value_cell.get_text())
                     if date_match: date_str = date_match.group(1); data['release_date'] = date_str.replace('/', '-') if date_str not in PLACEHOLDERS else None
                 elif re.search(r' 収録時間|Duration', key, re.IGNORECASE):
                     runtime_match = re.search(r'(\d+)\s*(分|min)', value_text)
                     if runtime_match: runtime_val = runtime_match.group(1); data['runtime'] = runtime_val if runtime_val not in PLACEHOLDERS else None
    # Fallback searches if not found in table
    if not data['release_date']:
        date_match = re.search(r'(\d{4}/\d{2}/\d{2})', html_content)
        if date_match: date_str = date_match.group(1); data['release_date'] = date_str.replace('/', '-') if date_str not in PLACEHOLDERS else None
    if not data['runtime']:
        runtime_match = re.search(r'(\d{2,3})\s*(分|minutes)', html_content)
        if runtime_match: runtime_val = runtime_match.group(1); data['runtime'] = runtime_val if runtime_val not in PLACEHOLDERS else None
    data['release_year'] = data['release_date'].split('-')[0] if data.get('release_date') else None


    # --- Director, Maker, Label, Series, Actresses, Genres ---
    data['director'] = None; data['maker'] = None; data['label'] = None; data['series'] = None; data['actresses'] = []; data['genres'] = []
    if info_table:
        logging.debug("Processing info table for Director, Maker, Label, Series, Performers, Genres...")
        rows = info_table.find_all('tr')
        for row_idx, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) == 2:
                key_cell = cells[0]; value_cell = cells[1]
                key = key_cell.get_text(strip=True)
                logging.debug(f"Table Row {row_idx}: Key='{key}'")

                value_links = value_cell.find_all('a', href=True) # Keep for actresses/genres

                # Helper function (used for Maker, Label)
                def get_first_link_text_or_cell_text(cell):
                    link = cell.find('a')
                    text = link.text.strip() if link else cell.get_text(strip=True)
                    return text if text not in PLACEHOLDERS else None

                # Director, Maker, Label (logic remains the same)
                if re.search(r'監督|Director', key, re.IGNORECASE):
                    director_text = value_cell.get_text(strip=True); data['director'] = director_text if director_text not in PLACEHOLDERS else None; logging.debug(f"  Director: {data['director']}")
                elif re.search(r'メーカー|Maker', key, re.IGNORECASE): data['maker'] = get_first_link_text_or_cell_text(value_cell); logging.debug(f"  Maker: {data['maker']}")
                elif re.search(r'レーベル|Label', key, re.IGNORECASE): data['label'] = get_first_link_text_or_cell_text(value_cell); logging.debug(f"  Label: {data['label']}")
                elif re.search(r'シリーズ|Series', key, re.IGNORECASE): data['series'] = get_first_link_text_or_cell_text(value_cell); logging.debug(f"  Series: {data['series']}")

                # Actresses, Genres (logic remains the same)
                elif re.search(r'出演者|Performers|女優', key, re.IGNORECASE):
                    actress_list = [];
                    for link in value_links:
                        href = link.get('href')
                        if (
                            ('/article=actress/' in href or 
                            '/list/=/article=actress/' in href or
                            '/digital/videoa/-/list/?actress=' in href)):
                            name = link.text.strip()
                            if name and name not in PLACEHOLDERS and name not in ['▼すべて表示する', 'See All']: actress_list.append({'name': name})
                    if actress_list: data['actresses'] = actress_list
                    else:
                         plain_text = value_cell.get_text(strip=True)
                         if plain_text and plain_text not in PLACEHOLDERS:
                             potential_names = [n.strip() for n in re.split(r'\s*[/／]\s*|\s+', plain_text) if n.strip() and n.strip() not in PLACEHOLDERS]
                             if potential_names: data['actresses'] = [{'name': n} for n in potential_names]
                elif re.search(r'ジャンル|Genre', key, re.IGNORECASE):
                     genre_list = [];
                     for link in value_links:
                         name = link.text.strip()
                         if name and name not in PLACEHOLDERS: genre_list.append(name)
                     if genre_list: data['genres'] = genre_list
            # else: logging.debug(f"Table Row {row_idx}: Skipping, not 2 cells.") # Uncomment if needed
    else:
        logging.warning("Info table not found. Using XPath fallbacks for Director, Maker, etc.")
        # Fallback for Director
        director_element = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[1]/div[2]/table/tbody/tr[6]/td/span/div/a/text()')
        if director_element:
            data['director'] = director_element[0].strip()

        # Fallback for Maker/Studio
        maker_element = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[1]/div[2]/table/tbody/tr[8]/td/span/a/text()')
        if maker_element:
            data['maker'] = maker_element[0].strip()

        # Fallback for Label
        label_element = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[1]/div[2]/table/tbody/tr[9]/td/span/a/text()')
        if label_element:
            data['label'] = label_element[0].strip()

        # Fallback for Series
        series_element = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[1]/div[2]/table/tbody/tr[7]/td/span/a/text()')
        if series_element:
            data['series'] = series_element[0].strip()

        # Fallback for Genre
        genre_elements = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[1]/div[2]/table/tbody/tr[10]/td/span/div//a/text()')
        if genre_elements:
            data['genres'] = [genre.strip() for genre in genre_elements]

        # Fallback for Actress
        actress_elements = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[1]/div[2]/table/tbody/tr[5]/td/span/div//a/text()')
        if actress_elements:
            data['actresses'] = [{'name': actress.strip()} for actress in actress_elements]


    # --- AJAX Fallback for Actresses ---
    if not data.get('actresses'):
        logging.debug("Actresses not found in table, checking for AJAX pattern...")
        ajax_match = re.search(r'"(/digital/video[a-z]?/-/detail/ajax-performer/=/cid=\w+/)"', html_content)
        if not ajax_match: ajax_match = re.search(r'"(/digital/videoa/-/detail/ajax-performer/=/data=[^\"]*)"', html_content)
        if ajax_match:
            ajax_url_path = ajax_match.group(1)
            if ajax_url_path.startswith('/'):
                ajax_url = urljoin(data['url'], ajax_url_path)
                logging.info(f"Found potential AJAX URL for performers. Attempting AJAX GET: {ajax_url}")
                try:
                    ajax_response = session.get(ajax_url, headers=headers, timeout=15)
                    ajax_response.raise_for_status()
                    ajax_soup = BeautifulSoup(ajax_response.text, 'html.parser')
                    ajax_actress_links = ajax_soup.find_all('a', href=re.compile(r'/article=actress/id=\d+'))
                    ajax_actress_list = []
                    for link in ajax_actress_links:
                        name = link.text.strip()
                        if name and name not in PLACEHOLDERS and name not in ['▼すべて表示する', 'See All']: ajax_actress_list.append({'name': name})
                    if ajax_actress_list: data['actresses'] = ajax_actress_list; logging.info(f"AJAX success: Found {len(ajax_actress_list)} actresses: {data['actresses']}")
                    else: logging.warning(f"AJAX request successful, but no valid actress links found in response from {ajax_url}.")
                except requests.exceptions.RequestException as e: logging.warning(f"AJAX request for performers failed: {e}")
                except Exception as e_parse: logging.warning(f"Error parsing AJAX response for performers: {e_parse}")
            else: logging.debug(f"Extracted AJAX path doesn't seem relative: {ajax_url_path}")
        else: logging.debug("AJAX performer pattern not found in HTML.")
    elif data.get('actresses'): logging.debug("Actresses already found in table, skipping AJAX check.")

    # --- Cover Image (New logic: Prioritize AWS, Fallback to page scraping) ---
    data['cover_url'] = None
    aws_cover_url = None
    if data.get('content_id'):
        cid = data['content_id']
        # Construct the primary AWS URL
        # Assuming 'digital/video' path - adjust if needed for mono/dvd etc.
        aws_path_segment = 'digital/video'
        aws_cover_url = f"https://awsimgsrc.dmm.co.jp/pics_dig/{aws_path_segment}/{cid}/{cid}pl.jpg"
        logging.debug(f"Attempting primary Cover URL (AWS): {aws_cover_url}")

        # Validate AWS URL (Status Code Only)
        try:
            # Use HEAD request for efficiency, short timeout
            head_response = session.head(aws_cover_url, timeout=5, allow_redirects=True, headers=headers)
            logging.debug(f"HEAD request for AWS cover image status: {head_response.status_code}")

            if head_response.status_code == 200:
                data['cover_url'] = aws_cover_url
                logging.info(f"Successfully validated AWS Cover URL: {aws_cover_url}")
            else:
                logging.warning(f"AWS Cover URL check failed ({head_response.status_code}). Will attempt page scraping fallback.")
                aws_cover_url = None # Ensure it's None if check failed

        except requests.exceptions.Timeout:
            logging.warning(f"Timeout checking AWS Cover URL: {aws_cover_url}. Will attempt page scraping fallback.")
            aws_cover_url = None
        except requests.exceptions.RequestException as e_head:
            logging.warning(f"Network error checking AWS Cover URL {aws_cover_url}: {e_head}. Will attempt page scraping fallback.")
            aws_cover_url = None
    else:
        logging.warning("Cannot attempt AWS cover URL: content_id is missing.")

    # --- Fallback Cover Image Search (Only if AWS method failed or wasn't possible) ---
    if not data.get('cover_url'):
        logging.debug("AWS Cover URL failed or not available, attempting page scraping fallback...")
        cover_img_tag = soup.find('img', id='package-src')
        if cover_img_tag and cover_img_tag.get('src'):
            fallback_url = re.sub(r'p[s-]\.jpg$', 'pl.jpg', cover_img_tag['src'])
            data['cover_url'] = fallback_url
            logging.debug(f"Found Fallback Cover URL using #package-src (forced 'pl'): {data['cover_url']}")

        if not data.get('cover_url'):
            cover_match = re.search(r'(https://pics\.dmm\.co\.jp/(?:mono/(?:movie/adult|dvd)|digital/(?:video[a-z]?|amateur))/[^/]+/[^/]+?)(?:p[ls]|p-)?\.jpg', html_content, re.IGNORECASE)
            if cover_match:
                fallback_url = f"{cover_match.group(1)}pl.jpg"
                data['cover_url'] = fallback_url
                logging.debug(f"Found Fallback Cover URL using broad regex (forced 'pl'): {data['cover_url']}")
            else:
                cover_img_fallback = soup.find('img', src=re.compile(r'pics\.dmm\.co\.jp/.*/.*p[a-zA-Z-]?\.jpg'))
                if cover_img_fallback and cover_img_fallback.get('src'):
                    fallback_url = re.sub(r'p[s-]\.jpg$', 'pl.jpg', cover_img_fallback['src'])
                    data['cover_url'] = fallback_url
                    logging.debug(f"Found Fallback Cover URL using broad fallback img search (forced 'pl'): {data['cover_url']}")

    # Final check if cover is still missing
    if not data.get('cover_url'):
        logging.warning(f"Could not find Cover URL for {url} using AWS or any fallback method.")


    # --- Screenshots ---
    data['screenshot_urls'] = []
    screenshot_elements = tree.xpath('//*[@id="sample-image-block"]/div/div//li/a/img/@src')
    if screenshot_elements:
        data['screenshot_urls'] = [url.strip().replace('ps.jpg', 'pl.jpg') for url in screenshot_elements]

    if not data['screenshot_urls']:
        screenshot_elements = tree.xpath('/html/body/div[1]/main/div/div[2]/div/div[2]/div[1]/div[3]/div/div[2]//a/@href')
        if screenshot_elements:
            data['screenshot_urls'] = [url.strip() for url in screenshot_elements]
            
    if not data['screenshot_urls']:
        i = 1
        while True:
            screenshot_element = tree.xpath(f'//*[@id="package-image{i}"]/img/@src')
            if screenshot_element:
                data['screenshot_urls'].append(screenshot_element[0].strip().replace('ps.jpg', 'pl.jpg'))
                i += 1
            else:
                break

    # Remove duplicates and sort
    data['screenshot_urls'] = sorted(list(set(data['screenshot_urls'])))
    logging.debug(f"Found {len(data['screenshot_urls'])} unique Screenshot URLs.")


    # --- Add Default/Placeholder Fields ---
    data.setdefault('rating', None); data.setdefault('votes', None); data.setdefault('mpaa', None); data.setdefault('tagline', None)
    data.setdefault('set', data.get('series') if data.get('series') else None) # Important: Set 'set' from 'series'
    data.setdefault('folder_name', None)
    data.setdefault('download_all', False)
    data.setdefault('poster_manual_url', None)
    data.setdefault('folder_manual_url', None)
    # Removed folder_image_constructed_url as it's redundant now

    logging.info(f"Scraping complete for {url}. Title: '{data.get('title')}', ID: {data.get('id')}")
    return data


# --- Direct Execution Block ---
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG) # Set root logger to DEBUG
    logging.info("Running dmm_scraper.py directly for testing with DEBUG logging...")
    test_ids_to_check = ["ABF-118", "ABF-218", "DASS-603", "MKCK-510", "GARA-009", "ADN-588"]

    with open("output.txt", "w", encoding="utf-8") as f:
        for test_id in test_ids_to_check:
            f.write(f"\n" + "="*10 + f" Testing ID: {test_id} " + "="*10 + "\n")
            url = get_dmm_url_from_id(test_id)
            if url:
                f.write(f"RESULT: Found URL: {url}\n")
                f.write(f"\n>>> Testing Scraper with URL: {url} <<\n")
                scraped_data = scrape_dmm(url)
                if scraped_data:
                    f.write("RESULT: Scraped data:\n")
                    f.write(json.dumps(scraped_data, indent=2, ensure_ascii=False) + "\n")
                else:
                    f.write(f"RESULT: Could not scrape data for URL: {url}\n")
            else:
                f.write(f"RESULT: Could not find URL for {test_id}.\n")
            f.write("-" * (20 + len(test_id) + 20) + "\n")

# END OF FILE dmm_scraper.py

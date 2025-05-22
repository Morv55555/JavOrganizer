import os
import shutil
import requests
import streamlit as st
from xml.etree import ElementTree as ET
from xml.dom import minidom
import time
import glob
import re
from urllib.parse import urljoin
import json
import logging
import subprocess
import sys 
import concurrent.futures
import threading

# --- Import Settings ---
try:
    import settings as app_settings
    SETTINGS_LOADED = True
except ImportError:
    st.error("FATAL ERROR: settings.py not found. Please create it with default values.")
    SETTINGS_LOADED = False
    # Provide dummy defaults
    class DummySettings:
        DEFAULT_DOWNLOAD_ALL_INITIAL_STATE = False
        DEFAULT_ENABLED_SCRAPERS = ["Dmm"]
        DEFAULT_FIELD_PRIORITIES = {'title': ['DMM']}
        ORDERED_PRIORITY_FIELDS_WITH_LABELS = [('title', 'Title')]
        PRIORITY_FIELDS_ORDERED = ['title']
        DEFAULT_INPUT_DIRECTORY = ""
        DEFAULT_OUTPUT_DIRECTORY = ""
        DEFAULT_TRANSLATOR_SERVICE = "None"
        DEFAULT_TARGET_LANGUAGE = ""
        DEFAULT_API_KEY = ""
        DEFAULT_TRANSLATE_TITLE = False
        DEFAULT_TRANSLATE_DESCRIPTION = False
        DEFAULT_KEEP_ORIGINAL_DESCRIPTION = False
        DEFAULT_GENRE_BLACKLIST = []
    app_settings = DummySettings()

# --- Define Settings File Path ---
USER_SETTINGS_FILE = "user_settings.json"

# --- Imports for Scraper and URL Finder ---
SCRAPER_REGISTRY = {}
# Define availability flags
DMM_AVAILABLE = False
R18DEV_AVAILABLE = False
R18DEVJA_AVAILABLE = False
MGS_AVAILABLE = False
JAVLIBRARY_AVAILABLE = False 

# Try importing each scraper
try:
    from dmm_scraper import get_dmm_url_from_id, scrape_dmm
    SCRAPER_REGISTRY["Dmm"] = {'find': get_dmm_url_from_id, 'scrape': scrape_dmm}
    DMM_AVAILABLE = True
except ImportError: print("INFO: dmm_scraper.py not found or failed to import.")

try:
    from r18dev_scraper import get_r18dev_url_from_id, scrape_r18dev
    SCRAPER_REGISTRY["r18dev"] = {'find': get_r18dev_url_from_id, 'scrape': scrape_r18dev}
    R18DEV_AVAILABLE = True
except ImportError: print("INFO: r18dev_scraper.py not found or failed to import.")

try:
    from r18devja_scraper import get_r18devja_url_from_id, scrape_r18devja
    SCRAPER_REGISTRY["r18dev Ja"] = {'find': get_r18devja_url_from_id, 'scrape': scrape_r18devja}
    R18DEVJA_AVAILABLE = True # Optional flag
except ImportError:
    print("INFO: r18devja_scraper.py not found or failed to import.")

try:
    from mgs_scraper import get_mgs_url_from_id, scrape_mgs
    SCRAPER_REGISTRY["Mgs"] = {'find': get_mgs_url_from_id, 'scrape': scrape_mgs}
    MGS_AVAILABLE = True
except ImportError: print("INFO: mgs_scraper.py not found or failed to import.")

try:
    from javlibrary_scraper import get_javlibrary_url_from_id, scrape_javlibrary
    SCRAPER_REGISTRY["Javlibrary"] = {'find': get_javlibrary_url_from_id, 'scrape': scrape_javlibrary}
    JAVLIBRARY_AVAILABLE = True
except ImportError:
    print("INFO: javlibrary_scraper.py not found or failed to import.")

AVAILABLE_SCRAPER_NAMES = list(SCRAPER_REGISTRY.keys())

# --- Function to Load Settings ---
def load_settings():
    # Define defaults based on settings.py
    defaults = {
        "default_download_all_initial_state": app_settings.DEFAULT_DOWNLOAD_ALL_INITIAL_STATE,
        "enabled_scrapers": app_settings.DEFAULT_ENABLED_SCRAPERS,
        "field_priorities": app_settings.DEFAULT_FIELD_PRIORITIES, 
        "input_dir": app_settings.DEFAULT_INPUT_DIRECTORY,
        "output_dir": app_settings.DEFAULT_OUTPUT_DIRECTORY,
        # Translation Defaults
        "translator_service": app_settings.DEFAULT_TRANSLATOR_SERVICE,
        "target_language": app_settings.DEFAULT_TARGET_LANGUAGE,
        "api_key": app_settings.DEFAULT_API_KEY,
        "translate_title": app_settings.DEFAULT_TRANSLATE_TITLE,
        "translate_description": app_settings.DEFAULT_TRANSLATE_DESCRIPTION,
        "keep_original_description": app_settings.DEFAULT_KEEP_ORIGINAL_DESCRIPTION,
        "genre_blacklist": app_settings.DEFAULT_GENRE_BLACKLIST,
    }
    # Filter defaults based on availability right away
    defaults["enabled_scrapers"] = [s for s in defaults["enabled_scrapers"] if s in AVAILABLE_SCRAPER_NAMES]
    validated_default_priorities = {}
    for field, prio_list in defaults["field_priorities"].items():
         # Make sure the field itself is valid according to the (updated) ordered list
        if field in app_settings.PRIORITY_FIELDS_ORDERED:
             validated_default_priorities[field] = [s for s in prio_list if s in AVAILABLE_SCRAPER_NAMES]
    defaults["field_priorities"] = validated_default_priorities

    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)

            # Merge defaults with user settings, applying validation/filtering
            loaded_settings = {**defaults}

            # Load simple boolean/string settings
            loaded_settings["default_download_all_initial_state"] = user_settings.get("default_download_all_initial_state", defaults["default_download_all_initial_state"])
            loaded_settings["input_dir"] = user_settings.get("input_dir", defaults["input_dir"])
            loaded_settings["output_dir"] = user_settings.get("output_dir", defaults["output_dir"])

            # Load and validate enabled scrapers
            user_enabled = user_settings.get("enabled_scrapers", [])
            loaded_settings["enabled_scrapers"] = [s for s in user_enabled if s in AVAILABLE_SCRAPER_NAMES]

            # Load and validate priorities
            user_priorities = user_settings.get("field_priorities", {})
            validated_priorities = {}
            # Use the updated ordered list from settings.py
            for field_key in app_settings.PRIORITY_FIELDS_ORDERED:
                default_prio = defaults["field_priorities"].get(field_key, [])
                user_prio = user_priorities.get(field_key, default_prio)
                validated_priorities[field_key] = [s for s in user_prio if s in AVAILABLE_SCRAPER_NAMES]
            loaded_settings["field_priorities"] = validated_priorities

            # Load Translation Settings
            loaded_settings["translator_service"] = user_settings.get("translator_service", defaults["translator_service"])
            loaded_settings["target_language"] = user_settings.get("target_language", defaults["target_language"])
            loaded_settings["api_key"] = user_settings.get("api_key", defaults["api_key"])
            loaded_settings["translate_title"] = user_settings.get("translate_title", defaults["translate_title"])
            loaded_settings["translate_description"] = user_settings.get("translate_description", defaults["translate_description"])
            loaded_settings["keep_original_description"] = user_settings.get("keep_original_description", defaults["keep_original_description"])

            raw_blacklist = user_settings.get("genre_blacklist", defaults["genre_blacklist"])
            if isinstance(raw_blacklist, list):
                loaded_settings["genre_blacklist"] = [
                    str(g).strip().lower() for g in raw_blacklist if isinstance(g, str) and str(g).strip()
                ]
            else: # If not a list, use default
                loaded_settings["genre_blacklist"] = defaults["genre_blacklist"]


            print(f"Loaded and validated settings from {USER_SETTINGS_FILE}")
            return loaded_settings
        except (json.JSONDecodeError, TypeError, KeyError, AttributeError) as e:
            print(f"Error loading or validating {USER_SETTINGS_FILE}: {e}. Using default settings.")
            return defaults
    else:
        print(f"{USER_SETTINGS_FILE} not found. Using default settings.")
        return defaults

# --- Function to Save Settings ---
def save_settings_to_file():
    settings_to_save = {
        "enabled_scrapers": st.session_state.enabled_scrapers,
        "field_priorities": st.session_state.field_priorities,
        "input_dir": st.session_state.input_dir,
        "output_dir": st.session_state.output_dir,
        # Translation Settings
        "translator_service": st.session_state.translator_service,
        "target_language": st.session_state.target_language,
        "api_key": st.session_state.api_key,
        "translate_title": st.session_state.translate_title,
        "translate_description": st.session_state.translate_description,
        "keep_original_description": st.session_state.keep_original_description,
        "genre_blacklist": st.session_state.get("genre_blacklist", []),
    }
    try:
        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
        st.toast("Settings saved successfully!", icon="💾")
    except Exception as e:
        st.error(f"Error saving settings to {USER_SETTINGS_FILE}: {e}")

# --- Function to Sync Settings from File/Defaults to Session State ---
def sync_settings_from_file_to_state():
    """
    Loads settings from user_settings.json (or defaults) and updates
    the corresponding st.session_state variables.
    Called on page load for Crawler and Settings pages.
    """
    print("Syncing settings from file/defaults to session state...")
    loaded_settings = load_settings() 

    # Update session state keys that come from settings
    st.session_state.enabled_scrapers = loaded_settings["enabled_scrapers"]
    st.session_state.field_priorities = loaded_settings["field_priorities"]
    st.session_state.input_dir = loaded_settings["input_dir"]
    st.session_state.output_dir = loaded_settings["output_dir"]
    st.session_state.translator_service = loaded_settings["translator_service"]
    st.session_state.target_language = loaded_settings["target_language"]
    st.session_state.api_key = loaded_settings["api_key"]
    st.session_state.translate_title = loaded_settings["translate_title"]
    st.session_state.translate_description = loaded_settings["translate_description"]
    st.session_state.keep_original_description = loaded_settings["keep_original_description"]
    st.session_state.genre_blacklist = loaded_settings.get("genre_blacklist", [])

    print(f"  Synced input_dir: {st.session_state.input_dir}")
    print(f"  Synced output_dir: {st.session_state.output_dir}")
    print(f"  Synced enabled_scrapers: {st.session_state.enabled_scrapers}")
    print(f"  Synced genre_blacklist: {st.session_state.get('genre_blacklist')}")

# --- Page Config & Styles ---
st.set_page_config(page_title="Movie Scraper & Organizer", layout="wide", initial_sidebar_state="collapsed")
# --- End Config & Styles ---

# --- Session State Initialization & Settings Loading ---
if 'initialized' not in st.session_state:
    loaded_settings = load_settings() 
    st.session_state.all_movie_data = {}
    st.session_state.current_movie_key = None
    st.session_state.movie_file_paths = []
    st.session_state.current_page = "Crawler"  
    st.session_state.crawler_view = "Editor"   

    # Load settings from file/defaults
    st.session_state.default_download_all_initial_state = loaded_settings.get("default_download_all_initial_state", False) 
    st.session_state.enabled_scrapers = loaded_settings.get("enabled_scrapers", []) 
    st.session_state.field_priorities = loaded_settings.get("field_priorities", {}) 
    st.session_state.input_dir = loaded_settings.get("input_dir", "") 
    st.session_state.output_dir = loaded_settings.get("output_dir", "") 
    
    # Translation settings (if you have them)
    st.session_state.translator_service = loaded_settings.get("translator_service", "None")
    st.session_state.target_language = loaded_settings.get("target_language", "") 
    st.session_state.api_key = loaded_settings.get("api_key", "") 
    st.session_state.translate_title = loaded_settings.get("translate_title", False) 
    st.session_state.translate_description = loaded_settings.get("translate_description", False) 
    st.session_state.keep_original_description = loaded_settings.get("keep_original_description", False) 

    # Javlibrary specific session state for credentials prompt
    st.session_state.javlibrary_user_agent = None
    st.session_state.javlibrary_cf_token = None
    st.session_state.show_javlibrary_prompt = False 
    st.session_state.javlibrary_creds_provided_this_session = False 

    # Other states you might have
    st.session_state.genre_blacklist = loaded_settings.get("genre_blacklist", [])
    st.session_state.last_crawl_was_recursive = False 

    # Initialize session state for re-scrape UI
    st.session_state.rescrape_scraper_select = AVAILABLE_SCRAPER_NAMES[0] if AVAILABLE_SCRAPER_NAMES else None
    st.session_state.rescrape_url_input = ""
    st.session_state.show_rescrape_section = False

    # Initialize selected_scraper if applicable
    if not st.session_state.enabled_scrapers: 
        st.session_state.selected_scraper = None
    elif "selected_scraper" not in st.session_state or st.session_state.selected_scraper not in st.session_state.enabled_scrapers: 
        st.session_state.selected_scraper = st.session_state.enabled_scrapers[0] if st.session_state.enabled_scrapers else None
    
    st.session_state.initialized = True
# --- End Session State ---

# --- Helper: Determine Auto Poster URL ---
def get_auto_poster_url(data):
    poster_url = data.get('cover_url');
    if poster_url: return poster_url
    screenshot_urls = data.get('screenshot_urls', [])
    first_screenshot_url = screenshot_urls[0] if screenshot_urls else None
    return first_screenshot_url
# ---

# --- Generate NFO Function ---
def generate_nfo(data, filename, download_all_flag):
    # download_all_flag is now the per-movie value passed from organize_all_callback
    movie = ET.Element('movie')
    # NFO Title field maps to the potentially translated 'title' from merged_data
    field_mapping = { 'title': 'title', 'originaltitle': 'originaltitle', 'id': 'id', 'premiered': 'release_date', 'year': 'release_year', 'director': 'director', 'studio': 'maker', 'label': 'label', 'series': 'series', 'rating': 'rating', 'votes': 'votes', 'plot': 'description', 'runtime': 'runtime', 'mpaa': 'mpaa', 'tagline': 'tagline', 'set': 'set'}

    for tag, key in field_mapping.items():
        value = data.get(key);
        if tag == 'set' and not value: value = data.get('series', '')
        if tag == 'rating' and isinstance(value, dict): value = value.get('Rating')
        if tag == 'votes' and isinstance(value, dict): value = value.get('Votes')
        elem = ET.SubElement(movie, tag); elem.text = str(value) if value is not None else ''

    # Removed references to folder_url or folder_image_constructed_url for NFO generation
    base_page_url = data.get('url', '') # Get the base URL for resolving relative paths
    fanart_thumbs_to_add = [] # Initialize list for ALL fanart thumbs

    # 1. Get the primary image URL (what was previously the poster)
    primary_image_url_to_use = data.get('poster_manual_url') or get_auto_poster_url(data)
    if primary_image_url_to_use:
        try:
            # Add the primary image URL as the FIRST item for fanart
            abs_primary_url = urljoin(base_page_url, primary_image_url_to_use)
            fanart_thumbs_to_add.insert(0, abs_primary_url) 
        except Exception as e:
            st.warning(f"Could not process primary image URL {primary_image_url_to_use} for NFO fanart: {e}")

    # 2. Add screenshots if flag is set
    if download_all_flag: # Use the flag passed into the function
        screenshot_urls = data.get('screenshot_urls', [])
        # Ensure primary image isn't duplicated in screenshots
        primary_abs_url_for_check = fanart_thumbs_to_add[0] if fanart_thumbs_to_add else None

        for ss_url in screenshot_urls:
            if ss_url: # Check if screenshot URL exists
                 try:
                     abs_ss_url = urljoin(base_page_url, ss_url)
                     # Avoid adding duplicates of primary or other screenshots
                     if abs_ss_url != primary_abs_url_for_check and abs_ss_url not in fanart_thumbs_to_add:
                          fanart_thumbs_to_add.append(abs_ss_url)
                 except Exception as e:
                     st.warning(f"Could not add screenshot thumb {ss_url} to NFO fanart: {e}")

    # 3. Create the <fanart> tag and add all collected <thumb> elements
    if fanart_thumbs_to_add:
        fanart = ET.SubElement(movie, 'fanart')
        # Use the collected list directly (primary image is already first)
        processed_urls = set() 
        final_thumb_list = []
        for thumb_url in fanart_thumbs_to_add:
            if thumb_url not in processed_urls:
                final_thumb_list.append(thumb_url)
                processed_urls.add(thumb_url)

        for thumb_url in final_thumb_list: 
            try:
                ET.SubElement(fanart, 'thumb').text = thumb_url
            except Exception as e:
                st.warning(f"Could not write fanart thumb {thumb_url} to NFO: {e}")
    for genre in data.get('genres', []):
        if genre: ET.SubElement(movie, 'genre').text = str(genre).strip()
    for actor in data.get('actresses', []):
        actor_name = actor.get('name', '');
        if actor_name:
            actor_tag = ET.SubElement(movie, 'actor'); ET.SubElement(actor_tag, 'name').text = str(actor_name).strip(); ET.SubElement(actor_tag, 'role').text = ''; ET.SubElement(actor_tag, 'thumb').text = ''
    content_id = data.get('content_id');
    uniqueid_type = data.get('source', 'unknown').split('_')[0]
    if content_id: ET.SubElement(movie, 'uniqueid', {'type': uniqueid_type, 'default': 'true'}).text = str(content_id)
    fileinfo = ET.SubElement(movie, 'fileinfo'); streamdetails = ET.SubElement(fileinfo, 'streamdetails'); video = ET.SubElement(streamdetails, 'video');
    for vtag in ['codec', 'aspect', 'width', 'height', 'durationinseconds', 'stereomode']: ET.SubElement(video, vtag).text = ''
    audio = ET.SubElement(streamdetails, 'audio');
    for atag in ['codec', 'language', 'channels']: ET.SubElement(audio, atag).text = ''
    subtitle = ET.SubElement(streamdetails, 'subtitle'); ET.SubElement(subtitle, 'language').text = ''
    try:
        xml_str = ET.tostring(movie, encoding='UTF-8', method='xml'); xml_declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'; pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  "); pretty_xml_str = pretty_xml_str.replace('<?xml version="1.0" ?>', '', 1).strip(); final_xml = xml_declaration + pretty_xml_str; os.makedirs(os.path.dirname(filename), exist_ok=True);
        with open(filename, 'w', encoding='UTF-8') as f: f.write(final_xml)
    except Exception as e: st.error(f"Error writing NFO file '{filename}': {e}"); raise IOError(f"Error writing NFO file '{filename}': {e}")
# --- End Generate NFO ---

# --- Helper Function: Sanitize ID for Scrapers ---
def sanitize_id_for_scraper(raw_id):
    """
    Cleans and formats an ID string (often from a filename) before sending it to scrapers.
    Attempts to convert various formats (e.g., abc00123, h_1814nmsl00003, 118abf118)
    into a more standard format (e.g., ABC-123, NMSL-003, ABF-118).
    """
    if not raw_id: return None
    logging.debug(f"[SANITIZE] Original raw_id: {raw_id}") # Using logging from original

    # Clean prefixes commonly found in CIDs but not part of the standard ID
    prefixes_to_clean = [
        'h_086', 'h_113', 'h_068', 'h_729', # Specific known h_ prefixes
        r'^h_\d+_?',                     # Generic h_ followed by digits (and optional _)
        r'^\d+'                         # Generic leading digits (e.g., 118abf118) - handled specially below
    ]
    cleaned_cid_for_id = raw_id.lower() 
    prefix_removed = False
    for prefix_pattern in prefixes_to_clean:
        original_len = len(cleaned_cid_for_id)
        # Special handling for leading digits: remove only if followed by letters
        if prefix_pattern == r'^\d+':
            cleaned_cid_for_id = re.sub(r'^\d+(?=[a-zA-Z])', '', cleaned_cid_for_id)
        else:
            # Use re.match for other prefixes to ensure they are at the beginning
            match = re.match(prefix_pattern, cleaned_cid_for_id)
            if match:
                # Remove the matched part
                cleaned_cid_for_id = cleaned_cid_for_id[len(match.group(0)):]

        if len(cleaned_cid_for_id) < original_len:
            logging.debug(f"[SANITIZE] Removed prefix matching '{prefix_pattern}'. Remaining: '{cleaned_cid_for_id}'")
            prefix_removed = True

    # if not prefix_removed:
    #     logging.debug("[SANITIZE] No prefixes removed based on defined patterns.")


    logging.debug(f"[SANITIZE] ID after prefix cleaning: '{cleaned_cid_for_id}'")

    # Standard ID formatting logic (e.g., ABC123 -> ABC-123)
    match = re.match(r'([a-z_]+)(\d+)(.*)$', cleaned_cid_for_id, re.IGNORECASE) # Allow underscore in text part
    if match:
        prefix_id = match.group(1).upper().replace('_', '') # Remove underscores from text part
        number_id_str = match.group(2)
        suffix_id = match.group(3).upper() # Get suffix

        try:
            if len(number_id_str) > 5:
                 number_part = number_id_str 
            else:
                 number_val = int(number_id_str)
                 number_part = str(number_val).zfill(3) 
        except ValueError:
             # If conversion fails (shouldn't with \d+), fallback
             number_part = number_id_str.zfill(3)


        # Combine parts
        formatted_id = f"{prefix_id}-{number_part}{suffix_id}"
        # Remove trailing hyphen if suffix was empty
        if formatted_id.endswith('-'): formatted_id = formatted_id[:-1]

        logging.debug(f"[SANITIZE] Formatted ID: {formatted_id}")
        return formatted_id
    else:
        # Fallback if standard pattern doesn't match after cleaning
        # Simple uppercase is often sufficient as a fallback
        fallback_id = cleaned_cid_for_id.upper().replace('_','')
        logging.debug(f"[SANITIZE] Standard formatting pattern didn't match, using fallback: {fallback_id}")
        return fallback_id
# --- End Sanitize ID ---

# --- Helper Functions: sanitize_filename ---
def sanitize_filename(name):
    if not isinstance(name, str): name = str(name);
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name); sanitized = re.sub(r'\s+', ' ', sanitized).strip(); sanitized = re.sub(r'\.+', '.', sanitized).strip(' .'); reserved_names = {'CON', 'PRN', 'AUX', 'NUL'} | {f'COM{i}' for i in range(1, 10)} | {f'LPT{i}' for i in range(1, 10)};
    if sanitized.upper() in reserved_names: sanitized = "_" + sanitized;
    sanitized = sanitized.strip(' .');
    if not sanitized: return "empty_name_fallback";
    max_len = 250;
    while len(sanitized.encode('utf-8')) > max_len: sanitized = sanitized[:-1];
    sanitized = sanitized.strip(' .'); return sanitized

# --- Helper function for Folder Name ---
def format_and_truncate_folder_name(id_val, studio_val, title_val, max_len=150):
    """
    Formats folder name as 'ID [Studio] - Title' (omitting '[Studio] - ' if empty)
    and truncates to max_len, adding ellipsis if truncated.
    """
    # Ensure basic types and handle None/empty
    id_str = str(id_val).strip() if id_val else "NO_ID"
    # Use 'maker' field for studio, handle None/empty
    studio_str = str(studio_val).strip() if studio_val else ""
    # Use potentially translated title, fallback to raw, handle None/empty
    title_str = str(title_val).strip() if title_val else "NO_TITLE"

    # Construct base name - include studio and hyphen only if studio has content
    if studio_str:
        base_name = f"{id_str} [{studio_str}] - {title_str}" # Changed space to " - "
    else:
        base_name = f"{id_str} {title_str}" # Omit brackets and hyphen if studio is empty

    # Truncate if necessary
    if len(base_name) > max_len:
        # Truncate to max_len - 3 to make space for "..."
        # Ensure max_len is at least 3 to avoid negative slice index
        safe_truncate_len = max(0, max_len - 3)
        return base_name[:safe_truncate_len] + "..."
    else:
        return base_name
# --- End Helper Functions ---

# --- Helper Function for Concurrent Scraping ---
def run_single_scraper_task(scraper_name, movie_id,
                            user_agent_for_javlibrary=None, 
                            cf_token_for_javlibrary=None):
    
    thread_name = threading.current_thread().name
    print(f"[{thread_name}] Task Start: Scraper='{scraper_name}', ID='{movie_id}'")

    if scraper_name not in SCRAPER_REGISTRY: 
        print(f"[{thread_name}] Error: Scraper '{scraper_name}' not found in registry.")
        return scraper_name, None

    find_url_func = SCRAPER_REGISTRY[scraper_name]['find']
    scrape_func = SCRAPER_REGISTRY[scraper_name]['scrape']
    scraped_data = None
    target_url_result = None

    try:
        # --- Find URL ---
        if scraper_name == "Javlibrary":
            target_url_result = find_url_func(movie_id, user_agent=user_agent_for_javlibrary, cf_clearance_token=cf_token_for_javlibrary)
        else:
            target_url_result = find_url_func(movie_id)

        if target_url_result == "CF_CHALLENGE":
            logging.warning(f"[{thread_name}] Javlibrary CF Challenge during URL find for {movie_id}.")
            return scraper_name, "CF_CHALLENGE" 

        if target_url_result: 
            # --- Scrape Data ---
            if scraper_name == "Javlibrary":
                data_from_scraper = scrape_func(target_url_result, user_agent=user_agent_for_javlibrary, cf_clearance_token=cf_token_for_javlibrary)
            else:
                data_from_scraper = scrape_func(target_url_result)

            if data_from_scraper == "CF_CHALLENGE":
                logging.warning(f"[{thread_name}] Javlibrary CF Challenge during scraping for {movie_id} from {target_url_result}.")
                return scraper_name, "CF_CHALLENGE" 

            if data_from_scraper: 
                data_from_scraper.pop('folder_url', None)
                data_from_scraper.pop('folder_image_constructed_url', None)
                scraped_data = data_from_scraper
                print(f"[{thread_name}] Success: Scraped data found by {scraper_name}.")
            else:
                print(f"[{thread_name}] Info: {scraper_name} scrape function returned no data for URL {target_url_result}.")
        else:
            print(f"[{thread_name}] Info: No URL found by {scraper_name} for ID '{movie_id}'.")

    except Exception as e:
        print(f"[{thread_name}] CRITICAL Error running {scraper_name} for '{movie_id}': {e}")
        logging.exception(f"Exception in scraper task {scraper_name} for {movie_id}") # Log full traceback

    print(f"[{thread_name}] Task End: Scraper='{scraper_name}', Data Found={scraped_data is not None}")
    return scraper_name, scraped_data
# --- End Helper Function ---

# --- Data Merging Function ---
def merge_scraped_data(scraper_results, field_priorities):
    if not scraper_results:
        print("Merging: No scraper results provided.")
        return {}, {} 

    final_data = {}
    final_data_sources = {} 
    processed_by_priority = set()

    print("-" * 10, "Starting Data Merge", "-" * 10)
    print(f"Received results from: {list(scraper_results.keys())}")

    # --- 1. Apply Field Priorities ---
    # Iterate through the fields defined in settings.py for consistent order
    # The list app_settings.PRIORITY_FIELDS_ORDERED should no longer contain 'folder_url'
    for field in app_settings.PRIORITY_FIELDS_ORDERED:
        priority_list = field_priorities.get(field, [])
        processed_by_priority.add(field) 
        found_value_for_field = False
        for scraper_name in priority_list:
            # Check if this scraper ran and has data for this field
            if scraper_name in scraper_results and scraper_results[scraper_name]:
                data_dict = scraper_results[scraper_name]
                if field in data_dict:
                    value = data_dict.get(field)
                    # Check if value is considered valid (not None, not empty string/list/dict)
                    is_valid = False
                    if isinstance(value, (list, dict)): is_valid = bool(value)
                    elif value is not None and value != '': is_valid = True

                    if is_valid:
                         if field == 'title':
                             # For 'title' field, we want the processed title in final_data['title']
                             # and the original, potentially prefixed title in final_data['title_raw']
                             
                             # 'value' here is data_dict.get('title'), which for Javlibrary is "Actual Title"
                             processed_title_from_scraper = value 
                             
                             # 'title_raw' from the scraper (e.g., Javlibrary's "ID - Actual Title")
                             # Fallback to the processed title if 'title_raw' isn't explicitly provided by the scraper.
                             raw_title_from_scraper = data_dict.get('title_raw', processed_title_from_scraper) 

                             final_data['title'] = processed_title_from_scraper
                             final_data['title_raw'] = raw_title_from_scraper
                             
                             print(f"  Merging Field '{field}': SET 'title' to '{processed_title_from_scraper}' and 'title_raw' to '{raw_title_from_scraper}' using '{scraper_name}'.")
                         else:
                             final_data[field] = value
                             print(f"  Merging Field '{field}': SET using '{scraper_name}'. Value: {value}")
                         
                         final_data_sources[field] = scraper_name
                         found_value_for_field = True
                         if 'source' not in final_data:
                             final_data['source'] = data_dict.get('source', scraper_name.lower())
                         break # Found best value for this field, move to next field
                    # else: # Debugging if needed
                    #     print(f"  Merging Field '{field}': IGNORING invalid value from '{scraper_name}': {value}")
            # else: # Debugging if needed
            #      print(f"  Merging Field '{field}': Scraper '{scraper_name}' not in results or has no data.")

        if not found_value_for_field:
             print(f"  Merging Field '{field}': No valid value found in priority list {priority_list}. Field will be missing or default later.")
             # Ensure key exists but is None/empty if no priority scraper had it
             if field == 'title': # Ensure both title and title_raw are handled
                 final_data['title'] = None
                 final_data['title_raw'] = None
             else:
                 # Adjusted default for non-list/dict fields
                 final_data[field] = [] if field in ['genres', 'actresses', 'screenshot_urls'] else None


    # --- 2. Add Remaining Fields (Not explicitly prioritized) ---
    # Iterate through all scrapers that provided results
    # Use the order they appear in scraper_results
    print("Processing remaining (non-prioritized) fields...")
    all_found_keys = set()
    for scraper_name, results_dict in scraper_results.items():
         if results_dict: # Ensure scraper actually returned data
             all_found_keys.update(results_dict.keys())
             for key, value in results_dict.items():
                  # If the key wasn't handled by priority logic AND isn't already in final_data
                  # AND it's not the folder_url or constructed url we are ignoring
                  if key not in processed_by_priority and key not in final_data \
                     and key not in ['folder_url', 'folder_image_constructed_url']: 
                      # Check if value is valid before adding
                      is_valid = False
                      if isinstance(value, (list, dict)): is_valid = bool(value)
                      elif value is not None and value != '': is_valid = True

                      if is_valid:
                          final_data[key] = value
                          final_data_sources[key] = scraper_name 
                          print(f"  Adding Unprioritized Field '{key}': Using value from '{scraper_name}'. Value: {value}")
                          processed_by_priority.add(key)


    # --- 3. Ensure Essential Keys Exist ---
    # Define a base set of keys expected by the rest of the app
    essential_keys = {'id', 'content_id', 'title', 'title_raw', 'originaltitle',
                      'description', 'release_date', 'release_year', 'runtime',
                      'director', 'maker', 'label', 'series', 'genres',
                      'actresses', 'cover_url', # Keep cover_url as it's the source for the poster
                      'screenshot_urls', 'rating', 'votes', 'set', 'url',
                      'folder_name', 'download_all', 'original_filepath', 'source'}

    # Ensure all essential keys and any keys found during scraping are present
    # Remove folder_url and constructed url from consideration here too
    all_expected_keys = essential_keys.union(
        k for k in all_found_keys if k not in ['folder_url', 'folder_image_constructed_url']
    )

    print("Ensuring essential keys exist...")
    for key in all_expected_keys:
        if key not in final_data:
             final_data[key] = [] if key in ['genres', 'actresses', 'screenshot_urls'] else None
             print(f"  Adding missing essential key '{key}' with default value.")
    # Ensure source has a fallback if still missing
    if not final_data.get('source'): final_data['source'] = 'unknown'
    # Ensure title_raw has a fallback if somehow still missing
    if 'title_raw' not in final_data: final_data['title_raw'] = final_data.get('title')

    print(f"Final Merged Data Keys: {list(final_data.keys())}")
    print("-" * 10, "Finished Data Merge", "-" * 10)
    return final_data, final_data_sources 
# --- End Data Merging ---

# --- Translation Helper Function ---
def _run_translation_script(service, text, target_language, api_key=None):
    if not service or service == "None":
        return None
    # Strip whitespace from text before checking if empty
    text_to_translate = text.strip() if isinstance(text, str) else ""
    if not text_to_translate:
        logging.warning("Translation skipped: Input text is empty or only whitespace.")
        return None

    script_map = {
        "Google": "translate_google.py",
        "DeepL": "translate_deepl.py",
        "DeepSeek": "translate_deepseek.py"
    }
    script_name = script_map.get(service)
    if not script_name:
        logging.error(f"Unknown translation service: {service}")
        return None

    script_path = os.path.join(os.path.dirname(__file__), script_name) 
    if not os.path.exists(script_path):
        logging.error(f"Translation script not found: {script_path}")
        st.error(f"Translation script '{script_name}' not found.")
        return None

    cmd = [sys.executable, script_path, text_to_translate, target_language] 
    if service in ["DeepL", "DeepSeek"]:
        if not api_key:
            logging.error(f"API key required for {service} but not provided.")
            st.toast(f"⚠️ API Key missing for {service} translation.", icon="🔑")
            return None
        cmd.append(api_key)

    # Debug: Print the command being executed
    print(f"--- DEBUG: Executing translation command: {' '.join(cmd)}")

    logging.info(f"Running translation: Service='{service}', Lang='{target_language}', Text='{text_to_translate[:30]}...'")
    translated_text = None
    temp_file_path = None
    try:
        # Set timeout to prevent hanging (e.g., 60 seconds)
        timeout_seconds = 60
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', check=False, timeout=timeout_seconds)

        # Debug: Print script output
        print(f"--- DEBUG: Translation script return code: {result.returncode}")
        print(f"--- DEBUG: Translation script stdout:\n{result.stdout}")
        print(f"--- DEBUG: Translation script stderr:\n{result.stderr}")


        if result.returncode != 0:
            error_message = result.stderr.strip() if result.stderr else f"Translation script '{script_name}' failed with exit code {result.returncode}."
            logging.error(f"Translation Error ({service}): {error_message}")
            st.toast(f"❌ Translation failed ({service}): {error_message[:100]}...", icon="💬")
            return None
        else:
            temp_file_path = result.stdout.strip()
            if not temp_file_path or not os.path.exists(temp_file_path):
                error_message = f"Translation script '{script_name}' succeeded but did not return a valid temp file path (stdout: '{temp_file_path}')."
                if result.stderr: error_message += f"\nStderr: {result.stderr.strip()}"
                logging.error(error_message)
                st.toast(f"❌ Translation error ({service}): Script output error.", icon="📄")
                return None

            # Read the content from the temp file
            with open(temp_file_path, 'r', encoding='utf-8') as f:
                translated_text = f.read()
            logging.info(f"Translation successful ({service}). Translated Text: '{translated_text[:50]}...'")
            return translated_text

    except subprocess.TimeoutExpired:
        logging.error(f"Translation ({service}) timed out after {timeout_seconds} seconds.")
        st.toast(f"⏱️ Translation timed out ({service}).", icon="💬")
        return None
    except FileNotFoundError:
        logging.error(f"Error: Python executable '{sys.executable}' or script '{script_path}' not found.")
        st.error("Translation component error: Python or script not found.")
        return None
    except Exception as e:
        logging.error(f"Unexpected error running translation script ({service}): {e}")
        st.toast(f"💥 Unexpected translation error ({service}). Check logs.", icon="💬")
        return None
    finally:
        # Ensure temporary file is always deleted if path was obtained
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logging.debug(f"Successfully removed temp file: {temp_file_path}")
            except OSError as e:
                logging.error(f"Error removing temporary translation file '{temp_file_path}': {e}")
# --- End Translation Helper ---


# --- Callback Functions ---
def process_input_dir_callback():
    # --- Read input directory and recursive flag from UI state ---
    input_dir_from_state = st.session_state.input_dir.strip()
    recursive_scan_active = st.session_state.get("recursive_scan_active", False)
    st.session_state.last_crawl_was_recursive = recursive_scan_active
    final_input_dir = input_dir_from_state

    if not input_dir_from_state:
        print("[DEBUG CRAWLER] Input directory field is empty. Loading default from settings...")
        latest_defaults_for_input = load_settings() # Assuming load_settings() defined
        default_input_path = latest_defaults_for_input.get("input_dir", "").strip()
        if default_input_path:
            final_input_dir = default_input_path
            print(f"[DEBUG CRAWLER] Using default input directory from settings: {final_input_dir}")
        else:
            st.error("Input Directory field empty and no default set.")
            return
    else:
        print(f"[DEBUG CRAWLER] Using input directory from field: {final_input_dir}")

    if not os.path.isdir(final_input_dir):
        st.error(f"Input Directory invalid: '{final_input_dir}'")
        return

    print("[DEBUG CRAWLER] Loading latest settings from file for callback...")
    latest_settings = load_settings() # Reload settings from JSON/defaults

    enabled_scrapers = latest_settings.get("enabled_scrapers", [])
    if not enabled_scrapers:
        st.error("No scrapers selected in Settings.")
        return
    field_priorities = latest_settings.get("field_priorities", {})
    print(f"[DEBUG CRAWLER] Using Enabled Scrapers: {enabled_scrapers}")

    # --- Javlibrary Credentials Check ---
    if "Javlibrary" in enabled_scrapers and JAVLIBRARY_AVAILABLE:
        if not st.session_state.get("javlibrary_creds_provided_this_session", False):
            st.session_state.show_javlibrary_prompt = True 
            st.warning("Javlibrary scraper is enabled. Please provide your User-Agent and CF Clearance token when prompted at the top of the page.", icon="🔑")
            st.rerun() # 
            return

    # --- Use loaded translation settings ---
    translator_service = latest_settings.get("translator_service", "None") 
    target_language = latest_settings.get("target_language", "") 
    api_key = latest_settings.get("api_key", "") # app_settings.DEFAULT_API_KEY
    translate_title_flag = latest_settings.get("translate_title", False) 
    translate_desc_flag = latest_settings.get("translate_description", False) 
    keep_orig_desc_flag = latest_settings.get("keep_original_description", False) 
    translation_enabled = translator_service != "None"
    translation_possible = True
    if translation_enabled:
        if not target_language:
            st.warning("Translation enabled, but Target Language is not set.", icon="⚠️")
            translation_possible = False
        if translator_service in ["DeepL", "DeepSeek"] and not api_key:
            st.warning(f"Translation enabled for {translator_service}, but API Key is not set.", icon="🔑")
            translation_possible = False
    
    # --- State Init and File Loading ---
    st.session_state.all_movie_data = {}
    st.session_state.current_movie_key = None
    st.session_state.movie_file_paths = []
    processed_files = 0
    skipped_manual_entry = 0
    skipped_nfo_count = 0
    valid_extensions_lower = ('.mp4', '.mkv', '.avi', '.wmv', '.mov') 
    movie_files_to_process = []
    status_text_discovery = st.empty()

    try:
        if not recursive_scan_active:
            status_text_discovery.text(f"Scanning directory: {final_input_dir}...")
            for item_name in os.listdir(final_input_dir):
                item_path = os.path.join(final_input_dir, item_name)
                if os.path.isfile(item_path):
                    filename, ext = os.path.splitext(item_name)
                    if ext.lower() in valid_extensions_lower:
                        nfo_path = os.path.join(final_input_dir, filename + ".nfo")
                        if os.path.exists(nfo_path):
                            skipped_nfo_count += 1
                            continue
                        else:
                            movie_files_to_process.append(item_path)
        else:
            for root, _, files in os.walk(final_input_dir):
                status_text_discovery.text(f"Scanning directory: {root}...")
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    filename_no_ext, ext = os.path.splitext(file_name)
                    if ext.lower() in valid_extensions_lower:
                        nfo_path = os.path.join(root, filename_no_ext + ".nfo")
                        if os.path.exists(nfo_path):
                            skipped_nfo_count += 1
                            continue
                        else:
                            movie_files_to_process.append(file_path)
        status_text_discovery.text("Finished scanning directories.")
    except OSError as e:
        st.error(f"Error scanning Input Directory '{final_input_dir}': {e}")
        status_text_discovery.empty()
        return

    if skipped_nfo_count > 0:
        st.info(f"ℹ️ Skipped {skipped_nfo_count} movie file(s) due to existing .nfo files.")
    status_text_discovery.empty()

    if not movie_files_to_process:
        st.warning(f"No movie files found to process in '{final_input_dir}'" + (" (recursively)" if recursive_scan_active else "") + " or all were skipped.")
        return

    st.session_state.movie_file_paths = sorted(movie_files_to_process)
    total_files = len(st.session_state.movie_file_paths)
    progress_bar = st.progress(0)
    status_text = st.empty()
    default_download_state = latest_settings.get('default_download_all_initial_state', False) 
    max_workers = min(len(enabled_scrapers), os.cpu_count() + 4 if len(enabled_scrapers) > 1 else 1)

    # Get Javlibrary credentials from session state
    current_jl_user_agent = st.session_state.get("javlibrary_user_agent")
    current_jl_cf_token = st.session_state.get("javlibrary_cf_token")
    javlibrary_globally_failed_this_run = False 

    with st.spinner(f"Processing {total_files} movie files..."):
        for i, filepath in enumerate(st.session_state.movie_file_paths):
            if javlibrary_globally_failed_this_run:
                status_text.text("Javlibrary credential failure. Halting further movie processing for this run.")
                break 

            filename_base = os.path.basename(filepath)
            raw_movie_id_from_filename = os.path.splitext(filename_base)[0]
            original_filename_base_for_nfo = raw_movie_id_from_filename
            sanitized_movie_id = sanitize_id_for_scraper(raw_movie_id_from_filename) 

            if not sanitized_movie_id:
                 st.warning(f"Could not sanitize ID from filename '{filename_base}', skipping file.")
                 skipped_manual_entry += 1
                 continue

            status_text.text(f"Processing: {filename_base} (ID: {sanitized_movie_id}) ({i+1}/{total_files}) - Running Scrapers...")
            scraper_results = {}
            any_scraper_succeeded_for_this_movie = False
            futures = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                for scraper_name in enabled_scrapers:
                    ua_for_jl = current_jl_user_agent if scraper_name == "Javlibrary" else None
                    cf_for_jl = current_jl_cf_token if scraper_name == "Javlibrary" else None
                    
                    future = executor.submit(run_single_scraper_task, scraper_name, sanitized_movie_id,
                                             user_agent_for_javlibrary=ua_for_jl,
                                             cf_token_for_javlibrary=cf_for_jl)
                    futures.append(future)

                status_text.text(f"Processing: {filename_base} (ID: {sanitized_movie_id}) ({i+1}/{total_files}) - Waiting for scrapers...")
                
                # Flag to stop processing other scrapers *for this specific movie* if Javlibrary fails
                stop_this_movie_scraper_processing = False

                for future in concurrent.futures.as_completed(futures):
                    try:
                        name, data_result = future.result()
                        if name == "Javlibrary" and data_result == "CF_CHALLENGE":
                            st.error(f"Javlibrary credentials failed for ID '{sanitized_movie_id}' (Cloudflare Challenge). You will be prompted again on the next 'Run Crawlers' attempt if Javlibrary remains enabled.", icon="🚨")
                            st.session_state.javlibrary_creds_provided_this_session = False 
                            # Clear failed credentials from session to avoid reusing them if user doesn't update
                            st.session_state.javlibrary_user_agent = None
                            st.session_state.javlibrary_cf_token = None
                            javlibrary_globally_failed_this_run = True 
                            stop_this_movie_scraper_processing = True 

                            # Cancel other pending futures for this specific movie's scrapers
                            for f_to_cancel in futures:
                                if not f_to_cancel.done():
                                    f_to_cancel.cancel()
                            break 

                        if data_result and data_result != "CF_CHALLENGE":
                            scraper_results[name] = data_result
                            any_scraper_succeeded_for_this_movie = True
                    except concurrent.futures.CancelledError:
                        print(f"A scraper task was cancelled for {filename_base} (likely due to Javlibrary CF failure).")
                    except Exception as exc:
                        print(f"Error retrieving result from future for ID {sanitized_movie_id}: {exc}")
                
                if stop_this_movie_scraper_processing: 
                    progress_bar.progress((i + 1) / total_files) 
                    continue 

            # --- Merging and Translation (only if no global CF fail and some scraper succeeded) ---
            if not javlibrary_globally_failed_this_run and any_scraper_succeeded_for_this_movie:
                status_text.text(f"Processing: {filename_base} (ID: {sanitized_movie_id}) ({i+1}/{total_files}) - Merging data...")
                merged_data, field_sources = merge_scraped_data(scraper_results, field_priorities) 

                if translation_enabled and translation_possible:
                    translation_tasks = []
                    # Capture original texts before potential modification by translation
                    original_title_for_translation = merged_data.get('title')
                    original_description_for_translation = merged_data.get('description')

                    if translate_title_flag and original_title_for_translation:
                        translation_tasks.append({'field': 'title', 'text': original_title_for_translation})
                    
                    if translate_desc_flag and original_description_for_translation:
                        translation_tasks.append({'field': 'description', 'text': original_description_for_translation})

                    if translation_tasks:
                        status_parts = [task['field'].capitalize() for task in translation_tasks]
                        status_text.text(f"{filename_base} ({i+1}/{total_files}) - Translating { ' & '.join(status_parts) }...")
                        
                        translated_results_map = {}
                        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(translation_tasks), 2)) as translator_executor:
                            future_to_task_field = {
                                translator_executor.submit(
                                    _run_translation_script,
                                    translator_service,
                                    task['text'],
                                    target_language,
                                    api_key
                                ): task['field']
                                for task in translation_tasks
                            }
                            for future in concurrent.futures.as_completed(future_to_task_field):
                                field_name = future_to_task_field[future]
                                try:
                                    translated_text = future.result()
                                    if translated_text is not None: # Check if translation script returned something
                                        translated_results_map[field_name] = translated_text
                                except Exception as e:
                                    logging.error(f"Error during {field_name} translation for '{filename_base}': {e}")
                                    st.toast(f"⚠️ {field_name.capitalize()} translation failed for '{filename_base}'.", icon="💬")
                        
                        # Apply successful translations
                        if 'title' in translated_results_map:
                            merged_data['title'] = translated_results_map['title']
                        
                        if 'description' in translated_results_map:
                            translated_desc = translated_results_map['description']
                            if keep_orig_desc_flag and original_description_for_translation:
                                merged_data['description'] = f"{translated_desc}\n\n{original_description_for_translation}"
                            else:
                                merged_data['description'] = translated_desc
                        pass

                # --- GENRE BLACKLIST ---
                current_genre_blacklist_lc = st.session_state.get("genre_blacklist", []) 
                
                if current_genre_blacklist_lc and \
                    'genres' in merged_data and \
                    isinstance(merged_data['genres'], list) and \
                    merged_data['genres']: 
                
                    original_genres_for_movie = merged_data['genres']
                    filtered_movie_genres = [
                        genre_item 
                        for genre_item in original_genres_for_movie 
                        if isinstance(genre_item, str) and \
                            genre_item.strip() and \
                            genre_item.strip().lower() not in current_genre_blacklist_lc
                    ]
                    
                    if len(filtered_movie_genres) < len(original_genres_for_movie):
                        removed_count = len(original_genres_for_movie) - len(filtered_movie_genres)
                        log_msg = (f"[GENRE_BLACKLIST] ID '{sanitized_movie_id}': Removed {removed_count}. "
                                    f"Original: {original_genres_for_movie}, Filtered: {filtered_movie_genres}")
                        logging.info(log_msg) 
                    
                    merged_data['genres'] = filtered_movie_genres
                # --- GENRE BLACKLIST BLOCK ---


                # --- Final Data Preparation ---
                merged_data['_original_filename_base'] = original_filename_base_for_nfo
                merged_data['id'] = sanitized_movie_id
                merged_data['original_filepath'] = filepath
                merged_data['download_all'] = default_download_state
                merged_data['_field_sources'] = field_sources
                semantic_title_for_folder = merged_data.get('title', merged_data.get('title_raw', 'NO_TITLE'))
                final_id = merged_data.get('id', 'NO_ID')
                final_studio = merged_data.get('maker', '')
                final_title = merged_data.get('title', merged_data.get('title_raw', 'NO_TITLE')) 
                prefix_to_check = f"[{final_id}]"
                if final_id != 'NO_ID' and final_title and not final_title.lower().startswith(prefix_to_check.lower()):
                    merged_data['title'] = f"[{final_id}] {final_title}" 
                elif not final_title and final_id != 'NO_ID':
                    merged_data['title'] = f"[{final_id}]" 
                merged_data['folder_name'] = format_and_truncate_folder_name(final_id, final_studio, semantic_title_for_folder) 
                if 'title_raw' not in merged_data or not merged_data.get('title_raw'):
                    merged_data['title_raw'] = merged_data.get('originaltitle', semantic_title_for_folder)
                st.session_state.all_movie_data[filepath] = merged_data
                processed_files += 1
            elif not javlibrary_globally_failed_this_run: # No scraper succeeded, but also no global CF fail
                 st.toast(f"No scraper data for '{sanitized_movie_id}'. Creating manual entry.", icon="✍️")
                 # ... (Your manual data creation logic) ...
                 # Example:
                 manual_data = {
                     'id': sanitized_movie_id, # Use sanitized ID
                     'content_id': sanitized_movie_id, # Use sanitized ID here too? Or keep raw? Let's use sanitized for consistency.
                     '_original_filename_base': original_filename_base_for_nfo,
                     'title': f"[{sanitized_movie_id}]", # Start title with ID prefix
                     'title_raw': '', 'originaltitle': '', 'description': '',
                     'release_date': None, 'release_year': None, 'runtime': None,
                     'director': None, 'maker': None, 'label': None, 'series': None,
                     'genres': [], 'actresses': [], 'cover_url': None, 'screenshot_urls': [],
                     'rating': None, 'votes': None, 'set': None, 'url': None,
                     'source': 'manual',
                     'original_filepath': filepath,
                     'download_all': default_download_state,
                     '_field_sources': {},
                     'folder_name': format_and_truncate_folder_name(sanitized_movie_id, "", "") # Use sanitized ID
                 }
                 st.session_state.all_movie_data[filepath] = manual_data
                 processed_files += 1
                 skipped_manual_entry += 1

            progress_bar.progress((i + 1) / total_files)

    # --- AFTER THE LOOP ---
    if javlibrary_globally_failed_this_run:
        status_text.text(f"Processing halted due to Javlibrary credential failure. Please provide new credentials and 'Run Crawlers' again.")
        # The show_javlibrary_prompt will be True for the next run because javlibrary_creds_provided_this_session is now False.
    else:
        status_text.text(f"Processing complete. Processed: {processed_files} ({skipped_manual_entry} manual entries). Skipped (NFO found): {skipped_nfo_count}.")
    
    if progress_bar: progress_bar.empty()

    if st.session_state.all_movie_data and not javlibrary_globally_failed_this_run:
        st.session_state.current_movie_key = next(iter(st.session_state.all_movie_data))
        st.toast(f"✅ Processed {processed_files} movies!", icon="🎬")
    elif skipped_nfo_count > 0 and not st.session_state.all_movie_data and not javlibrary_globally_failed_this_run:
         st.toast(f"ℹ️ No new movies processed. {skipped_nfo_count} skipped due to existing NFOs.", icon="🤷")
    elif not javlibrary_globally_failed_this_run: 
        st.session_state.current_movie_key = None
        st.toast("ℹ️ No movie data could be retrieved.", icon="🤷")


def organize_all_callback():
    # --- Get the current output directory value from session state ---
    output_dir_from_state = st.session_state.output_dir.strip()
    # --- Read the crawl mode used for the current data ---
    is_recursive_run = st.session_state.get('last_crawl_was_recursive', False)
    print(f"[DEBUG ORGANIZE] Organizer running. Recursive mode detected: {is_recursive_run}")

    # --- Determine the effective *global* output directory (only used if not recursive) ---
    global_output_dir = output_dir_from_state
    if not is_recursive_run: # Only validate/create global output dir if NOT recursive
        if not output_dir_from_state:
            print("[DEBUG ORGANIZE] Output directory field empty (non-recursive). Loading default...")
            latest_defaults = load_settings()
            default_output_path = latest_defaults.get("output_dir", "").strip()
            if default_output_path:
                global_output_dir = default_output_path
                print(f"[DEBUG ORGANIZE] Using default global output directory: {global_output_dir}")
            else:
                st.error("Output Directory field empty and no default set (required for non-recursive organization).")
                return
        # Validate/Create the global output directory if needed for non-recursive run
        if not os.path.isdir(global_output_dir):
            try:
                os.makedirs(global_output_dir, exist_ok=True)
                st.info(f"Output directory '{global_output_dir}' created.")
            except Exception as e:
                st.error(f"Global Output directory path invalid: {e}")
                return
    # --- End Global Output Dir Handling ---

    if not st.session_state.all_movie_data: st.error("No movie data processed yet."); return
    processed_count = 0; error_count = 0; skipped_move_count = 0 
    total_movies = len(st.session_state.all_movie_data); progress_bar = st.progress(0); status_text = st.empty()

    # --- Define path to crop.py (once) ---
    script_dir = os.path.dirname(__file__)
    crop_script_path = os.path.join(script_dir, "crop.py")
    crop_script_exists = os.path.exists(crop_script_path)
    if not crop_script_exists:
        st.warning(f"Crop script 'crop.py' not found in the application directory ({script_dir}). Folder images cannot be generated.")

    with st.spinner(f"Organizing {total_movies} movies..."):
        for i, (original_filepath, data) in enumerate(st.session_state.all_movie_data.items()):
            original_basename = os.path.basename(original_filepath)
            status_text.text(f"Organizing: {original_basename} ({i+1}/{total_movies})")
            download_all_flag = data.get('download_all', False)

            try:
                # Get the standard (formatted) ID for logging/messaging
                movie_id_for_logs = data.get('id', 'UNKNOWN_ID')

                if not os.path.exists(original_filepath):
                    st.toast(f"Skip: Original file '{original_basename}' not found.", icon="⚠️"); error_count += 1; continue

                # --- Determine Target Directory based on Mode ---
                if is_recursive_run:
                    # Recursive: Target directory is the folder containing the original movie
                    target_dir = os.path.dirname(original_filepath)
                    print(f"[DEBUG ORGANIZE RECURSIVE] Target dir for NFO/images: '{target_dir}'")
                else:
                    # Non-Recursive: Construct new folder in the global output directory
                    folder_name_from_data = data.get('folder_name')
                    if folder_name_from_data and str(folder_name_from_data).strip():
                         final_folder_name_before_sanitize = str(folder_name_from_data).strip()
                    else:
                         fb_id = data.get('id', 'NO_ID'); fb_studio = data.get('maker', ''); fb_title = data.get('title', data.get('title_raw', 'NO_TITLE'))
                         final_folder_name_before_sanitize = format_and_truncate_folder_name(fb_id, fb_studio, fb_title)
                    sanitized_folder_name = sanitize_filename(final_folder_name_before_sanitize)
                    if not sanitized_folder_name: sanitized_folder_name = sanitize_filename(movie_id_for_logs) # Use standard ID as fallback

                    target_dir = os.path.join(global_output_dir, sanitized_folder_name)
                    print(f"[DEBUG ORGANIZE NON-RECURSIVE] Target dir for new folder: '{target_dir}'")

                    # Safety Check (Only relevant for non-recursive)
                    crawl_input_dir = load_settings().get("input_dir", "")
                    if not crawl_input_dir: crawl_input_dir = st.session_state.get("input_dir", "")
                    abs_target_dir = os.path.abspath(target_dir)
                    abs_crawl_input_dir = os.path.abspath(crawl_input_dir) if crawl_input_dir else None
                    if abs_crawl_input_dir and abs_target_dir == abs_crawl_input_dir:
                         st.toast(f"Skip: Output folder '{sanitized_folder_name}' is same as crawl Input Dir for '{original_basename}'.", icon="❗")
                         error_count += 1
                         continue

                # --- Create Target Directory (safe for both modes) ---
                # In recursive mode, dir already exists, exist_ok=True handles it.
                # In non-recursive mode, creates the new folder.
                os.makedirs(target_dir, exist_ok=True)

                # --- NFO Generation (Uses the correct target_dir now) ---
                nfo_base_name_to_use = data.get('_original_filename_base')
                if not nfo_base_name_to_use:
                     logging.warning(f"Original filename base not found for '{original_basename}', falling back to formatted ID '{movie_id_for_logs}' for NFO name.")
                     nfo_base_name_to_use = movie_id_for_logs
                sanitized_nfo_filename_base = sanitize_filename(nfo_base_name_to_use)
                if not sanitized_nfo_filename_base:
                    sanitized_nfo_filename_base = sanitize_filename(movie_id_for_logs)

                nfo_filename = f"{sanitized_nfo_filename_base}.nfo"
                nfo_path = os.path.join(target_dir, nfo_filename)
                generate_nfo(data, filename=nfo_path, download_all_flag=download_all_flag)
                processed_image_count_this_movie = 0

                # --- Image Download Helper (Definition unchanged) ---
                def download_image(url, base_filename, current_target_dir, source_page_url="", log_movie_id="UNKNOWN"):
                    nonlocal processed_image_count_this_movie
                    if not url: return None
                    abs_url = urljoin(source_page_url, url); safe_base_filename = sanitize_filename(base_filename); potential_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif'];
                    existing_file = None
                    for ext in potential_extensions:
                        potential_path = os.path.join(current_target_dir, f"{safe_base_filename}{ext}")
                        if os.path.exists(potential_path): existing_file = potential_path; break
                    if existing_file: return existing_file
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0...', 'Referer': source_page_url or 'https://google.com/'}
                        r = requests.get(abs_url, stream=True, timeout=30, headers=headers); r.raise_for_status(); content_type = r.headers.get('content-type'); final_ext = '.jpg'
                        if content_type: mime_type = content_type.split(';')[0].lower(); mime_ext_map = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}; final_ext = mime_ext_map.get(mime_type, '.jpg')
                        final_filename = f"{safe_base_filename}{final_ext}"
                        final_target_img_path = os.path.join(current_target_dir, final_filename)
                        if not os.path.exists(final_target_img_path):
                            with open(final_target_img_path, 'wb') as f:
                                for chunk in r.iter_content(1024*8): f.write(chunk)
                            processed_image_count_this_movie += 1;
                            print(f"[DEBUG DL] Successfully downloaded: {final_filename} to {current_target_dir}")
                            return final_target_img_path
                        else:
                            print(f"[DEBUG DL] Image '{final_filename}' already exists in {current_target_dir} (checked again).")
                            return final_target_img_path
                    except requests.exceptions.Timeout: st.toast(f"DL Timeout: '{base_filename}' for {log_movie_id}.", icon="⏱️")
                    except requests.exceptions.RequestException as e: st.toast(f"DL Fail: '{base_filename}' for {log_movie_id} ({e}).", icon="❌")
                    except Exception as e: st.toast(f"DL Error: '{base_filename}' for {log_movie_id} ({e}).", icon="💥")
                    return None
                # --- End Image Download Helper ---

                source_url = data.get('url', ''); screenshot_urls = data.get('screenshot_urls', [])

                # --- Poster Download ---
                poster_url_to_download = data.get('poster_manual_url') or get_auto_poster_url(data)
                downloaded_poster_path = None
                if poster_url_to_download:
                    downloaded_poster_path = download_image(poster_url_to_download, "fanart", target_dir, source_url, log_movie_id=movie_id_for_logs)
                else:
                    print(f"[DEBUG ORGANIZE] No poster URL for {movie_id_for_logs}.")

                # --- Folder Image Generation ---
                if downloaded_poster_path and os.path.exists(downloaded_poster_path) and crop_script_exists:
                    poster_ext = os.path.splitext(downloaded_poster_path)[1]
                    folder_img_path = os.path.join(target_dir, f"folder{poster_ext}")
                    if not os.path.exists(folder_img_path):
                        try:
                            cmd = [sys.executable, crop_script_path, downloaded_poster_path, folder_img_path]
                            # ... (rest of crop execution logic) ...
                            print(f"--- DEBUG: Running crop command: {' '.join(cmd)}")
                            result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8', timeout=15)
                            if result.returncode == 0 and os.path.exists(folder_img_path):
                                print(f"--- DEBUG: Successfully created folder image: {folder_img_path}")
                            elif result.returncode == 0 and not os.path.exists(folder_img_path):
                                st.warning(f"Crop script OK but output '{os.path.basename(folder_img_path)}' not found for '{original_basename}'.", icon="⚠️")
                                print(f"--- DEBUG: Crop script stdout/stderr:\n{result.stdout}\n{result.stderr}")
                            else:
                                st.error(f"Error crop.py (code {result.returncode}) for '{os.path.basename(downloaded_poster_path)}'. Check console.")
                                print(f"--- ERROR: Crop script failed for {downloaded_poster_path} ---\nReturn Code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}")
                                if os.path.exists(folder_img_path):
                                    try: os.remove(folder_img_path)
                                    except OSError: pass
                        except FileNotFoundError: st.error(f"Error: Python executable '{sys.executable}' or crop script '{crop_script_path}' not found.")
                        except subprocess.TimeoutExpired: st.error(f"Error: Cropping '{os.path.basename(downloaded_poster_path)}' timed out.")
                        except Exception as crop_e: st.error(f"Unexpected error cropping '{os.path.basename(downloaded_poster_path)}': {crop_e}")
                    else:
                         print(f"[DEBUG CROP] Folder image '{os.path.basename(folder_img_path)}' already exists in {target_dir}. Skipping crop.")
                elif not downloaded_poster_path or not os.path.exists(downloaded_poster_path): print(f"[DEBUG CROP] Skipping folder img gen for '{original_basename}', poster issue.")
                elif not crop_script_exists: print(f"[DEBUG CROP] Skipping folder img gen for '{original_basename}', crop.py missing.")


                # --- Screenshot Download (Uses the correct target_dir now) ---
                if download_all_flag:
                    actual_poster_url_downloaded = poster_url_to_download
                    screenshots_to_process = [ss_url for ss_url in screenshot_urls if ss_url and ss_url != actual_poster_url_downloaded]
                    if screenshots_to_process: print(f"[DEBUG ORGANIZE] Downloading {len(screenshots_to_process)} screenshots to {target_dir}...")
                    for ss_idx, url_img in enumerate(screenshots_to_process):
                        download_image(url_img, f"screenshot_{ss_idx+1}", target_dir, source_url, log_movie_id=movie_id_for_logs)

                # --- Conditional Move Movie File ---
                if not is_recursive_run:
                    # Only move the file if NOT in recursive mode
                    target_movie_path = os.path.join(target_dir, original_basename)
                    abs_target_movie_path = os.path.abspath(target_movie_path)
                    abs_original_filepath = os.path.abspath(original_filepath)

                    if abs_original_filepath != abs_target_movie_path:
                        if not os.path.exists(target_movie_path):
                            try:
                                print(f"[DEBUG ORGANIZE NON-RECURSIVE] Moving '{abs_original_filepath}' to '{abs_target_movie_path}'")
                                shutil.move(original_filepath, target_movie_path)
                            except Exception as move_error:
                                st.error(f"Failed to move '{original_basename}': {move_error}")
                                error_count += 1
                                continue 
                        else:
                            st.toast(f"Skip move: '{original_basename}' already exists in target '{target_dir}'.", icon="ℹ️")
                            skipped_move_count += 1 
                    else:
                        st.toast(f"Skip move: Source/Target path identical for '{original_basename}'.", icon="ℹ️")
                        skipped_move_count += 1
                else:
                    # Recursive mode: Log that move is skipped
                    print(f"[DEBUG ORGANIZE RECURSIVE] Skipping move for '{original_basename}'. File remains in '{os.path.dirname(original_filepath)}'.")


                processed_count += 1
            except Exception as e:
                st.error(f"Unexpected error organizing '{original_basename}': {e}")
                logging.exception(f"Organizer loop error for {original_basename}") # Log traceback
                error_count += 1
            progress_bar.progress((i + 1) / total_movies)

    # --- End Main Loop ---
    status_text.text(f"Organization complete. Processed: {processed_count}. Errors: {error_count}. Skipped Moves (Non-Recursive): {skipped_move_count}.") # Adjusted message
    if progress_bar: progress_bar.empty()
    if processed_count > 0: st.toast(f"💾 Successfully organized {processed_count} movies!", icon="🎉")
    elif error_count == 0 and skipped_move_count == 0 and total_movies > 0 and not is_recursive_run: st.toast("No movies needed organization (already done?).", icon="🤷")
    elif error_count == 0 and total_movies > 0 and is_recursive_run: st.toast("Finished placing NFO/images in existing folders.", icon="✅") # Different message for recursive success
    elif total_movies == 0 : st.toast("No movie data to organize.", icon="🤷")


def apply_changes_callback():
    st.session_state._apply_changes_triggered = True

    # --- CHECK IF MOVIE KEY IS VALID ---
    if st.session_state.current_movie_key and st.session_state.current_movie_key in st.session_state.all_movie_data:
        original_movie_key = st.session_state.current_movie_key

        # --- GET ORIGINAL EDITOR URL ---
        original_editor_poster = st.session_state.get('_original_editor_poster_url', '')

        # Get current data for reference
        current_data = st.session_state.all_movie_data[original_movie_key]

        try:
            # --- HELPER FUNCTION TO SAFELY GET & STRIP FORM VALUES ---
            def safe_get_strip(key):
                val = st.session_state.get(key)
                return str(val).strip() if key in st.session_state and val is not None else ""

            # --- READ ALL SUBMITTED VALUES FROM EDITOR STATE ---
            submitted_poster_url = safe_get_strip('editor_poster_url')
            submitted_title = safe_get_strip('editor_title')
            submitted_original_title = safe_get_strip('editor_original_title')
            submitted_desc = st.session_state.get('editor_desc', '')
            if submitted_desc is None: submitted_desc = ""

            submitted_folder_name = safe_get_strip('editor_folder_name')
            submitted_id = safe_get_strip('editor_id')
            submitted_content_id = safe_get_strip('editor_content_id')
            submitted_year = safe_get_strip('editor_year')
            submitted_date = safe_get_strip('editor_date')
            submitted_runtime = safe_get_strip('editor_runtime')
            submitted_director = safe_get_strip('editor_director')
            submitted_maker = safe_get_strip('editor_maker')
            submitted_label = safe_get_strip('editor_label')
            submitted_series = safe_get_strip('editor_series')
            submitted_genres_str = st.session_state.get('editor_genres', '') # Read raw string
            submitted_actresses_str = st.session_state.get('editor_actresses', '') # Read raw string

            # --- CHECK IF EDITOR URL FIELD CHANGED (Only Poster) ---
            poster_input_changed = submitted_poster_url != original_editor_poster
            manual_url_input_changed = poster_input_changed

            # --- PREPARE DICTIONARY OF VALUES TO UPDATE ---
            updated_values = {
                'folder_name': submitted_folder_name,
                'id': submitted_id,
                'content_id': submitted_content_id,
                'title': submitted_title,
                'originaltitle': submitted_original_title,
                'description': submitted_desc,
                'release_year': submitted_year,
                'release_date': submitted_date,
                'runtime': submitted_runtime,
                'director': submitted_director,
                'maker': submitted_maker,
                'label': submitted_label,
                'series': submitted_series,
                'genres': [g.strip() for g in submitted_genres_str.split(',') if isinstance(submitted_genres_str, str) and g.strip()],
                'actresses': [{'name': a.strip()} for a in submitted_actresses_str.split(',') if isinstance(submitted_actresses_str, str) and a.strip()],
                'poster_manual_url': submitted_poster_url,
            }

            # --- CONDITIONALLY OVERWRITE SCREENSHOTS ---
            if manual_url_input_changed:
                updated_values['screenshot_urls'] = [] # Clear the list

            # Debug print
            # if 'screenshot_urls' in updated_values:
            #      print(f"  - screenshot_urls: {updated_values.get('screenshot_urls')}")
            # else:
            #      print(f"  - screenshot_urls: (Not in update dict - preserving existing)")


            # --- PERFORM THE UPDATE on the main data dictionary ---
            st.session_state.all_movie_data[original_movie_key].update(updated_values)

            # --- SUCCESS FEEDBACK ---
            st.toast(f"Changes applied for '{os.path.basename(original_movie_key)}'.", icon="🖊️")

        except Exception as e:
            # --- ERROR HANDLING ---
            st.error(f"Failed to apply changes: {e}")
            st.session_state._apply_changes_triggered = False 

    else:
        # --- HANDLING FOR INVALID MOVIE KEY ---
        st.error("No movie selected or data not found.")
        st.session_state._apply_changes_triggered = False 

# --- NEW: Callback for Re-Scraping with URL ---
def rescrape_with_url_callback():
    current_movie_key = st.session_state.current_movie_key
    selected_scraper_for_rescrape = st.session_state.get("rescrape_scraper_select")
    rescrape_url = st.session_state.get("rescrape_url_input", "").strip()

    if not current_movie_key or current_movie_key not in st.session_state.all_movie_data:
        st.error("No movie selected or data not found for re-scraping.")
        return

    if not selected_scraper_for_rescrape:
        st.error("Please select a scraper for re-scraping.")
        return

    if not rescrape_url:
        st.error("Please enter a URL for re-scraping.")
        return

    if selected_scraper_for_rescrape not in SCRAPER_REGISTRY:
        st.error(f"Selected scraper '{selected_scraper_for_rescrape}' is not available.")
        return

    # Javlibrary credentials check for re-scrape
    if selected_scraper_for_rescrape == "Javlibrary" and JAVLIBRARY_AVAILABLE:
        if not st.session_state.get("javlibrary_creds_provided_this_session", False):
            st.session_state.show_javlibrary_prompt = True 
            st.warning("Javlibrary selected for re-scrape. Please provide credentials via the prompt at the top of the page, then try re-scraping again.", icon="🔑")
            st.rerun()
            return

    status_placeholder = st.empty() 
    status_placeholder.info(f"Re-scraping '{os.path.basename(current_movie_key)}' using {selected_scraper_for_rescrape} from URL...")

    scrape_func = SCRAPER_REGISTRY[selected_scraper_for_rescrape]['scrape']
    newly_scraped_data = None
    try:
        if selected_scraper_for_rescrape == "Javlibrary":
            current_jl_user_agent = st.session_state.get("javlibrary_user_agent")
            current_jl_cf_token = st.session_state.get("javlibrary_cf_token")
            raw_data = scrape_func(rescrape_url, user_agent=current_jl_user_agent, cf_clearance_token=current_jl_cf_token)
        else:
            raw_data = scrape_func(rescrape_url)

        if raw_data == "CF_CHALLENGE":
            st.error(f"Javlibrary credentials failed for re-scrape (Cloudflare Challenge). Please provide valid credentials and try again.", icon="🚨")
            st.session_state.javlibrary_creds_provided_this_session = False
            st.session_state.javlibrary_user_agent = None
            st.session_state.javlibrary_cf_token = None
            status_placeholder.empty()
            st.rerun()
            return
        elif raw_data:
            newly_scraped_data = raw_data
            newly_scraped_data.pop('folder_url', None)
            newly_scraped_data.pop('folder_image_constructed_url', None)
        else:
            st.warning(f"Scraper '{selected_scraper_for_rescrape}' did not return any data from the URL: {rescrape_url}")
            status_placeholder.empty()
            return

    except Exception as e:
        st.error(f"Error during re-scrape with '{selected_scraper_for_rescrape}': {e}")
        logging.exception(f"Error re-scraping {current_movie_key} with {selected_scraper_for_rescrape}")
        status_placeholder.empty()
        return

    if newly_scraped_data:
        status_placeholder.info("Re-scrape successful. Processing data...")
        
        original_movie_entry = st.session_state.all_movie_data[current_movie_key]
        processed_data_for_movie = {}

        # 1. Preserve essential fields
        processed_data_for_movie['_original_filename_base'] = original_movie_entry.get('_original_filename_base')
        processed_data_for_movie['original_filepath'] = original_movie_entry.get('original_filepath')
        # Use default from app_settings if not found in original entry
        default_dl_all_initial = app_settings.DEFAULT_DOWNLOAD_ALL_INITIAL_STATE if SETTINGS_LOADED else False
        processed_data_for_movie['download_all'] = original_movie_entry.get('download_all', default_dl_all_initial)


        # 2. Initialize with base structure then populate with newly scraped data
        base_keys_to_init = (set(app_settings.PRIORITY_FIELDS_ORDERED) | 
                             {'content_id', 'originaltitle', 'release_year', 'runtime', 
                              'director', 'maker', 'label', 'series', 'cover_url', 
                              'rating', 'votes', 'set'})
        
        for key in base_keys_to_init:
            if key in ['genres', 'actresses', 'screenshot_urls']:
                processed_data_for_movie[key] = []
            else:
                processed_data_for_movie[key] = None
        
        processed_data_for_movie.update(newly_scraped_data)

        # 3. Set source and URL
        processed_data_for_movie['source'] = newly_scraped_data.get('source',selected_scraper_for_rescrape.lower())
        processed_data_for_movie['url'] = rescrape_url 
        
        # 4. Set _field_sources
        field_sources_for_rescrape = {}
        for key in newly_scraped_data.keys():
            if key not in ['folder_url', 'folder_image_constructed_url']:
                 field_sources_for_rescrape[key] = selected_scraper_for_rescrape
        processed_data_for_movie['_field_sources'] = field_sources_for_rescrape

        # 5. ID handling
        if 'id' not in newly_scraped_data or not newly_scraped_data.get('id'):
            processed_data_for_movie['id'] = original_movie_entry.get('id', sanitize_id_for_scraper(original_movie_entry.get('_original_filename_base','')))
        if 'content_id' not in processed_data_for_movie or not processed_data_for_movie.get('content_id'):
            processed_data_for_movie['content_id'] = processed_data_for_movie.get('id')


        # --- Re-apply Translations ---
        current_settings = load_settings()
        translator_service = current_settings.get("translator_service", "None")
        target_language = current_settings.get("target_language", "")
        api_key_trans = current_settings.get("api_key", "")
        translate_title_flag = current_settings.get("translate_title", False)
        translate_desc_flag = current_settings.get("translate_description", False)
        keep_orig_desc_flag = current_settings.get("keep_original_description", False)
        translation_enabled = translator_service != "None"
        translation_possible_for_rescrape = True
        if translation_enabled:
            if not target_language: translation_possible_for_rescrape = False
            if translator_service in ["DeepL", "DeepSeek"] and not api_key_trans: translation_possible_for_rescrape = False

        if translation_enabled and translation_possible_for_rescrape:
            status_placeholder.info("Translating re-scraped data...")
            # Use title from newly_scraped_data (pre-translation) for translation source
            title_to_translate = newly_scraped_data.get('title', '') 
            desc_to_translate = newly_scraped_data.get('description', '')

            if translate_title_flag and title_to_translate:
                translated_title = _run_translation_script(translator_service, title_to_translate, target_language, api_key_trans)
                if translated_title:
                    processed_data_for_movie['title'] = translated_title
            
            if translate_desc_flag and desc_to_translate:
                translated_desc = _run_translation_script(translator_service, desc_to_translate, target_language, api_key_trans)
                if translated_desc:
                    if keep_orig_desc_flag and desc_to_translate: # Keep original from scraper
                        processed_data_for_movie['description'] = f"{translated_desc}\n\n{desc_to_translate}"
                    else:
                        processed_data_for_movie['description'] = translated_desc
        
        # --- Re-apply Genre Blacklist ---
        status_placeholder.info("Applying genre blacklist...")
        current_genre_blacklist_lc = current_settings.get("genre_blacklist", [])
        if current_genre_blacklist_lc and \
           'genres' in processed_data_for_movie and \
           isinstance(processed_data_for_movie['genres'], list) and \
           processed_data_for_movie['genres']:
            
            original_genres_for_movie = processed_data_for_movie['genres']
            filtered_movie_genres = [
                genre_item 
                for genre_item in original_genres_for_movie 
                if isinstance(genre_item, str) and \
                   genre_item.strip() and \
                   genre_item.strip().lower() not in current_genre_blacklist_lc
            ]
            processed_data_for_movie['genres'] = filtered_movie_genres

        # --- Final Data Preparation ---
        status_placeholder.info("Finalizing data...")
        final_id_for_formatting = processed_data_for_movie.get('id', 'NO_ID')
        final_studio_for_formatting = processed_data_for_movie.get('maker', '')
        
        # title_raw should be the original, non-translated title from the scraper.
        processed_data_for_movie['title_raw'] = newly_scraped_data.get('title_raw', newly_scraped_data.get('title', ''))
        if not processed_data_for_movie['title_raw']:
            processed_data_for_movie['title_raw'] = processed_data_for_movie.get('originaltitle', '')

        # semantic_title_for_folder: use translated title if available, else title_raw
        semantic_title_for_folder = processed_data_for_movie.get('title', processed_data_for_movie.get('title_raw', 'NO_TITLE'))
        if final_id_for_formatting != 'NO_ID' and semantic_title_for_folder.lower().startswith(f"[{final_id_for_formatting.lower()}]"):
             # If semantic title (potentially translated one) is ALREADY prefixed from scraper, remove prefix for folder name logic
             semantic_title_for_folder = semantic_title_for_folder[len(final_id_for_formatting)+2:].strip()


        # Current 'title' in processed_data_for_movie is the display title (potentially translated)
        current_display_title_for_prefix = processed_data_for_movie.get('title', '')
        prefix_to_check = f"[{final_id_for_formatting}]"
        if final_id_for_formatting != 'NO_ID' and current_display_title_for_prefix and not current_display_title_for_prefix.lower().startswith(prefix_to_check.lower()):
            processed_data_for_movie['title'] = f"[{final_id_for_formatting}] {current_display_title_for_prefix}"
        elif not current_display_title_for_prefix and final_id_for_formatting != 'NO_ID':
            processed_data_for_movie['title'] = f"[{final_id_for_formatting}]"
        
        processed_data_for_movie['folder_name'] = format_and_truncate_folder_name(
            final_id_for_formatting, 
            final_studio_for_formatting, 
            semantic_title_for_folder
        )
        
        if 'originaltitle' not in processed_data_for_movie or not processed_data_for_movie.get('originaltitle'):
            processed_data_for_movie['originaltitle'] = processed_data_for_movie.get('title_raw', '')

        st.session_state.all_movie_data[current_movie_key] = processed_data_for_movie
        
        status_placeholder.empty()
        st.toast(f"Successfully re-scraped and updated '{os.path.basename(current_movie_key)}'!", icon="✅")
        
        st.session_state._apply_changes_triggered = False

# --- Other Callbacks (update_download_all_flag, go_previous/next_movie) remain unchanged ---
def update_download_all_flag():
    movie_key = st.session_state.current_movie_key; checkbox_key = f"cb_download_all_{movie_key}"
    if movie_key and checkbox_key in st.session_state and movie_key in st.session_state.all_movie_data:
        st.session_state.all_movie_data[movie_key]['download_all'] = st.session_state[checkbox_key]

def go_previous_movie():
    if st.session_state.current_movie_key and st.session_state.all_movie_data:
        keys = list(st.session_state.all_movie_data.keys())
        try: current_index = keys.index(st.session_state.current_movie_key)
        except ValueError:
             if keys: st.session_state.current_movie_key = keys[0]; st.rerun(); return 
        if current_index > 0:
            st.session_state.current_movie_key = keys[current_index - 1]
            st.session_state._apply_changes_triggered = False 

def go_next_movie():
     if st.session_state.current_movie_key and st.session_state.all_movie_data:
        keys = list(st.session_state.all_movie_data.keys())
        try: current_index = keys.index(st.session_state.current_movie_key)
        except ValueError:
             if keys: st.session_state.current_movie_key = keys[0]; st.rerun(); return 
        if current_index < len(keys) - 1:
            st.session_state.current_movie_key = keys[current_index + 1]
            st.session_state._apply_changes_triggered = False 
# --- End Callbacks ---

# --- Save Settings Callback ---
def save_settings_callback():
    print("Save Settings button clicked.")
    # Update enabled scrapers list from checkboxes
    enabled_list = []
    for scraper_name in AVAILABLE_SCRAPER_NAMES:
        checkbox_key = f"enable_{scraper_name}"
        if st.session_state.get(checkbox_key, False):
            enabled_list.append(scraper_name)
    st.session_state.enabled_scrapers = enabled_list
    print(f"Updated enabled_scrapers: {st.session_state.enabled_scrapers}")

    # Update field priorities from text inputs
    new_priorities = {}
    try:
        # Create a mapping for case-insensitive lookup: lowercase name -> canonical name
        available_scrapers_lower = {name.lower(): name for name in AVAILABLE_SCRAPER_NAMES}

        # Use the updated ordered list from settings (which shouldn't have folder_url)
        for field_key in app_settings.PRIORITY_FIELDS_ORDERED:
            input_key = f"priority_{field_key}"
            if input_key in st.session_state:
                priority_str = st.session_state[input_key].strip()
                user_priority_list = [s.strip() for s in priority_str.split(',') if s.strip()]

                # Validate user input case-insensitively and store canonical names, preserving order
                validated_list = []
                for name in user_priority_list:
                    if name.lower() in available_scrapers_lower:
                        validated_list.append(available_scrapers_lower[name.lower()])

                new_priorities[field_key] = validated_list
            else:
                 # Fallback to current state if widget key missing
                 new_priorities[field_key] = st.session_state.field_priorities.get(field_key, [])
        st.session_state.field_priorities = new_priorities
        print(f"Updated field_priorities: {st.session_state.field_priorities}")
    except Exception as e:
         st.error(f"Error processing field priorities: {e}"); return

    # Directories are now directly updated in session state via shared keys
    print(f"Input directory state: {st.session_state.input_dir}")
    print(f"Output directory state: {st.session_state.output_dir}")

    # --- Update Translation Settings in Session State (Unchanged) ---
    print(f"Translator service: {st.session_state.translator_service}")
    print(f"Target language: {st.session_state.target_language}")
    print(f"Translate Title: {st.session_state.translate_title}")
    print(f"Translate Description: {st.session_state.translate_description}")
    print(f"Keep Original Desc: {st.session_state.keep_original_description}")
    # API key is intentionally not printed to console

    # --- GENRE BLACKLIST ---
    if "ui_genre_blacklist_input_settings" in st.session_state:
        blacklist_input_str = st.session_state.ui_genre_blacklist_input_settings
        
        if isinstance(blacklist_input_str, str) and blacklist_input_str.strip():
            parsed_blacklist = [
                genre.strip().lower() 
                for genre in blacklist_input_str.split(',') 
                if genre.strip()
            ]
            st.session_state.genre_blacklist = sorted(list(set(parsed_blacklist)))
        else: 
            st.session_state.genre_blacklist = [] 
        
        print(f"Updated st.session_state.genre_blacklist from UI: {st.session_state.genre_blacklist}")
    elif "genre_blacklist" not in st.session_state: # Ensure key exists even if UI element somehow missing
         st.session_state.genre_blacklist = []
         print("Warning: 'ui_genre_blacklist_input_settings' not in st.session_state, initialized genre_blacklist to empty.")
    # --- GENRE BLACKLIST ---

    save_settings_to_file()
# --- End Save Settings Callback ---

# --- Sidebar ---
st.sidebar.header("Navigation")
page_options = ["Crawler", "Settings"]
current_page_index = 0
if 'current_page' in st.session_state:
    try: current_page_index = page_options.index(st.session_state.current_page)
    except ValueError: current_page_index = 0
st.sidebar.selectbox( "Select Page", options=page_options, key="current_page", index=current_page_index, label_visibility="collapsed")
st.sidebar.divider()

if st.session_state.current_page == "Crawler":
    st.sidebar.header("Crawler")
    crawler_view_options = ["Editor", "Raw Data"]
    current_crawler_view_index = 0
    if 'crawler_view' in st.session_state:
         try: current_crawler_view_index = crawler_view_options.index(st.session_state.crawler_view)
         except ValueError: current_crawler_view_index = 0
    st.sidebar.radio( "View Mode", options=crawler_view_options, key="crawler_view", index=current_crawler_view_index, label_visibility="collapsed")
# --- End Sidebar ---

# --- Main Page Content ---
if st.session_state.current_page == "Crawler":
    st.markdown("<h1 style='padding-top: 0px; margin-top: 0px;'>🎬 Movie Scraper & Organizer</h1>", unsafe_allow_html=True)

    # --- Javlibrary Credentials Prompt UI ---
    # JAVLIBRARY_AVAILABLE should be a global flag set during scraper import
    if st.session_state.get("show_javlibrary_prompt") and \
       ("Javlibrary" in st.session_state.get("enabled_scrapers", []) or \
        st.session_state.get("rescrape_scraper_select") == "Javlibrary") and \
       JAVLIBRARY_AVAILABLE: # Check if scraper module itself is available
        
        with st.container(border=True): 
            st.subheader("Javlibrary Credentials Required for this Session")
            st.caption(
                "Javlibrary scraper is enabled. Please provide your current browser **User-Agent** string "
                "and a valid **`cf_clearance` cookie value** from `javlibrary.com`. "
                "You can typically find the User-Agent by searching 'what is my user agent' in your browser, "
                "and the `cf_clearance` cookie in your browser's developer tools (Application/Storage -> Cookies) "
                "after successfully solving a challenge on their site."
            )
            
            with st.form("javlibrary_credentials_form_main_page"): 
                jl_user_agent_input_val = st.text_input(
                    "Your Browser User-Agent:",
                    key="jl_user_agent_input_crawler_page", 
                    placeholder="e.g., Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
                    value=st.session_state.get("javlibrary_user_agent", "") 
                )
                jl_cf_token_input_val = st.text_input(
                    "CF Clearance Token (from javlibrary.com cookie):",
                    key="jl_cf_token_input_crawler_page", # Unique key for the input widget
                    value=st.session_state.get("javlibrary_cf_token", "") 
                )
                submitted_jl_credentials_main = st.form_submit_button("Save Javlibrary Credentials for this Session")

                if submitted_jl_credentials_main:
                    if jl_user_agent_input_val and jl_user_agent_input_val.strip() and \
                       jl_cf_token_input_val and jl_cf_token_input_val.strip():
                        
                        st.session_state.javlibrary_user_agent = jl_user_agent_input_val.strip()
                        st.session_state.javlibrary_cf_token = jl_cf_token_input_val.strip()
                        st.session_state.show_javlibrary_prompt = False 
                        st.session_state.javlibrary_creds_provided_this_session = True 
                        
                        st.success("Javlibrary credentials received for this session. You can now click 'Run Crawlers' or 'Fetch & Replace'.", icon="✅")
                        st.rerun() 
                    else:
                        st.error("Both User-Agent and CF Clearance Token are required for Javlibrary.", icon="🚫")
                        st.session_state.javlibrary_creds_provided_this_session = False 

    # --- Inputs: Directories ---
    col_in, col_out = st.columns(2)

    latest_defaults_for_placeholder = load_settings()
    default_input_placeholder_path = latest_defaults_for_placeholder.get("input_dir", "")
    default_output_placeholder_path = latest_defaults_for_placeholder.get("output_dir", "")
    input_placeholder = f"Default: {default_input_placeholder_path}" if default_input_placeholder_path else "Enter path..."
    output_placeholder = f"Default: {default_output_placeholder_path}" if default_output_placeholder_path else "Enter path..."
    # --- End placeholder loading ---

    with col_in:
        with st.form("input_dir_form_crawler_page"):
            st.text_input(
                "Input Directory",
                key="input_dir",
                help="Folder containing movie files (e.g., ABCD-123.mp4). Set default in Settings.",
                placeholder=input_placeholder
            )

            # Create columns for the button and the checkbox
            col_btn, col_cb = st.columns([1.5, 1]) 

            with col_btn:
                # Button with default size
                submitted_input = st.form_submit_button("▶️ Run Crawlers")

            with col_cb:
                # Ensure key exists before accessing
                if "recursive_scan_active" not in st.session_state: st.session_state.recursive_scan_active = False
                st.checkbox("Recursive Scan", key="recursive_scan_active", value=st.session_state.recursive_scan_active,
                            help="Scans Input Directory and all subfolders. Save & Organize will use existing folders as basis.")

            # The callback trigger remains outside the columns but inside the form
            if submitted_input:
                process_input_dir_callback()

    with col_out:
        # Output directory input is now only relevant if NOT doing a recursive scan
        output_dir_help_text = ("Folder where organized movie folders will be created (if Recursive Scan is OFF). Set default in Settings."
                                if not st.session_state.get("last_crawl_was_recursive", False)
                                else "Output Directory (Ignored when Recursive Scan was used for crawling).")
        output_dir_disabled = st.session_state.get("last_crawl_was_recursive", False)

        with st.form("output_dir_form_crawler_page"):
            st.text_input(
                "Output Directory",
                key="output_dir",
                help=output_dir_help_text,
                placeholder=output_placeholder,
                disabled=output_dir_disabled # Disable if last crawl was recursive
            )
            # Add hint if disabled
            if output_dir_disabled:
                st.caption("Output Directory ignored because last crawl used 'Recursive Scan'. Output will be placed next to original files.")

            organize_button_label = "💾 Save & Organize" + (" (Recursive Mode)" if st.session_state.get("last_crawl_was_recursive", False) else "")
            submitted_output = st.form_submit_button(organize_button_label)
            if submitted_output: organize_all_callback()

    # --- View Rendering (based on crawler_view state) ---
    if st.session_state.crawler_view == "Editor":
        # --- Movie Selection & Navigation ---
        if st.session_state.all_movie_data:
            valid_keys = [fp for fp in st.session_state.all_movie_data.keys() if fp]
            if valid_keys:
                # Display full path in dropdown if last crawl was recursive for clarity
                is_recursive_display = st.session_state.get("last_crawl_was_recursive", False)
                movie_options = {fp: (fp if is_recursive_display else os.path.basename(fp)) for fp in valid_keys}

                if st.session_state.current_movie_key not in movie_options:
                    st.session_state.current_movie_key = valid_keys[0] if valid_keys else None
                    if st.session_state.current_movie_key: 
                         st.session_state._apply_changes_triggered = False

                current_index = 0
                if st.session_state.current_movie_key:
                    try:
                        current_index = valid_keys.index(st.session_state.current_movie_key)
                    except ValueError:
                        st.session_state.current_movie_key = valid_keys[0] if valid_keys else None
                        current_index = 0
                        if st.session_state.current_movie_key: 
                             st.session_state._apply_changes_triggered = False

                nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 5])
                with nav_col1: st.button("⬅️ Previous", on_click=go_previous_movie, disabled=(current_index == 0 or not st.session_state.current_movie_key), use_container_width=True)
                with nav_col2: st.button("Next ➡️", on_click=go_next_movie, disabled=(current_index >= len(valid_keys) - 1 or not st.session_state.current_movie_key), use_container_width=True)

                def update_current_movie_selection():
                    st.session_state.current_movie_key = st.session_state.movie_selector
                    st.session_state._apply_changes_triggered = False 

                with nav_col3:
                    st.selectbox("Select Movie:",
                                 options=valid_keys,
                                 format_func=lambda fp: movie_options.get(fp, "Unknown File"),
                                 key="movie_selector",
                                 index=current_index,
                                 on_change=update_current_movie_selection, 
                                 label_visibility="collapsed",
                                 disabled=(not valid_keys))

                # --- Display Contributing Scrapers --- << MODIFIED SECTION >>
                if st.session_state.current_movie_key: 
                    data = st.session_state.all_movie_data.get(st.session_state.current_movie_key, {})
                    field_sources = data.get('_field_sources', {}) 

                    if field_sources: 
                        # Get unique scraper names that contributed
                        contributing_scrapers = sorted(list(set(field_sources.values())))
                        if contributing_scrapers:
                            st.caption(f"**Sources:** {', '.join([f'**`{s}`**' for s in contributing_scrapers])}") # <-- MODIFIED LINE
                        else:
                            st.caption("No specific field sources recorded.")
                    elif data.get('source') == 'manual':
                         st.caption("**Source:** Manual Entry (No scrapers found data)") # Indicate manual entry
                    else:
                        st.caption("Field source information not available.")
                # --- End Display Contributing Scrapers ---

            else:
                st.warning("Movie data dictionary is empty or invalid.")
        elif st.session_state.movie_file_paths:
            st.warning("Processed input directory, but no data could be scraped.")
        else:
            st.info("👋 Welcome! Enter an Input Directory above and click 'Run Crawlers'.")

        # --- Editor Form ---
        if st.session_state.current_movie_key and st.session_state.current_movie_key in st.session_state.all_movie_data:

            apply_changes_was_triggered = st.session_state.get('_apply_changes_triggered', False)

            if apply_changes_was_triggered:
                st.session_state._apply_changes_triggered = False
            else:
                # --- Pre-populate session state for editor widgets ---
                data = st.session_state.all_movie_data[st.session_state.current_movie_key]

                def to_str(val): return str(val) if val is not None else ""

                st.session_state.editor_id = to_str(data.get('id'))
                st.session_state.editor_content_id = to_str(data.get('content_id'))
                st.session_state.editor_folder_name = data.get('folder_name', '')
                st.session_state.editor_title = to_str(data.get('title', ''))
                st.session_state.editor_original_title = to_str(data.get('originaltitle', ''))
                if not st.session_state.editor_title: st.session_state.editor_title = to_str(data.get('title_raw', ''))
                st.session_state.editor_desc = to_str(data.get('description'))
                st.session_state.editor_year = to_str(data.get('release_year'))
                st.session_state.editor_date = to_str(data.get('release_date'))
                st.session_state.editor_runtime = to_str(data.get('runtime'))
                st.session_state.editor_director = to_str(data.get('director'))
                st.session_state.editor_maker = to_str(data.get('maker'))
                st.session_state.editor_label = to_str(data.get('label'))
                st.session_state.editor_series = to_str(data.get('series'))
                genres_list = data.get('genres', []) or []
                st.session_state.editor_genres = ", ".join(to_str(g).strip() for g in genres_list if to_str(g).strip())
                actresses_list = data.get('actresses', []) or []
                st.session_state.editor_actresses = ", ".join(to_str(a.get('name', '')).strip() for a in actresses_list if isinstance(a, dict) and to_str(a.get('name', '')).strip())

                # Poster URL Pre-population
                auto_poster_url = get_auto_poster_url(data)
                default_poster_input_url = data.get('poster_manual_url');
                if default_poster_input_url is None: default_poster_input_url = auto_poster_url or ''
                st.session_state.editor_poster_url = to_str(default_poster_input_url)

                # REMOVED Folder URL Pre-population

                # Store original editor state (only poster now)
                st.session_state._original_editor_poster_url = st.session_state.editor_poster_url
                print(f"[DEBUG PREPOP] Stored original editor poster URL: '{st.session_state._original_editor_poster_url}'")
                # --- End Pre-population Block ---


            # --- The Form ---
            with st.form(key="editor_form"):
                img_col, text_col = st.columns([1.2, 2])

                # --- Image Preview Section ---
                with img_col:
                    # Poster Preview
                    display_poster_url = st.session_state.get('editor_poster_url', '')
                    if display_poster_url:
                        data_for_display = st.session_state.all_movie_data.get(st.session_state.current_movie_key, {})
                        try:
                            abs_display_poster_url = urljoin(data_for_display.get('url', ''), display_poster_url)
                            source_lower = data_for_display.get('source', '').lower()
                            if source_lower.startswith('r18') or source_lower.startswith('mgs') or source_lower == 'manual': 
                                st.image(abs_display_poster_url, caption="Poster Preview") 
                            else:
                                st.image(abs_display_poster_url, use_container_width=True, caption="Poster Preview")
                        except Exception as img_e: st.warning(f"Could not load poster preview: {img_e}")
                    else: st.info("No poster image URL provided. Add one below.") 


                # --- Metadata Inputs Column ---
                with text_col:
                    id_col1, id_col2 = st.columns(2);
                    with id_col1: st.text_input("ID", key="editor_id")
                    with id_col2: st.text_input("Content ID", key="editor_content_id", help="Internal Scraper ID.")
                    st.text_input("Folder Name", key="editor_folder_name", help="Output folder name.")
                    st.text_input("Title", key="editor_title", help="Potentially translated title. Saved directly to NFO title.")
                    st.text_input("Original Title", key="editor_original_title", help="Original language title (e.g., Japanese).")
                    st.text_area("Description / Plot", height=120, key="editor_desc", help="Potentially translated/combined description.")
                    col1, col2 = st.columns(2);
                    with col1:
                        st.text_input("Release Year", key="editor_year");
                        st.text_input("Release Date (YYYY-MM-DD)", key="editor_date");
                        st.text_input("Runtime (min)", key="editor_runtime");
                        st.text_input("Director", key="editor_director");
                    with col2:
                        st.text_input("Maker/Studio", key="editor_maker");
                        st.text_input("Label", key="editor_label");
                        st.text_input("Series", key="editor_series");
                        st.text_input("Genres", key="editor_genres"); # Comma-separated input
                        st.text_input("Actresses", key="editor_actresses") # Comma-separated input
                    # Only Poster URL input remains
                    st.text_input("Cover", key="editor_poster_url", help="URL for fanart.jpg. Cleared value uses auto-detected. Manually set value overrides.")

                    apply_callback_func = apply_changes_callback if ('apply_changes_callback' in globals() and callable(apply_changes_callback)) else None
                    if apply_callback_func is None:
                         print("[ERROR] apply_changes_callback function not found!")
                         st.error("Apply changes callback not defined!")
                    submitted_edit = st.form_submit_button(
                        "🖊️ Apply Changes",
                        on_click=apply_callback_func,
                        disabled=(apply_callback_func is None)
                    )
                    # Callback handles the rest

            # --- Elements outside the form ---
            # Re-fetch data after potential update
            data = st.session_state.all_movie_data.get(st.session_state.current_movie_key, {})

            # --- Re-Scrape Section ---
            
            # Checkbox to toggle visibility of the re-scrape section
            st.checkbox("Show Manual Re-Crawl Options", key="show_rescrape_section")

            if st.session_state.get("show_rescrape_section", False): # Check if the checkbox is ticked
                with st.container(border=True):
                    st.subheader("Re-Scrape with Specific URL")
                    st.caption("If the initial scrape was incorrect, select a scraper, provide the correct URL to the movie's page, and fetch new data. This will replace the current movie's metadata.")
                    
                    # Use all available scrapers, not just enabled ones for bulk scan
                    scraper_options_rescrape = [""] + AVAILABLE_SCRAPER_NAMES 
                    current_rescrape_scraper_idx = 0
                    if st.session_state.get("rescrape_scraper_select") in scraper_options_rescrape:
                        current_rescrape_scraper_idx = scraper_options_rescrape.index(st.session_state.rescrape_scraper_select)

                    st.selectbox(
                        "Select Scraper:", 
                        options=scraper_options_rescrape, 
                        index=current_rescrape_scraper_idx,
                        key="rescrape_scraper_select",
                        help="Choose the scraper corresponding to the URL you provide."
                    )
                    st.text_input(
                        "Movie URL:", 
                        key="rescrape_url_input", 
                        placeholder="e.g., https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=abc00123/",
                        help="Paste the direct URL to the movie's page on the selected scraper's site."
                    )
                    st.button(
                        "🔄 Fetch & Replace Movie Data", 
                        on_click=rescrape_with_url_callback, 
                        disabled=(not st.session_state.get("rescrape_scraper_select") or not AVAILABLE_SCRAPER_NAMES) 
                    )

            # Per-Movie Checkbox (Unchanged)
            checkbox_key = f"cb_download_all_{st.session_state.current_movie_key}"
            st.checkbox( "Download all additional images for this movie",
                         value=data.get('download_all', False),
                         key=checkbox_key,
                         on_change=update_download_all_flag,
                         help="Downloads fanart (poster) and additional images. Folder image is always generated from fanart.") # Updated help text

            # Additional Images display
            screenshots = data.get('screenshot_urls', [])
            if screenshots:
                auto_poster_url_display = get_auto_poster_url(data)
                actual_poster_url_displayed = data.get('poster_manual_url', auto_poster_url_display)
                screenshots_to_display = [ ss_url for ss_url in screenshots if ss_url and ss_url != actual_poster_url_displayed]
                if screenshots_to_display:
                    st.markdown("---"); st.subheader("Additional Images")
                    num_screenshots = len(screenshots_to_display); num_cols = min(num_screenshots, 4);
                    if num_cols > 0:
                        cols_imgs = st.columns(num_cols);
                        field_sources = data.get('_field_sources', {})
                        screenshots_list_source = field_sources.get('screenshot_urls')
                        overall_source = data.get('source', '').lower()
                        no_stretch = False
                        # Determine stretch based on specific list source first, then overall
                        if screenshots_list_source in ['r18dev', 'r18dev Ja']: no_stretch = True
                        elif overall_source == 'mgs': no_stretch = True
                        elif screenshots_list_source is None and overall_source.startswith('r18'): no_stretch = True
                        elif overall_source == 'manual': no_stretch = True # Don't stretch if manual

                        for idx, img_url in enumerate(screenshots_to_display):
                             with cols_imgs[idx % num_cols]:
                                 try:
                                     abs_ss_url = urljoin(data.get('url', ''), img_url)
                                     if no_stretch:
                                         st.image(abs_ss_url, caption=f"Image {idx+1}") # No stretch
                                     else:
                                         st.image(abs_ss_url, use_container_width=True, caption=f"Image {idx+1}")
                                 except Exception as ss_e: st.warning(f"Image {idx+1} error: {ss_e}")

            elif 'screenshot_urls' in data and not data['screenshot_urls']:
                 if data.get('poster_manual_url') or data.get('cover_url'): 
                     st.info("Additional images list is empty. This could be due to a manual Poster URL change, no scraped screenshots, or if the poster was the only image.")
                 else: # No poster and no screenshots
                     st.info("No images (poster or screenshots) available for this movie.")
        # --- End Editor Form conditional block ---

    elif st.session_state.crawler_view == "Raw Data":
        st.subheader("Processed Movie Data")
        if st.session_state.current_movie_key and st.session_state.current_movie_key in st.session_state.all_movie_data:
            current_movie_data = st.session_state.all_movie_data[st.session_state.current_movie_key]
            # Display full path if last crawl was recursive
            display_key_name = (st.session_state.current_movie_key
                                if st.session_state.get("last_crawl_was_recursive", False)
                                else os.path.basename(st.session_state.current_movie_key))
            st.caption(f"Displaying processed data for: {display_key_name}")
            # Display a copy, removing fields we no longer handle internally
            display_data = current_movie_data.copy()
            display_data.pop('folder_url', None)
            display_data.pop('folder_image_constructed_url', None)
            display_data.pop('folder_manual_url', None) # Remove this from display too
            st.json(display_data, expanded=True)
        elif st.session_state.all_movie_data:
             st.info("Select a movie in the 'Editor' view to see its processed data here.")
        else:
            st.info("No data processed yet. Use 'Run Crawlers' first.")
    # --- End View Rendering ---

# --- Settings Page ---
elif st.session_state.current_page == "Settings":
    sync_settings_from_file_to_state()
    st.markdown("<h1 style='padding-top: 0px; margin-top: 0px;'>⚙️ Settings</h1>", unsafe_allow_html=True)

    with st.form("settings_form"):

        # Enabled Scrapers
        st.subheader("Enabled Scrapers")
        st.caption("Select which scrapers to run when 'Run Crawlers' is clicked.")
        for scraper_name in AVAILABLE_SCRAPER_NAMES:
            specific_help = None # Default to no specific help
            if scraper_name == "Javlibrary":
                specific_help = "Requires providing User-Agent and CF Clearance token when prompted on the Crawler page."
            elif scraper_name == "Mgs":
                specific_help = "May require a Japanese IP address."
            st.checkbox(scraper_name,
                         key=f"enable_{scraper_name}",
                         value=(scraper_name in st.session_state.get('enabled_scrapers', [])),
                         help=specific_help
                         )

        # Field Priority
        st.subheader("Field Priority")
        st.caption("Define the order scrapers are checked (left-to-right) for each field. Enter scraper names separated by commas (e.g., DMM, R18.Dev, MGS). Invalid names are ignored.")
        if 'field_priorities' in st.session_state and hasattr(app_settings, 'ORDERED_PRIORITY_FIELDS_WITH_LABELS'):
            ordered_fields_with_labels = app_settings.ORDERED_PRIORITY_FIELDS_WITH_LABELS
            total_fields = len(ordered_fields_with_labels)
            num_columns = 3
            base_items_per_col = total_fields // num_columns
            remainder = total_fields % num_columns

            cols = st.columns(num_columns)
            field_idx = 0
            for col_idx in range(num_columns):
                with cols[col_idx]:
                    items_in_this_col = base_items_per_col + (1 if col_idx < remainder else 0)
                    for _ in range(items_in_this_col):
                        if field_idx < total_fields:
                            # Field key should NOT be 'folder_url' if list is updated
                            field_key, display_label = ordered_fields_with_labels[field_idx]
                            current_priority_list = st.session_state.field_priorities.get(field_key, [])
                            st.text_input(
                                label=display_label,
                                key=f"priority_{field_key}", # State automatically updated
                                value=", ".join(current_priority_list), # Display current value
                                help=f"Priority for '{display_label}'. Available: {', '.join(AVAILABLE_SCRAPER_NAMES)}"
                            )
                            field_idx += 1
                        else: break
        else:
             st.warning("Field priorities not found in session state or settings.")

        st.subheader("Genre Blacklist")
        st.caption("Enter genres to exclude, separated by commas (e.g., Short, Parody, Featured). This is case-insensitive.")
        
        # Pre-fill the text_area with the current blacklist from session_state, joined as a string.
        current_blacklist_display_str = ", ".join(st.session_state.get("genre_blacklist", []))
        st.text_area(
            "Blacklisted Genres:",
            key="ui_genre_blacklist_input_settings", 
            value=current_blacklist_display_str,
            height=100,
            help="Genres listed here will be removed from movie data."
        )

        st.subheader("Translation")
        # Translation settings (Unchanged)
        translator_options = ["None", "Google", "DeepL", "DeepSeek"]
        st.selectbox("Translator Service", options=translator_options, key="translator_service")
        st.text_input("Target Language Code", key="target_language", help="e.g., EN, DE, FR. Check service documentation for supported codes.")
        st.text_input("API Key", key="api_key", type="password", help="Required for DeepL and DeepSeek services.")
        st.checkbox("Translate Title", key="translate_title")
        col_desc1, col_desc2 = st.columns(2)
        with col_desc1: st.checkbox("Translate Description", key="translate_description")
        with col_desc2: st.checkbox("Keep Original Description", key="keep_original_description", help="If 'Translate Description' is also checked, appends translation below original text.")


        st.subheader("Directories")
        # Directories settings
        current_settings_input_val = st.session_state.get("input_dir", "")
        st.text_input("Default Input Directory", key="input_dir", help="Set the default path for the 'Input Directory' field on the Crawler page.")
        current_settings_output_val = st.session_state.get("output_dir", "")
        st.text_input("Default Output Directory", key="output_dir", help="Set the default path for the 'Output Directory' field on the Crawler page.")

        # Save button uses the updated callback
        save_button = st.form_submit_button("💾 Save All Settings", use_container_width=True, on_click=save_settings_callback)

# --- End Settings Page ---
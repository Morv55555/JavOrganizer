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
        DEFAULT_EDITOR_SHOW_SCREENSHOTS = False
        DEFAULT_GENRE_BLACKLIST = []
        DEFAULT_NAMING_POSTER_FILENAME_PATTERN = "poster"
        DEFAULT_NAMING_FOLDER_IMAGE_FILENAME_PATTERN = "folder"
        DEFAULT_NAMING_SCREENSHOT_FILENAME_PATTERN = "fanart{n}"
        DEFAULT_NAMING_NFO_TITLE_PATTERN = "[{id}] {title}"
        DEFAULT_NAMING_FOLDER_NAME_PATTERN = "{id} [{studio}] - {title}"
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
        "naming_poster_filename_pattern": app_settings.DEFAULT_NAMING_POSTER_FILENAME_PATTERN,
        "naming_folder_image_filename_pattern": app_settings.DEFAULT_NAMING_FOLDER_IMAGE_FILENAME_PATTERN,
        "naming_screenshot_filename_pattern": app_settings.DEFAULT_NAMING_SCREENSHOT_FILENAME_PATTERN,
        "naming_nfo_title_pattern": app_settings.DEFAULT_NAMING_NFO_TITLE_PATTERN,
        "naming_folder_name_pattern": app_settings.DEFAULT_NAMING_FOLDER_NAME_PATTERN,
        "editor_show_screenshots": app_settings.DEFAULT_EDITOR_SHOW_SCREENSHOTS,
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
            loaded_settings["editor_show_screenshots"] = user_settings.get("editor_show_screenshots", defaults["editor_show_screenshots"])

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

            # Load Naming Convention Settings
            loaded_settings["naming_poster_filename_pattern"] = user_settings.get("naming_poster_filename_pattern", defaults["naming_poster_filename_pattern"])
            loaded_settings["naming_folder_image_filename_pattern"] = user_settings.get("naming_folder_image_filename_pattern", defaults["naming_folder_image_filename_pattern"])
            loaded_settings["naming_screenshot_filename_pattern"] = user_settings.get("naming_screenshot_filename_pattern", defaults["naming_screenshot_filename_pattern"])
            loaded_settings["naming_nfo_title_pattern"] = user_settings.get("naming_nfo_title_pattern", defaults["naming_nfo_title_pattern"])
            loaded_settings["naming_folder_name_pattern"] = user_settings.get("naming_folder_name_pattern", defaults["naming_folder_name_pattern"])


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
        "naming_poster_filename_pattern": st.session_state.naming_poster_filename_pattern,
        "naming_folder_image_filename_pattern": st.session_state.naming_folder_image_filename_pattern,
        "naming_screenshot_filename_pattern": st.session_state.naming_screenshot_filename_pattern,
        "naming_nfo_title_pattern": st.session_state.naming_nfo_title_pattern,
        "naming_folder_name_pattern": st.session_state.naming_folder_name_pattern,
        "editor_show_screenshots": st.session_state.get("editor_show_screenshots", app_settings.DEFAULT_EDITOR_SHOW_SCREENSHOTS),
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
    st.session_state.naming_poster_filename_pattern = loaded_settings["naming_poster_filename_pattern"]
    st.session_state.naming_folder_image_filename_pattern = loaded_settings["naming_folder_image_filename_pattern"]
    st.session_state.naming_screenshot_filename_pattern = loaded_settings["naming_screenshot_filename_pattern"]
    st.session_state.naming_nfo_title_pattern = loaded_settings["naming_nfo_title_pattern"]
    st.session_state.naming_folder_name_pattern = loaded_settings["naming_folder_name_pattern"]
    st.session_state.editor_show_screenshots = loaded_settings.get("editor_show_screenshots", app_settings.DEFAULT_EDITOR_SHOW_SCREENSHOTS)

    print(f"  Synced input_dir: {st.session_state.input_dir}")
    print(f"  Synced output_dir: {st.session_state.output_dir}")
    print(f"  Synced enabled_scrapers: {st.session_state.enabled_scrapers}")
    print(f"  Synced genre_blacklist: {st.session_state.get('genre_blacklist')}")
    print(f"  Synced NFO title pattern: {st.session_state.naming_nfo_title_pattern}")

# --- Page Config & Styles ---
st.set_page_config(page_title="JavOrganizer", layout="wide", initial_sidebar_state="collapsed")
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

    # Naming Convention Settings
    st.session_state.naming_poster_filename_pattern = loaded_settings.get("naming_poster_filename_pattern", app_settings.DEFAULT_NAMING_POSTER_FILENAME_PATTERN)
    st.session_state.naming_folder_image_filename_pattern = loaded_settings.get("naming_folder_image_filename_pattern", app_settings.DEFAULT_NAMING_FOLDER_IMAGE_FILENAME_PATTERN)
    st.session_state.naming_screenshot_filename_pattern = loaded_settings.get("naming_screenshot_filename_pattern", app_settings.DEFAULT_NAMING_SCREENSHOT_FILENAME_PATTERN)
    st.session_state.naming_nfo_title_pattern = loaded_settings.get("naming_nfo_title_pattern", app_settings.DEFAULT_NAMING_NFO_TITLE_PATTERN)
    st.session_state.naming_folder_name_pattern = loaded_settings.get("naming_folder_name_pattern", app_settings.DEFAULT_NAMING_FOLDER_NAME_PATTERN)
    st.session_state.editor_show_screenshots = loaded_settings.get("editor_show_screenshots", app_settings.DEFAULT_EDITOR_SHOW_SCREENSHOTS)


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
    # download_all_flag is the per-movie value

    # Helper to add an element if value is not None/empty
    def add_element(parent, tag_name, text_value, attributes=None):
        if text_value is not None:
            # Convert to string, strip, and check if non-empty
            processed_text = str(text_value).strip()
            if processed_text: # Only add if there's actual content after stripping
                elem = ET.SubElement(parent, tag_name)
                elem.text = processed_text
                if attributes:
                    for attr_name, attr_value in attributes.items():
                        elem.set(attr_name, str(attr_value))
                return elem
        return None

    # Helper to add an empty element (like <epbookmark />)
    def add_empty_element(parent, tag_name, attributes=None):
        elem = ET.SubElement(parent, tag_name)
        if attributes:
            for attr_name, attr_value in attributes.items():
                elem.set(attr_name, str(attr_value))
        return elem

    movie = ET.Element('movie')
    base_page_url = data.get('url', '') # For resolving relative image URLs

    # --- Order roughly based on blueprint ---
    add_element(movie, 'title', data.get('title'))
    add_element(movie, 'originaltitle', data.get('originaltitle'))
    add_empty_element(movie, 'epbookmark')
    add_element(movie, 'year', data.get('release_year'))

    # Ratings
    rating_value_from_data = data.get('rating')
    rating_val_to_use = None
    votes_val_to_use = "0"

    if isinstance(rating_value_from_data, dict):
        rating_val_to_use = rating_value_from_data.get('Rating')
        votes_val_to_use = str(rating_value_from_data.get('Votes', '0'))
    elif rating_value_from_data is not None:
        rating_val_to_use = rating_value_from_data

    if rating_val_to_use is not None and str(rating_val_to_use).strip():
        ratings_tag = ET.SubElement(movie, 'ratings')
        rating_tag = add_element(ratings_tag, 'rating', None)
        if rating_tag is not None:
            rating_tag.set('name', 'NFO') # Blueprint has 'NFO' as name
            rating_tag.set('default', 'true') # Changed from 'false' to 'true' as per blueprint (if this is the main rating)
            rating_tag.set('max', '10')
            add_element(rating_tag, 'value', rating_val_to_use)
            add_element(rating_tag, 'votes', votes_val_to_use)

    add_element(movie, 'userrating', "0.0") # As per blueprint
    add_element(movie, 'top250', "0") # As per blueprint

    # Set (Series)
    series_name = data.get('series')
    if series_name and str(series_name).strip():
        set_tag = ET.SubElement(movie, 'set')
        add_element(set_tag, 'name', series_name)
        add_empty_element(set_tag, 'overview') # As per blueprint

    add_element(movie, 'plot', data.get('description'))
    add_element(movie, 'outline', data.get('description')) # Duplicate plot for outline
    add_element(movie, 'tagline', data.get('tagline'))
    add_element(movie, 'runtime', data.get('runtime'))

    # Primary Poster Thumb (outside fanart)
    primary_image_url_to_use = data.get('poster_manual_url') or get_auto_poster_url(data)
    if primary_image_url_to_use:
        try:
            abs_primary_url = urljoin(base_page_url, primary_image_url_to_use)
            add_element(movie, 'thumb', abs_primary_url, attributes={'aspect': 'poster'})
        except Exception as e:
            st.warning(f"Could not process primary image URL {primary_image_url_to_use} for NFO <thumb>: {e}")

    add_element(movie, 'mpaa', data.get('mpaa'))
    add_empty_element(movie, 'certification') # As per blueprint
    add_empty_element(movie, 'id') # Movie root ID tag, empty as per blueprint

    add_element(movie, 'premiered', data.get('release_date'))
    add_element(movie, 'watched', "false") # As per blueprint
    add_element(movie, 'playcount', "0") # As per blueprint
    add_empty_element(movie, 'lastplayed') # As per blueprint

    # Genres
    for genre_text in data.get('genres', []):
        add_element(movie, 'genre', genre_text)

    add_element(movie, 'studio', data.get('maker'))
    add_element(movie, 'director', data.get('director'))

    # Tag (from series name, as per blueprint)
    if series_name and str(series_name).strip():
        add_element(movie, 'tag', series_name)

    # Actors
    for actor_data in data.get('actresses', []):
        actor_name = actor_data.get('name', '')
        if actor_name and str(actor_name).strip():
            actor_tag = ET.SubElement(movie, 'actor')
            add_element(actor_tag, 'name', actor_name)
            add_element(actor_tag, 'role', "Actress") # Fixed role as per blueprint example
            add_empty_element(actor_tag, 'thumb') # Empty as per blueprint (unless we add actress thumbs)
            add_empty_element(actor_tag, 'profile') # As per blueprint

    add_empty_element(movie, 'trailer') # Empty for now, as per blueprint

    # --- Fanart section ---
    fanart_thumbs_to_add = [] # Initialize list for ALL fanart thumbs
    # 1. Get the primary image URL (what was previously the poster)
    # primary_image_url_to_use is already defined above
    if primary_image_url_to_use:
        try:
            abs_primary_url = urljoin(base_page_url, primary_image_url_to_use)
            fanart_thumbs_to_add.insert(0, abs_primary_url)
        except Exception as e:
            st.warning(f"Could not process primary image URL {primary_image_url_to_use} for NFO fanart: {e}")

    # 2. Add screenshots if flag is set
    if download_all_flag: # Use the flag passed into the function
        screenshot_urls = data.get('screenshot_urls', [])
        primary_abs_url_for_check = fanart_thumbs_to_add[0] if fanart_thumbs_to_add else None
        for ss_url in screenshot_urls:
            if ss_url:
                 try:
                     abs_ss_url = urljoin(base_page_url, ss_url)
                     if abs_ss_url != primary_abs_url_for_check and abs_ss_url not in fanart_thumbs_to_add:
                          fanart_thumbs_to_add.append(abs_ss_url)
                 except Exception as e:
                     st.warning(f"Could not add screenshot thumb {ss_url} to NFO fanart: {e}")

    # 3. Create the <fanart> tag and add all collected <thumb> elements
    if fanart_thumbs_to_add:
        fanart = ET.SubElement(movie, 'fanart')
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
    # --- END REVERTED fanart section ---


    # Original Filename
    original_basename_from_data = data.get('_original_filename_base')
    original_filepath_from_data = data.get('original_filepath')
    if original_basename_from_data and original_filepath_from_data:
        try:
            _, ext = os.path.splitext(os.path.basename(original_filepath_from_data))
            if ext:
                add_element(movie, 'original_filename', f"{original_basename_from_data}{ext}")
        except Exception as e:
            st.warning(f"Could not determine original_filename: {e}")

    # Source (text field, e.g., "dmm_jp", as per blueprint)
    add_element(movie, 'source', data.get('source', 'unknown'))
    add_empty_element(movie, 'edition') # As per blueprint


    # --- XML Output ---
    try:
        xml_str = ET.tostring(movie, encoding='UTF-8', method='xml')
        xml_declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
        pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="  ")
        pretty_xml_str = pretty_xml_str.replace('<?xml version="1.0" ?>', '', 1).strip()
        final_xml = xml_declaration + pretty_xml_str
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', encoding='UTF-8') as f:
            f.write(final_xml)
    except Exception as e:
        st.error(f"Error writing NFO file '{filename}': {e}")
        raise IOError(f"Error writing NFO file '{filename}': {e}")
# --- End Generate NFO ---

# --- Helper Function: Sanitize ID for Scrapers ---
def sanitize_id_for_scraper(raw_id):
    """
    Cleans and formats an ID string (often from a filename) before sending it to scrapers.
    Attempts to convert various formats (e.g., abc00123, h_1814nmsl00003, 118abf118, abc-123-1080p)
    into a more standard format (e.g., ABC-123, NMSL-003, ABF-118, ABC-123).
    """
    if not raw_id: return None
    logging.debug(f"[SANITIZE] Original raw_id: {raw_id}")

    # --- 1. Prefix Cleaning ---
    prefixes_to_clean = [
        'h_086', 'h_113', 'h_068', 'h_729',
        r'^h_\d+_?',
        r'^\d+(?=[a-zA-Z])'
    ]
    id_after_prefix_clean = raw_id.lower()
    for prefix_pattern in prefixes_to_clean:
        original_len = len(id_after_prefix_clean)
        if prefix_pattern == r'^\d+(?=[a-zA-Z])':
            id_after_prefix_clean = re.sub(prefix_pattern, '', id_after_prefix_clean)
        else:
            match_prefix = re.match(prefix_pattern, id_after_prefix_clean)
            if match_prefix:
                id_after_prefix_clean = id_after_prefix_clean[len(match_prefix.group(0)):]
        if len(id_after_prefix_clean) < original_len:
            logging.debug(f"[SANITIZE] Removed prefix matching '{prefix_pattern}'. Remaining: '{id_after_prefix_clean}'")

    logging.debug(f"[SANITIZE] ID after prefix cleaning: '{id_after_prefix_clean}'")

    # --- 2. Core ID Extraction and Trail Truncation ---
    id_to_format = id_after_prefix_clean # Default

    # Regex to identify the core JAV ID structure at the beginning of the string.
    # Group 1: The entire matched core ID (e.g., "abc-123", "ebod123a", "studio-name-456vr")
    # It looks for:
    #   - A text part (letters, numbers, underscores, possibly internal hyphens)
    #   - Optionally followed by a hyphen
    #   - Followed by numbers
    #   - Optionally followed by a short (0-4 char) alphabetic suffix.
    # This needs to be anchored at the start of the string (after prefix cleaning).
    # The (?=...) is a lookahead to check for common trail separators or end of string.
    core_id_regex = r'^(([a-z0-9_]+(?:[-_][a-z0-9_]+)*?)\-?(\d+)([a-z]{0,4}))'
    # Breakdown of the capturing group `(...)`:
    # `([a-z0-9_]+(?:[-_][a-z0-9_]+)*?)` : Studio/text prefix (non-greedy to allow hyphen to be next)
    # `\-?`                               : Optional hyphen
    # `(\d+)`                             : Number part
    # `([a-z]{0,4})`                      : Optional short suffix (like 'a', 'vr')

    match = re.match(core_id_regex, id_after_prefix_clean)

    if match:
        potential_core_id = match.group(1) # The full matched potential core ID
        end_of_potential_core = match.end(1)

        # Check if there's anything after this potential core ID
        if end_of_potential_core < len(id_after_prefix_clean):
            char_after_core = id_after_prefix_clean[end_of_potential_core]
            trail_separators = ['-', '_', '.', '['] # Common characters that indicate a trail
            # Common trail keywords (lowercase) that might not have a separator
            # (e.g., "id123cd" where "cd" is a trail, not part of the ID's suffix) - less common with good core_id_regex
            # trail_keywords_pattern = r'^(cd|1080p|720p|hd|fullhd|uhd|4k|part|extra|uncensored|ch)'

            if char_after_core in trail_separators:
                id_to_format = potential_core_id
                removed_trail = id_after_prefix_clean[end_of_potential_core:]
                logging.debug(f"[SANITIZE] Trail '{removed_trail}' (separator: '{char_after_core}') identified. Core for formatting: '{id_to_format}'")
            # else if re.match(trail_keywords_pattern, id_after_prefix_clean[end_of_potential_core:]):
            #     id_to_format = potential_core_id
            #     removed_trail = id_after_prefix_clean[end_of_potential_core:]
            #     logging.debug(f"[SANITIZE] Trail '{removed_trail}' (keyword match) identified. Core for formatting: '{id_to_format}'")
            else:
                # If no common trail separator/keyword, assume the matched part is the full ID or needs to be handled by final formatting
                # This path might be taken if the suffix in core_id_regex was shorter than actual, or if it's an unusual ID.
                # We will still use `potential_core_id` if the regex matched something, otherwise `id_after_prefix_clean`
                id_to_format = potential_core_id # Stick with what core_id_regex found as the best guess
                logging.debug(f"[SANITIZE] Core ID regex matched '{potential_core_id}'. No clear trail separator immediately after. Proceeding with this for formatting.")
        else:
            # The core_id_regex matched the entire string
            id_to_format = potential_core_id
            logging.debug(f"[SANITIZE] Core ID regex matched the entire string: '{id_to_format}'. No trail.")
    else:
        logging.debug(f"[SANITIZE] Core ID regex did not match '{id_after_prefix_clean}'. Will use it as is for final formatting.")
        # id_to_format remains id_after_prefix_clean

    logging.debug(f"[SANITIZE] ID before final formatting: '{id_to_format}'")

    # --- 3. Standard ID Formatting (applied to id_to_format) ---
    # This regex splits the id_to_format into its main components:
    # Group 1: The entire text/studio prefix part (e.g., "ebod", "studio-name-", "some_prefix_")
    # Group 2: The numeric part (e.g., "123")
    # Group 3: An optional short alphabetic suffix (0-4 chars, e.g., "a", "vr")
    final_format_match = re.match(r'^(.*?)(\d+)([a-z]{0,4})$', id_to_format, re.IGNORECASE)

    if final_format_match:
        raw_text_part = final_format_match.group(1)
        number_part_str = final_format_match.group(2)
        raw_suffix_part = final_format_match.group(3) if final_format_match.group(3) else ""

        formatted_text_part = raw_text_part.upper().replace('_', '')

        padded_number_part = number_part_str
        try:
            if formatted_text_part.startswith("FC2") and len(number_part_str) > 5:
                 padded_number_part = number_part_str
            else:
                 temp_num_str = number_part_str.lstrip('0')
                 if not temp_num_str: temp_num_str = "0"
                 if len(temp_num_str) <= 3 or (len(number_part_str) <=5 and len(temp_num_str) > 3) :
                     padded_number_part = temp_num_str.zfill(3)
                 else:
                     padded_number_part = temp_num_str
        except ValueError:
             padded_number_part = number_part_str.zfill(3)

        formatted_suffix_part = raw_suffix_part.upper()

        final_id_parts = []
        if formatted_text_part:
            # Remove trailing hyphen from text part if it's there, as we'll add one consistently
            # unless it's something like FC2 which doesn't use hyphens.
            if formatted_text_part.endswith('-') and not formatted_text_part.startswith("FC2"):
                final_id_parts.append(formatted_text_part[:-1])
            else:
                final_id_parts.append(formatted_text_part)

            # Add hyphen if text part exists and doesn't look like FC2 (which doesn't use hyphens)
            if not formatted_text_part.startswith("FC2"):
                final_id_parts.append('-')
        
        final_id_parts.append(padded_number_part)
        final_id_parts.append(formatted_suffix_part)

        formatted_id = "".join(final_id_parts)
        
        # Final cleanup: if it ended with a hyphen due to empty number/suffix and non-FC2 text part
        if formatted_id.endswith('-') and not formatted_text_part.startswith("FC2") and not (padded_number_part or formatted_suffix_part):
             formatted_id = formatted_id[:-1]


        logging.debug(f"[SANITIZE] Formatted ID: {formatted_id}")
        return formatted_id
    else:
        fallback_id = id_to_format.upper().replace('_','').replace('-','')
        if not fallback_id and '-' in id_to_format:
            parts = id_to_format.upper().split('-', 1)
            if len(parts) == 2 and parts[1].isdigit():
                num = parts[1].lstrip('0').zfill(3)
                fallback_id = f"{parts[0].replace('_','')}-{num}"
            elif len(parts) == 2 and re.match(r'^\d+[A-Z]{0,4}$', parts[1]):
                 num_suffix_match = re.match(r'^(\d+)([A-Z]{0,4})$', parts[1])
                 if num_suffix_match:
                     num = num_suffix_match.group(1).lstrip('0').zfill(3)
                     suf = num_suffix_match.group(2)
                     fallback_id = f"{parts[0].replace('_','')}-{num}{suf}"
        logging.debug(f"[SANITIZE] Final formatting pattern didn't match '{id_to_format}', using fallback: '{fallback_id if fallback_id else id_to_format.upper()}'")
        return fallback_id if fallback_id else id_to_format.upper()
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

# --- Helper function for Formatting Strings with Placeholders ---
def format_string_with_placeholders(pattern_string, data_dict, screenshot_index=None):
    """
    Replaces placeholders in a pattern string with values from data_dict.
    Available placeholders: {id}, {content_id}, {title}, {original_title},
                           {year}, {studio}, {original_filename_base}, {actress} or {actress:N}, {n} (for screenshots)
    """
    if not isinstance(pattern_string, str): return ""
    
    # Prepare base placeholder values (excluding 'actress' as it's handled specially)
    base_placeholders = {
        'id': str(data_dict.get('id', '')),
        'content_id': str(data_dict.get('content_id', '')),
        'title': str(data_dict.get('title', '')),
        'original_title': str(data_dict.get('original_title', '')),
        'year': str(data_dict.get('year', '')),
        'studio': str(data_dict.get('studio', '')),
        'original_filename_base': str(data_dict.get('original_filename_base', ''))
    }
    if screenshot_index is not None:
        base_placeholders['n'] = str(screenshot_index)

    formatted_string = pattern_string

    # Handle general placeholders first
    for key, value in base_placeholders.items():
        formatted_string = formatted_string.replace(f"{{{key}}}", value)

    # Special handling for {actress} or {actress:N}
    actresses_data_list = data_dict.get('actresses', []) 
    
    all_actress_names_from_data = []
    if actresses_data_list and isinstance(actresses_data_list, list):
        for actress_item_dict in actresses_data_list:
            if isinstance(actress_item_dict, dict) and 'name' in actress_item_dict:
                actress_name_str = str(actress_item_dict['name']).strip()
                if actress_name_str: 
                    all_actress_names_from_data.append(actress_name_str)

    def replace_actress_placeholder_match(match_obj):
        limit_specifier_str = match_obj.group(1) 
        
        names_to_include_list = []
        if not all_actress_names_from_data: 
            return ""

        if limit_specifier_str: # e.g., "3"
            if limit_specifier_str.isdigit():
                num_limit = int(limit_specifier_str)
                if num_limit > 0:
                    names_to_include_list = all_actress_names_from_data[:num_limit]
        else: 
            names_to_include_list = all_actress_names_from_data
        
        return ", ".join(names_to_include_list)

    formatted_string = re.sub(r'(?i)\{actress(?:[:]([\d]+))?\}', replace_actress_placeholder_match, formatted_string)
    
    return formatted_string

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

        # --- Check if enabled scrapers are actually used in priorities ---
    all_scrapers_in_priority_lists = set()
    for field_key in app_settings.PRIORITY_FIELDS_ORDERED: # Iterate through defined priority fields
        if field_key in field_priorities:
            all_scrapers_in_priority_lists.update(field_priorities[field_key])
    
    unused_enabled_scrapers = []
    for scraper_name in enabled_scrapers:
        if scraper_name not in all_scrapers_in_priority_lists:
            unused_enabled_scrapers.append(scraper_name)

    if unused_enabled_scrapers:
        warning_message = (
            f"Warning: The following enabled scraper(s) are not listed in any field's priority "
            f"order in Settings: **{', '.join(unused_enabled_scrapers)}**. "
            f"Please review your Field Priority settings."
        )
        st.warning(warning_message, icon="⚠️")
        logging.warning(f"Unused enabled scrapers found: {unused_enabled_scrapers}. They are not in any priority list.")
    # --- END CHECK ---

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

    # --- Helper function for running scraper tasks ---
    def execute_scraper_tasks(id_to_scrape, current_jl_ua, current_jl_cf, enabled_scrapers_list, max_workers_count, current_filename_base_for_status, current_progress_tuple_for_status):
        nonlocal javlibrary_globally_failed_this_run # Allow modification of the outer scope variable
        # No need to pass st or st.session_state, can access them directly if needed from outer scope.

        _scraper_results = {}
        _any_success = False
        _futures = []

        status_text.text(f"Processing: {current_filename_base_for_status} (ID: {id_to_scrape}) ({current_progress_tuple_for_status[0]}/{current_progress_tuple_for_status[1]}) - Running scrapers...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_count) as executor:
            for scraper_name_iter in enabled_scrapers_list:
                ua_for_jl_iter = current_jl_ua if scraper_name_iter == "Javlibrary" else None
                cf_for_jl_iter = current_jl_cf if scraper_name_iter == "Javlibrary" else None
                
                future_iter = executor.submit(run_single_scraper_task, scraper_name_iter, id_to_scrape,
                                            user_agent_for_javlibrary=ua_for_jl_iter,
                                            cf_token_for_javlibrary=cf_for_jl_iter)
                _futures.append(future_iter)
        
        status_text.text(f"Processing: {current_filename_base_for_status} (ID: {id_to_scrape}) ({current_progress_tuple_for_status[0]}/{current_progress_tuple_for_status[1]}) - Waiting for scrapers...")
        
        for future_iter_done in concurrent.futures.as_completed(_futures):
            try:
                name_res, data_res = future_iter_done.result()
                if name_res == "Javlibrary" and data_res == "CF_CHALLENGE":
                    st.error(f"Javlibrary credentials failed for ID '{id_to_scrape}' (Cloudflare Challenge). You will be prompted again on the next 'Run Crawlers' attempt if Javlibrary remains enabled.", icon="🚨")
                    st.session_state.javlibrary_creds_provided_this_session = False 
                    st.session_state.javlibrary_user_agent = None
                    st.session_state.javlibrary_cf_token = None
                    javlibrary_globally_failed_this_run = True # Set the global flag
                    
                    for f_to_cancel_iter in _futures: # Cancel other pending futures for this ID
                        if not f_to_cancel_iter.done():
                            f_to_cancel_iter.cancel()
                    break # Break from processing results for this ID as JavLib is critical path for this attempt

                if data_res and data_res != "CF_CHALLENGE":
                    _scraper_results[name_res] = data_res
                    _any_success = True
            except concurrent.futures.CancelledError:
                print(f"A scraper task was cancelled for {current_filename_base_for_status} (ID: {id_to_scrape}).")
            except Exception as exc_res:
                print(f"Error retrieving result from future for ID {id_to_scrape}: {exc_res}")
        
        return _scraper_results, _any_success
    # --- End Helper function ---


    with st.spinner(f"Processing {total_files} movie files..."):
        for i, filepath in enumerate(st.session_state.movie_file_paths):
            if javlibrary_globally_failed_this_run:
                status_text.text("Javlibrary credential failure. Halting further movie processing for this run.")
                break 

            filename_base = os.path.basename(filepath)
            raw_movie_id_from_filename = os.path.splitext(filename_base)[0]
            original_filename_base_for_nfo = raw_movie_id_from_filename
            
            sanitized_movie_id = sanitize_id_for_scraper(raw_movie_id_from_filename) 

            if not sanitized_movie_id: # If sanitize_id_for_scraper returns None or empty
                 st.warning(f"Could not derive a valid ID from filename '{filename_base}', skipping file.")
                 # skipped_manual_entry += 1 # Not a manual entry yet, just a skip.
                 progress_bar.progress((i + 1) / total_files)
                 continue

            scraper_results = {}
            any_scraper_succeeded_for_this_movie = False
            id_used_for_successful_scrape = None
            
            # --- ATTEMPT 1: Using Sanitized ID ---
            attempt1_results, attempt1_success = execute_scraper_tasks(
                sanitized_movie_id, current_jl_user_agent, current_jl_cf_token, enabled_scrapers, max_workers,
                filename_base, (i+1, total_files) 
            )
            
            if javlibrary_globally_failed_this_run: # Check immediately after helper returns
                progress_bar.progress((i + 1) / total_files)
                continue # Skip to next movie file if JavLib globally failed during this attempt

            if attempt1_success:
                scraper_results = attempt1_results
                any_scraper_succeeded_for_this_movie = True
                id_used_for_successful_scrape = sanitized_movie_id
            
            # --- ATTEMPT 2: Using Raw ID (if Sanitized ID failed, Raw ID is different, and no global JL fail) ---
            if not any_scraper_succeeded_for_this_movie and \
               raw_movie_id_from_filename.lower() != sanitized_movie_id.lower() and \
               not javlibrary_globally_failed_this_run: # Ensure no global failure before trying again

                attempt2_results, attempt2_success = execute_scraper_tasks(
                    raw_movie_id_from_filename, current_jl_user_agent, current_jl_cf_token, enabled_scrapers, max_workers,
                    filename_base, (i+1, total_files) 
                )

                if javlibrary_globally_failed_this_run: # Check again
                    progress_bar.progress((i + 1) / total_files)
                    continue 

                if attempt2_success:
                    scraper_results = attempt2_results
                    any_scraper_succeeded_for_this_movie = True
                    id_used_for_successful_scrape = raw_movie_id_from_filename
            
            # --- Merging and Translation (only if no global CF fail and some scraper succeeded) ---
            if not javlibrary_globally_failed_this_run and any_scraper_succeeded_for_this_movie:
                status_text.text(f"Processing: {filename_base} (ID: {id_used_for_successful_scrape}) ({i+1}/{total_files}) - Merging data...")
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
                        log_msg = (f"[GENRE_BLACKLIST] ID '{id_used_for_successful_scrape}': Removed {removed_count}. "
                                    f"Original: {original_genres_for_movie}, Filtered: {filtered_movie_genres}")
                        logging.info(log_msg) 
                    
                    merged_data['genres'] = filtered_movie_genres
                # --- GENRE BLACKLIST BLOCK ---


# --- Final Data Preparation ---
                merged_data['_original_filename_base'] = original_filename_base_for_nfo
                merged_data['id'] = id_used_for_successful_scrape # Use the ID that resulted in success
                merged_data['original_filepath'] = filepath
                merged_data['download_all'] = default_download_state
                merged_data['_field_sources'] = field_sources
                
# --- Apply Naming Conventions ---
                # 1. Prepare data for placeholder substitution
                base_title_for_patterns = merged_data.get('title') or merged_data.get('title_raw') or 'NO_TITLE'
                current_id_for_patterns = merged_data.get('id', 'NO_ID')
                
                semantic_title_for_patterns = base_title_for_patterns
                # Strip ID prefix if present (e.g., from Javlibrary title) for a 'cleaner' semantic title
                # This ensures {title} in patterns refers to the movie's actual title, not "ID - Title"
                temp_id_prefix_for_strip1 = f"[{current_id_for_patterns}]" # Check for [ID] Title
                temp_id_prefix_for_strip2 = f"{current_id_for_patterns} -" # Check for ID - Title
                
                if semantic_title_for_patterns.lower().startswith(temp_id_prefix_for_strip1.lower()):
                    semantic_title_for_patterns = semantic_title_for_patterns[len(temp_id_prefix_for_strip1):].lstrip(" -").strip()
                elif semantic_title_for_patterns.lower().startswith(temp_id_prefix_for_strip2.lower()):
                     # More robustly find where the title starts after "ID - "
                    match = re.match(re.escape(current_id_for_patterns) + r'\s*-\s*(.*)', semantic_title_for_patterns, re.IGNORECASE)
                    if match:
                        semantic_title_for_patterns = match.group(1).strip()
                
                if not semantic_title_for_patterns: semantic_title_for_patterns = 'NO_TITLE'

                actresses_list_for_pattern = merged_data.get('actresses', [])
                first_actress_name_for_pattern = ""
                if actresses_list_for_pattern and isinstance(actresses_list_for_pattern[0], dict):
                    first_actress_name_for_pattern = actresses_list_for_pattern[0].get('name', '')


                placeholder_data = {
                    'id': current_id_for_patterns,
                    'content_id': merged_data.get('content_id', current_id_for_patterns),
                    'title': semantic_title_for_patterns, 
                    'original_title': merged_data.get('originaltitle', ''), # originaltitle is usually from scraper directly
                    'year': str(merged_data.get('release_year', '')),
                    'studio': merged_data.get('maker', ''),
                    'original_filename_base': merged_data.get('_original_filename_base', ''),
                    'actresses': actresses_list_for_pattern # Pass the list for format_string_with_placeholders
                }

                # 2. Generate Folder Name using pattern
                folder_name_pattern_from_settings = st.session_state.get("naming_folder_name_pattern", app_settings.DEFAULT_NAMING_FOLDER_NAME_PATTERN)
                raw_folder_name = format_string_with_placeholders(folder_name_pattern_from_settings, placeholder_data)
                
                # Sanitize the raw pattern output first
                temp_folder_name = sanitize_filename(raw_folder_name) 
                
                final_folder_name_for_data = temp_folder_name # Default to non-truncated
                
                max_folder_len = 150 # This should ideally be a system-aware max path component length or a safe value
                
                if len(temp_folder_name) > max_folder_len:
                    # Perform truncation. The ellipsis is for visual representation if displayed,
                    # but sanitize_filename will ultimately clean it for path safety.
                    safe_truncate_point = max(0, max_folder_len - 3) # Ensure space for "..."
                    truncated_name_with_ellipsis = temp_folder_name[:safe_truncate_point] + "..."
                    
                    # Sanitize AGAIN after adding ellipsis. This is critical.
                    # This ensures "..." becomes "." and then is stripped by sanitize_filename's strip(' .')
                    final_folder_name_for_data = sanitize_filename(truncated_name_with_ellipsis)
                
                # Ensure there's a non-empty folder name after all sanitization
                if not final_folder_name_for_data:
                    # Fallback to a sanitized ID or a generic name if ID is also problematic
                    fallback_name = placeholder_data.get('id', 'movie_folder') # Use ID as a good fallback
                    if not fallback_name: fallback_name = 'movie_folder' # Absolute fallback if ID was empty
                    final_folder_name_for_data = sanitize_filename(fallback_name)
                    # If even the sanitized ID is empty (e.g. ID was just "."), use a hardcoded name
                    if not final_folder_name_for_data: final_folder_name_for_data = "untitled_movie" 

                merged_data['folder_name'] = final_folder_name_for_data
                
                # 3. Generate NFO Title using pattern (This part should be fine)
                nfo_title_pattern_from_settings = st.session_state.get("naming_nfo_title_pattern", app_settings.DEFAULT_NAMING_NFO_TITLE_PATTERN)
                merged_data['title'] = format_string_with_placeholders(nfo_title_pattern_from_settings, placeholder_data)
                
                # Ensure title_raw has a fallback.
                if 'title_raw' not in merged_data or not merged_data.get('title_raw'):
                    merged_data['title_raw'] = merged_data.get('originaltitle', semantic_title_for_patterns if semantic_title_for_patterns != 'NO_TITLE' else "")
                
                st.session_state.all_movie_data[filepath] = merged_data
                processed_files += 1
            elif not javlibrary_globally_failed_this_run: # No scraper succeeded (after all attempts), but also no global CF fail
                 # Use the sanitized_movie_id for manual entry consistency
                 id_for_manual_entry = sanitized_movie_id 
                 toast_msg = f"No data for '{filename_base}' (tried ID: '{sanitized_movie_id}'"
                 if raw_movie_id_from_filename.lower() != sanitized_movie_id.lower():
                     toast_msg += f" and raw ID: '{raw_movie_id_from_filename}'"
                 toast_msg += "). Manual entry."
                 st.toast(toast_msg, icon="✍️")
                 
                 manual_data = {
                     'id': id_for_manual_entry, 
                     'content_id': id_for_manual_entry, 
                     '_original_filename_base': original_filename_base_for_nfo,
                     'title': f"[{id_for_manual_entry}]", 
                     'title_raw': '', 'originaltitle': '', 'description': '',
                     'release_date': None, 'release_year': None, 'runtime': None,
                     'director': None, 'maker': None, 'label': None, 'series': None,
                     'genres': [], 'actresses': [], 'cover_url': None, 'screenshot_urls': [],
                     'rating': None, 'votes': None, 'set': None, 'url': None,
                     'source': 'manual',
                     'original_filepath': filepath,
                     'download_all': default_download_state,
                     '_field_sources': {},
                     'folder_name': format_and_truncate_folder_name(id_for_manual_entry, "", "")
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

    # --- Load Naming Patterns Once ---
    poster_filename_pattern = st.session_state.get("naming_poster_filename_pattern", app_settings.DEFAULT_NAMING_POSTER_FILENAME_PATTERN)
    folder_image_filename_pattern = st.session_state.get("naming_folder_image_filename_pattern", app_settings.DEFAULT_NAMING_FOLDER_IMAGE_FILENAME_PATTERN)
    screenshot_filename_pattern = st.session_state.get("naming_screenshot_filename_pattern", app_settings.DEFAULT_NAMING_SCREENSHOT_FILENAME_PATTERN)


    with st.spinner(f"Organizing {total_movies} movies..."):
        for i, (original_filepath, data) in enumerate(st.session_state.all_movie_data.items()):
            original_basename = os.path.basename(original_filepath)
            status_text.text(f"Organizing: {original_basename} ({i+1}/{total_movies})")
            download_all_flag = data.get('download_all', False)

            try:
                movie_id_for_logs = data.get('id', 'UNKNOWN_ID') # Standard ID for logging

                # Prepare placeholder data for filename formatting
                # Use the 'semantic' title (post-translation, pre-NFO pattern) for filenames
                # Reconstruct semantic title if needed (similar to process_input_dir_callback)
                base_title_for_filenames = data.get('title') # This is already NFO-patterned. We need pre-pattern.
                                                            # title_raw is also an option, or originaltitle
                                                            # Let's assume title_raw is the best "semantic" title before NFO formatting
                
                # To get the 'semantic' title for filenames, we might need to re-derive it
                # or ensure it's stored separately. For now, use title_raw as a proxy for semantic title.
                # A more robust way would be to store the semantic title explicitly during crawl.
                # Using title_raw which should be the pre-NFO-formatted title.
                
                # Re-derive semantic_title from title_raw or originaltitle for filename patterns
                # This semantic_title should be the movie's actual title, not prefixed by ID or patterns.
                # Let's use originaltitle as a safe bet for a clean title, or title_raw if originaltitle is empty.
                title_raw_from_data = data.get('title_raw', '')
                original_title_from_data = data.get('originaltitle', '')
                
                semantic_title_for_filenames = title_raw_from_data if title_raw_from_data else original_title_from_data
                if not semantic_title_for_filenames: # Fallback if both are empty
                    # Try to strip from current data['title'] if it's patterned like "[ID] Actual Title"
                    current_nfo_title = data.get('title', '')
                    id_from_data = data.get('id', '')
                    if id_from_data and current_nfo_title.startswith(f"[{id_from_data}]"):
                        semantic_title_for_filenames = current_nfo_title[len(id_from_data)+2:].strip()
                    elif id_from_data and re.match(re.escape(id_from_data) + r'\s*-\s*(.*)', current_nfo_title, re.IGNORECASE):
                        match_title_strip = re.match(re.escape(id_from_data) + r'\s*-\s*(.*)', current_nfo_title, re.IGNORECASE)
                        if match_title_strip: semantic_title_for_filenames = match_title_strip.group(1).strip()
                    else:
                        semantic_title_for_filenames = "NO_TITLE_FOR_FILENAME"


                actresses_list_for_filename = data.get('actresses', [])


                filename_placeholder_data = {
                    'id': data.get('id', ''),
                    'content_id': data.get('content_id', data.get('id', '')),
                    'title': semantic_title_for_filenames,
                    'original_title': data.get('originaltitle', ''),
                    'year': str(data.get('release_year', '')),
                    'studio': data.get('maker', ''),
                    'original_filename_base': data.get('_original_filename_base', ''),
                    'actresses': actresses_list_for_filename # Pass the list
                }


                if not os.path.exists(original_filepath):
                    st.toast(f"Skip: Original file '{original_basename}' not found.", icon="⚠️"); error_count += 1; continue

                # --- Determine Target Directory based on Mode ---
                if is_recursive_run:
                    target_dir = os.path.dirname(original_filepath)
                else:
                    folder_name_from_data = data.get('folder_name') # This is already pattern-generated and sanitized/truncated
                    if not folder_name_from_data: # Fallback if folder_name somehow missing
                         fb_id = data.get('id', 'NO_ID'); fb_studio = data.get('maker', ''); fb_title = data.get('title_raw', 'NO_TITLE_FB')
                         folder_name_from_data = sanitize_filename(f"{fb_id} {fb_studio} {fb_title}")

                    target_dir = os.path.join(global_output_dir, folder_name_from_data) # folder_name_from_data is already sanitized

                    crawl_input_dir = load_settings().get("input_dir", "")
                    if not crawl_input_dir: crawl_input_dir = st.session_state.get("input_dir", "")
                    abs_target_dir = os.path.abspath(target_dir)
                    abs_crawl_input_dir = os.path.abspath(crawl_input_dir) if crawl_input_dir else None
                    if abs_crawl_input_dir and abs_target_dir == abs_crawl_input_dir:
                         st.toast(f"Skip: Output folder '{folder_name_from_data}' is same as crawl Input Dir for '{original_basename}'.", icon="❗")
                         error_count += 1
                         continue
                os.makedirs(target_dir, exist_ok=True)

                # --- NFO Generation ---
                nfo_base_name_to_use = data.get('_original_filename_base', movie_id_for_logs)
                sanitized_nfo_filename_base = sanitize_filename(nfo_base_name_to_use)
                nfo_filename = f"{sanitized_nfo_filename_base}.nfo"
                nfo_path = os.path.join(target_dir, nfo_filename)
                generate_nfo(data, filename=nfo_path, download_all_flag=download_all_flag)
                processed_image_count_this_movie = 0

                def download_image(url, base_filename_pattern, current_target_dir, placeholder_data_for_img, source_page_url="", log_movie_id="UNKNOWN", screenshot_idx_for_pattern=None):
                    nonlocal processed_image_count_this_movie
                    if not url: return None
                    
                    # Format the base filename using the pattern and data
                    formatted_base_filename = format_string_with_placeholders(base_filename_pattern, placeholder_data_for_img, screenshot_index=screenshot_idx_for_pattern)
                    safe_base_filename = sanitize_filename(formatted_base_filename)
                    if not safe_base_filename: safe_base_filename = sanitize_filename(log_movie_id + ("_img" if screenshot_idx_for_pattern is None else f"_ss{screenshot_idx_for_pattern}"))


                    abs_url = urljoin(source_page_url, url); potential_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif'];
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
                    except requests.exceptions.Timeout: st.toast(f"DL Timeout: '{safe_base_filename}' for {log_movie_id}.", icon="⏱️")
                    except requests.exceptions.RequestException as e: st.toast(f"DL Fail: '{safe_base_filename}' for {log_movie_id} ({e}).", icon="❌")
                    except Exception as e: st.toast(f"DL Error: '{safe_base_filename}' for {log_movie_id} ({e}).", icon="💥")
                    return None

                source_url = data.get('url', ''); screenshot_urls = data.get('screenshot_urls', [])

                # --- Poster Download ---
                poster_url_to_download = data.get('poster_manual_url') or get_auto_poster_url(data)
                downloaded_poster_path = None
                if poster_url_to_download:
                    downloaded_poster_path = download_image(
                        poster_url_to_download, 
                        poster_filename_pattern, # Use pattern
                        target_dir, 
                        filename_placeholder_data, # Pass placeholder data
                        source_url, 
                        log_movie_id=movie_id_for_logs
                    )
                else:
                    print(f"[DEBUG ORGANIZE] No poster URL for {movie_id_for_logs}.")

                # --- Folder Image Generation ---
                if downloaded_poster_path and os.path.exists(downloaded_poster_path) and crop_script_exists:
                    poster_ext = os.path.splitext(downloaded_poster_path)[1]
                    # Format folder image filename using pattern
                    folder_img_base_name_formatted = format_string_with_placeholders(folder_image_filename_pattern, filename_placeholder_data)
                    folder_img_base_name_safe = sanitize_filename(folder_img_base_name_formatted)
                    if not folder_img_base_name_safe: folder_img_base_name_safe = sanitize_filename(movie_id_for_logs + "_folder_fallback")

                    folder_img_path = os.path.join(target_dir, f"{folder_img_base_name_safe}{poster_ext}") # Use poster's extension
                    
                    if not os.path.exists(folder_img_path):
                        try:
                            cmd = [sys.executable, crop_script_path, downloaded_poster_path, folder_img_path]
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

                # --- Screenshot Download ---
                if download_all_flag:
                    actual_poster_url_downloaded = poster_url_to_download
                    screenshots_to_process = [ss_url for ss_url in screenshot_urls if ss_url and ss_url != actual_poster_url_downloaded]
                    if screenshots_to_process: print(f"[DEBUG ORGANIZE] Downloading {len(screenshots_to_process)} screenshots to {target_dir}...")
                    for ss_idx, url_img in enumerate(screenshots_to_process):
                        download_image(
                            url_img, 
                            screenshot_filename_pattern, # Use pattern
                            target_dir, 
                            filename_placeholder_data, # Pass placeholder data
                            source_url, 
                            log_movie_id=movie_id_for_logs,
                            screenshot_idx_for_pattern=ss_idx + 1 # Pass index for {n}
                        )

                # --- Conditional Move Movie File ---
                if not is_recursive_run:
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
                    print(f"[DEBUG ORGANIZE RECURSIVE] Skipping move for '{original_basename}'. File remains in '{os.path.dirname(original_filepath)}'.")

                processed_count += 1
            except Exception as e:
                st.error(f"Unexpected error organizing '{original_basename}': {e}")
                logging.exception(f"Organizer loop error for {original_basename}") # Log traceback
                error_count += 1
            progress_bar.progress((i + 1) / total_movies)

    # --- End Main Loop ---
    status_text.text(f"Organization complete. Processed: {processed_count}. Errors: {error_count}. Skipped Moves (Non-Recursive): {skipped_move_count}.")
    if progress_bar: progress_bar.empty()
    if processed_count > 0: st.toast(f"💾 Successfully organized {processed_count} movies!", icon="🎉")
    elif error_count == 0 and skipped_move_count == 0 and total_movies > 0 and not is_recursive_run: st.toast("No movies needed organization (already done?).", icon="🤷")
    elif error_count == 0 and total_movies > 0 and is_recursive_run: st.toast("Finished placing NFO/images in existing folders.", icon="✅") 
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
    selected_scrapers_for_rescrape = st.session_state.get("rescrape_selected_scrapers", [])

    if not current_movie_key or current_movie_key not in st.session_state.all_movie_data:
        st.error("No movie selected or data not found for re-scraping.")
        return

    if not selected_scrapers_for_rescrape:
        st.error("Please select at least one scraper for re-scraping.")
        return

    scraper_url_map = {}
    for scraper_name in selected_scrapers_for_rescrape:
        if scraper_name not in SCRAPER_REGISTRY:
            st.error(f"Selected scraper '{scraper_name}' is not available.")
            return
        url_key = f"rescrape_url_{scraper_name}"
        rescrape_url = st.session_state.get(url_key, "").strip()
        if not rescrape_url:
            st.error(f"Please enter a URL for the selected scraper: {scraper_name}.")
            return
        scraper_url_map[scraper_name] = rescrape_url

    if "Javlibrary" in selected_scrapers_for_rescrape and JAVLIBRARY_AVAILABLE:
        if not st.session_state.get("javlibrary_creds_provided_this_session", False):
            st.session_state.show_javlibrary_prompt = True
            st.warning("Javlibrary selected for re-scrape. Please provide credentials via the prompt at the top of the page, then try re-scraping again.", icon="🔑")
            st.rerun()
            return

    status_placeholder = st.empty()
    status_placeholder.info(f"Re-scraping '{os.path.basename(current_movie_key)}' using {', '.join(selected_scrapers_for_rescrape)}...")

    scraped_data_from_all_rescrape_sources = {}
    any_rescrape_success = False
    javlibrary_failed_this_rescrape_attempt = False

    current_jl_user_agent = st.session_state.get("javlibrary_user_agent")
    current_jl_cf_token = st.session_state.get("javlibrary_cf_token")

    for scraper_name, url_to_scrape in scraper_url_map.items():
        status_placeholder.info(f"Re-crawling with {scraper_name}")
        scrape_func = SCRAPER_REGISTRY[scraper_name]['scrape']
        try:
            raw_data = None
            if scraper_name == "Javlibrary":
                raw_data = scrape_func(url_to_scrape, user_agent=current_jl_user_agent, cf_clearance_token=current_jl_cf_token)
            else:
                raw_data = scrape_func(url_to_scrape)

            if raw_data == "CF_CHALLENGE":
                st.error(f"Javlibrary credentials failed for re-scrape with {scraper_name} (Cloudflare Challenge). Please provide valid credentials and try again.", icon="🚨")
                st.session_state.javlibrary_creds_provided_this_session = False
                st.session_state.javlibrary_user_agent = None
                st.session_state.javlibrary_cf_token = None
                javlibrary_failed_this_rescrape_attempt = True
                break
            elif raw_data:
                raw_data.pop('folder_url', None)
                raw_data.pop('folder_image_constructed_url', None)
                scraped_data_from_all_rescrape_sources[scraper_name] = raw_data
                any_rescrape_success = True
                print(f"Successfully re-scraped data with {scraper_name} for {current_movie_key}")
            else:
                st.warning(f"Scraper '{scraper_name}' did not return any data from the URL: {url_to_scrape}")
        except Exception as e:
            st.error(f"Error during re-scrape with '{scraper_name}': {e}")
            logging.exception(f"Error re-scraping {current_movie_key} with {scraper_name} from {url_to_scrape}")

    if javlibrary_failed_this_rescrape_attempt:
        status_placeholder.empty()
        st.rerun()
        return

    if not any_rescrape_success:
        status_placeholder.empty()
        st.warning("No data was successfully re-scraped from any of the provided URLs/scrapers.")
        return

    status_placeholder.info("Re-scrape successful. Merging data...")
    current_settings_for_merge = load_settings()
    field_priorities_for_merge = current_settings_for_merge.get("field_priorities", {})
    merged_data, field_sources = merge_scraped_data(scraped_data_from_all_rescrape_sources, field_priorities_for_merge)

    if not merged_data:
        status_placeholder.empty()
        st.error("Failed to merge data from re-scrape. No data to update.")
        return

    original_movie_entry = st.session_state.all_movie_data[current_movie_key]
    processed_data_for_movie = {}

    processed_data_for_movie['_original_filename_base'] = original_movie_entry.get('_original_filename_base')
    processed_data_for_movie['original_filepath'] = original_movie_entry.get('original_filepath')
    default_dl_all_initial = app_settings.DEFAULT_DOWNLOAD_ALL_INITIAL_STATE if SETTINGS_LOADED else False
    processed_data_for_movie['download_all'] = original_movie_entry.get('download_all', default_dl_all_initial)
    processed_data_for_movie.update(merged_data)
    processed_data_for_movie['_field_sources'] = field_sources

    if 'id' not in processed_data_for_movie or not processed_data_for_movie.get('id'):
        processed_data_for_movie['id'] = original_movie_entry.get('id', sanitize_id_for_scraper(original_movie_entry.get('_original_filename_base','')))
    if 'content_id' not in processed_data_for_movie or not processed_data_for_movie.get('content_id'):
        processed_data_for_movie['content_id'] = processed_data_for_movie.get('id')

    translator_service = current_settings_for_merge.get("translator_service", "None")
    target_language = current_settings_for_merge.get("target_language", "")
    api_key_trans = current_settings_for_merge.get("api_key", "")
    translate_title_flag = current_settings_for_merge.get("translate_title", False)
    translate_desc_flag = current_settings_for_merge.get("translate_description", False)
    keep_orig_desc_flag = current_settings_for_merge.get("keep_original_description", False)
    translation_enabled = translator_service != "None"
    translation_possible_for_rescrape = True
    if translation_enabled:
        if not target_language: translation_possible_for_rescrape = False
        if translator_service in ["DeepL", "DeepSeek"] and not api_key_trans: translation_possible_for_rescrape = False

    if translation_enabled and translation_possible_for_rescrape:
        status_placeholder.info("Translating re-scraped data...")
        title_to_translate = processed_data_for_movie.get('title', '')
        desc_to_translate = processed_data_for_movie.get('description', '')

        if translate_title_flag and title_to_translate:
            translated_title = _run_translation_script(translator_service, title_to_translate, target_language, api_key_trans)
            if translated_title:
                processed_data_for_movie['title'] = translated_title

        if translate_desc_flag and desc_to_translate:
            translated_desc = _run_translation_script(translator_service, desc_to_translate, target_language, api_key_trans)
            if translated_desc:
                if keep_orig_desc_flag and desc_to_translate:
                    processed_data_for_movie['description'] = f"{translated_desc}\n\n{desc_to_translate}"
                else:
                    processed_data_for_movie['description'] = translated_desc

    status_placeholder.info("Applying genre blacklist...")
    current_genre_blacklist_lc = current_settings_for_merge.get("genre_blacklist", [])
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

    status_placeholder.info("Finalizing data...")
    
    # --- Apply Naming Conventions ---
    # 1. Prepare data for placeholder substitution
    base_title_for_patterns = processed_data_for_movie.get('title') or processed_data_for_movie.get('title_raw') or 'NO_TITLE'
    current_id_for_patterns = processed_data_for_movie.get('id', 'NO_ID')

    semantic_title_for_patterns = base_title_for_patterns
    temp_id_prefix_for_strip1 = f"[{current_id_for_patterns}]"
    temp_id_prefix_for_strip2 = f"{current_id_for_patterns} -"

    if semantic_title_for_patterns.lower().startswith(temp_id_prefix_for_strip1.lower()):
        semantic_title_for_patterns = semantic_title_for_patterns[len(temp_id_prefix_for_strip1):].lstrip(" -").strip()
    elif semantic_title_for_patterns.lower().startswith(temp_id_prefix_for_strip2.lower()):
        match = re.match(re.escape(current_id_for_patterns) + r'\s*-\s*(.*)', semantic_title_for_patterns, re.IGNORECASE)
        if match:
            semantic_title_for_patterns = match.group(1).strip()
    if not semantic_title_for_patterns: semantic_title_for_patterns = 'NO_TITLE'

    actresses_list_for_pattern_rescrape = processed_data_for_movie.get('actresses', [])
    # first_actress_name_for_pattern_rescrape handled by format_string_with_placeholders

    placeholder_data = {
        'id': current_id_for_patterns,
        'content_id': processed_data_for_movie.get('content_id', current_id_for_patterns),
        'title': semantic_title_for_patterns,
        'original_title': processed_data_for_movie.get('originaltitle', ''),
        'year': str(processed_data_for_movie.get('release_year', '')),
        'studio': processed_data_for_movie.get('maker', ''),
        'original_filename_base': processed_data_for_movie.get('_original_filename_base', ''),
        'actresses': actresses_list_for_pattern_rescrape # Pass the list
    }

    # 2. Generate Folder Name using pattern
    folder_name_pattern_from_settings = st.session_state.get("naming_folder_name_pattern", app_settings.DEFAULT_NAMING_FOLDER_NAME_PATTERN)
    raw_folder_name = format_string_with_placeholders(folder_name_pattern_from_settings, placeholder_data)

    # Sanitize the raw pattern output first
    temp_folder_name = sanitize_filename(raw_folder_name)

    final_folder_name_for_data = temp_folder_name # Default to non-truncated

    max_folder_len = 150

    if len(temp_folder_name) > max_folder_len:
        safe_truncate_point = max(0, max_folder_len - 3)
        truncated_name_with_ellipsis = temp_folder_name[:safe_truncate_point] + "..."
        final_folder_name_for_data = sanitize_filename(truncated_name_with_ellipsis)

    if not final_folder_name_for_data:
        fallback_name = placeholder_data.get('id', 'movie_folder')
        if not fallback_name: fallback_name = 'movie_folder'
        final_folder_name_for_data = sanitize_filename(fallback_name)
        if not final_folder_name_for_data: final_folder_name_for_data = "untitled_movie"
        
    processed_data_for_movie['folder_name'] = final_folder_name_for_data

    # 3. Generate NFO Title using pattern
    nfo_title_pattern_from_settings = st.session_state.get("naming_nfo_title_pattern", app_settings.DEFAULT_NAMING_NFO_TITLE_PATTERN)
    processed_data_for_movie['title'] = format_string_with_placeholders(nfo_title_pattern_from_settings, placeholder_data)

    # Ensure 'title_raw' is present
    if 'title_raw' not in processed_data_for_movie or not processed_data_for_movie.get('title_raw'):
        processed_data_for_movie['title_raw'] = processed_data_for_movie.get('originaltitle', semantic_title_for_patterns if semantic_title_for_patterns != 'NO_TITLE' else "")
    
    # Ensure 'originaltitle' (for NFO) has a value if possible
    if 'originaltitle' not in processed_data_for_movie or not processed_data_for_movie.get('originaltitle'):
        processed_data_for_movie['originaltitle'] = processed_data_for_movie.get('title_raw', '')

    st.session_state.all_movie_data[current_movie_key] = processed_data_for_movie

    status_placeholder.empty()
    st.toast(f"Successfully re-scraped and updated '{os.path.basename(current_movie_key)}' using {', '.join(selected_scrapers_for_rescrape)}!", icon="✅")

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
        available_scrapers_lower = {name.lower(): name for name in AVAILABLE_SCRAPER_NAMES}
        for field_key in app_settings.PRIORITY_FIELDS_ORDERED:
            input_key = f"priority_{field_key}"
            if input_key in st.session_state:
                priority_str = st.session_state[input_key].strip()
                user_priority_list = [s.strip() for s in priority_str.split(',') if s.strip()]
                validated_list = []
                for name in user_priority_list:
                    if name.lower() in available_scrapers_lower:
                        validated_list.append(available_scrapers_lower[name.lower()])
                new_priorities[field_key] = validated_list
            else:
                 new_priorities[field_key] = st.session_state.field_priorities.get(field_key, [])
        st.session_state.field_priorities = new_priorities
        print(f"Updated field_priorities: {st.session_state.field_priorities}")
    except Exception as e:
         st.error(f"Error processing field priorities: {e}"); return

    # Update Naming Convention Patterns from UI inputs
    st.session_state.naming_poster_filename_pattern = st.session_state.get("ui_naming_poster_filename_pattern", app_settings.DEFAULT_NAMING_POSTER_FILENAME_PATTERN)
    st.session_state.naming_folder_image_filename_pattern = st.session_state.get("ui_naming_folder_image_filename_pattern", app_settings.DEFAULT_NAMING_FOLDER_IMAGE_FILENAME_PATTERN)
    st.session_state.naming_screenshot_filename_pattern = st.session_state.get("ui_naming_screenshot_filename_pattern", app_settings.DEFAULT_NAMING_SCREENSHOT_FILENAME_PATTERN)
    st.session_state.naming_nfo_title_pattern = st.session_state.get("ui_naming_nfo_title_pattern", app_settings.DEFAULT_NAMING_NFO_TITLE_PATTERN)
    st.session_state.naming_folder_name_pattern = st.session_state.get("ui_naming_folder_name_pattern", app_settings.DEFAULT_NAMING_FOLDER_NAME_PATTERN)
    print(f"Updated NFO title pattern: {st.session_state.naming_nfo_title_pattern}")
    print(f"Updated Folder name pattern: {st.session_state.naming_folder_name_pattern}")
    print(f"Updated Poster filename pattern: {st.session_state.naming_poster_filename_pattern}")


    # Directories are now directly updated in session state via shared keys
    print(f"Input directory state: {st.session_state.input_dir}")
    print(f"Output directory state: {st.session_state.output_dir}")

    # --- Update Translation Settings in Session State (Unchanged) ---
    print(f"Translator service: {st.session_state.translator_service}")
    print(f"Target language: {st.session_state.target_language}")
    print(f"Translate Title: {st.session_state.translate_title}")
    print(f"Translate Description: {st.session_state.translate_description}")
    print(f"Keep Original Desc: {st.session_state.keep_original_description}")

    # --- GENRE BLACKLIST ---
    if "ui_genre_blacklist_input_settings" in st.session_state:
        blacklist_input_str = st.session_state.ui_genre_blacklist_input_settings
        if isinstance(blacklist_input_str, str) and blacklist_input_str.strip():
            parsed_blacklist = [genre.strip().lower() for genre in blacklist_input_str.split(',') if genre.strip()]
            st.session_state.genre_blacklist = sorted(list(set(parsed_blacklist)))
        else: 
            st.session_state.genre_blacklist = [] 
        print(f"Updated st.session_state.genre_blacklist from UI: {st.session_state.genre_blacklist}")
    elif "genre_blacklist" not in st.session_state:
         st.session_state.genre_blacklist = []
         print("Warning: 'ui_genre_blacklist_input_settings' not in st.session_state, initialized genre_blacklist to empty.")

    save_settings_to_file()

# --- Javlibrary Credentials Dialog Function ---
@st.dialog(title="Javlibrary Credentials Required", width="large")
def javlibrary_credentials_dialog():
    st.caption(
        "Javlibrary scraper is enabled. Please provide your current browser **User-Agent** string "
        "and a valid **`cf_clearance` cookie value** from `javlibrary.com`. "
        "You can typically find the User-Agent by searching 'what is my user agent' in your browser, "
        "and the `cf_clearance` cookie in your browser's developer tools (Application/Storage -> Cookies) "
        "after successfully solving a challenge on their site."
    )
    
    jl_user_agent_input_val = st.text_input(
        "Your Browser User-Agent:",
        key="jl_user_agent_input_dialog", 
        placeholder="e.g., Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
        value=st.session_state.get("javlibrary_user_agent", "") 
    )
    jl_cf_token_input_val = st.text_input(
        "CF Clearance Token (from javlibrary.com cookie):",
        key="jl_cf_token_input_dialog", 
        value=st.session_state.get("javlibrary_cf_token", "") 
    )

    if st.button("Save Javlibrary Credentials for this Session", key="save_jl_creds_dialog_button"):
        if jl_user_agent_input_val and jl_user_agent_input_val.strip() and \
           jl_cf_token_input_val and jl_cf_token_input_val.strip():
            
            st.session_state.javlibrary_user_agent = jl_user_agent_input_val.strip()
            st.session_state.javlibrary_cf_token = jl_cf_token_input_val.strip()
            st.session_state.show_javlibrary_prompt = False 
            st.session_state.javlibrary_creds_provided_this_session = True 
            
            st.toast("Javlibrary credentials received. Dialog will close.", icon="✅")
            st.rerun() 
        else:
            st.error("Both User-Agent and CF Clearance Token are required for Javlibrary.", icon="🚫")
            st.session_state.javlibrary_creds_provided_this_session = False
# --- End Javlibrary Credentials Dialog Function ---

# --- Re-Scrape Dialog Function ---
@st.dialog(title="Re-Scrape with Specific URL", width="large")
def rescrape_dialog():
    st.caption("If the initial scrape was incorrect, select scraper(s), provide the correct URL(s) to the movie's page(s), and fetch new data. This will replace the current movie's metadata.")

    # Ensure the session state key for selected scrapers is initialized if it doesn't exist
    if "rescrape_selected_scrapers" not in st.session_state:
        st.session_state.rescrape_selected_scrapers = []
    # For URL inputs, ensure they are initialized dynamically within the loop if not present

    st.multiselect(
        "Select Scraper(s):",
        options=AVAILABLE_SCRAPER_NAMES,
        key="rescrape_selected_scrapers", # Streamlit uses the value from session_state if key exists
        help="Choose the scraper(s) corresponding to the URL(s) you will provide."
    )

    selected_scrapers_for_urls = st.session_state.get("rescrape_selected_scrapers", [])
    all_urls_provided = True
    if not selected_scrapers_for_urls:
        all_urls_provided = False

    for scraper_name in selected_scrapers_for_urls:
        url_input_key = f"rescrape_url_{scraper_name}"
        if url_input_key not in st.session_state: # Initialize if new scraper selected
             st.session_state[url_input_key] = ""

        st.text_input(
            f"URL for {scraper_name}:",
            key=url_input_key,
            placeholder=f"e.g., https://www.{scraper_name.lower()}.com/...",
            help=f"Paste the direct URL to the movie's page on {scraper_name}'s site."
        )
        if not st.session_state.get(url_input_key, "").strip():
            all_urls_provided = False

    col_action, col_cancel = st.columns(2)
    with col_action:
        if st.button(
            "Manual Re-Crawl",
            disabled=(not selected_scrapers_for_urls or not all_urls_provided or not AVAILABLE_SCRAPER_NAMES),
            use_container_width=True
        ):
            st.session_state.show_rescrape_dialog_actual = False # Mark dialog for closure *before* callback
            rescrape_with_url_callback()
            # If the callback (e.g. JavLib prompt) didn't already trigger a rerun,
            # we need one here to close the dialog and refresh the main page.
            if not st.session_state.get("show_javlibrary_prompt", False):
                 st.rerun()
# --- End Re-Scrape Dialog Function ---

# --- End Save Settings Callback ---

# --- Main Page Content ---
def show_crawler_page():
    st.markdown("<h1 style='padding-top: 0px; margin-top: 0px;'>🎬 JavOrganizer</h1>", unsafe_allow_html=True)

# --- Javlibrary Credentials Prompt UI (Updated condition) ---
    if st.session_state.get("show_javlibrary_prompt") and \
       (("Javlibrary" in st.session_state.get("enabled_scrapers", [])) or \
        ("Javlibrary" in st.session_state.get("rescrape_selected_scrapers", []))) and \
       JAVLIBRARY_AVAILABLE:
        javlibrary_credentials_dialog()

    # --- Inputs: Directories ---
    col_in, col_out = st.columns(2)

    latest_defaults_for_placeholder = load_settings()
    default_input_placeholder_path = latest_defaults_for_placeholder.get("input_dir", "")
    default_output_placeholder_path = latest_defaults_for_placeholder.get("output_dir", "")
    input_placeholder = f"Default: {default_input_placeholder_path}" if default_input_placeholder_path else "Enter path..."
    output_placeholder = f"Default: {default_output_placeholder_path}" if default_output_placeholder_path else "Enter path..."

    with col_in:
        with st.form("input_dir_form_crawler_page"):
            st.text_input(
                "Input Directory",
                key="input_dir",
                help="Folder containing movie files (e.g., ABCD-123.mp4). Set default in Settings.",
                placeholder=input_placeholder
            )
            col_btn, col_cb = st.columns([1.5, 1]) 
            with col_btn:
                submitted_input = st.form_submit_button("Run Crawlers")
            with col_cb:
                if "recursive_scan_active" not in st.session_state: st.session_state.recursive_scan_active = False
                st.checkbox("Recursive Scan", key="recursive_scan_active", value=st.session_state.recursive_scan_active,
                            help="Scans Input Directory and all subfolders. Save & Organize will use existing folders as basis.")
            if submitted_input:
                process_input_dir_callback()

    with col_out:
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
                disabled=output_dir_disabled
            )
            if output_dir_disabled:
                st.caption("Output Directory ignored because last crawl used 'Recursive Scan'. Output will be placed next to original files.")
            organize_button_label = "Save & Organize" + (" (Recursive Mode)" if st.session_state.get("last_crawl_was_recursive", False) else "")
            submitted_output = st.form_submit_button(organize_button_label)
            if submitted_output: organize_all_callback()

# --- View Rendering (based on crawler_view state) ---
    if st.session_state.crawler_view == "Editor":
        # --- Movie Selection & Navigation ---
        if st.session_state.all_movie_data:
            valid_keys = [fp for fp in st.session_state.all_movie_data.keys() if fp]
            if valid_keys:
                is_recursive_display = st.session_state.get("last_crawl_was_recursive", False)
                movie_options = {fp: (fp if is_recursive_display else os.path.basename(fp)) for fp in valid_keys}

                if st.session_state.current_movie_key not in movie_options:
                    st.session_state.current_movie_key = valid_keys[0] if valid_keys else None
                    if st.session_state.current_movie_key: st.session_state._apply_changes_triggered = False

                current_index = 0
                if st.session_state.current_movie_key:
                    try: current_index = valid_keys.index(st.session_state.current_movie_key)
                    except ValueError:
                        st.session_state.current_movie_key = valid_keys[0] if valid_keys else None
                        current_index = 0
                        if st.session_state.current_movie_key: st.session_state._apply_changes_triggered = False
                
                if "temp_show_screenshots_for_current_movie" not in st.session_state:
                    st.session_state.temp_show_screenshots_for_current_movie = False

                nav_col_prev, nav_col_next, nav_col_counter, nav_col_dropdown, nav_col_rescrape = st.columns([1, 1, 0.8, 3, 1.5]) 
                with nav_col_prev: 
                    st.button("Previous", on_click=go_previous_movie, disabled=(current_index == 0 or not st.session_state.current_movie_key), use_container_width=True)
                with nav_col_next: 
                    st.button("Next", on_click=go_next_movie, disabled=(current_index >= len(valid_keys) - 1 or not st.session_state.current_movie_key), use_container_width=True)
                with nav_col_counter:
                    if valid_keys:
                        st.markdown(
                            f"<div style='text-align: center; margin-top: 8px; font-size: 0.9em;'>{current_index + 1} / {len(valid_keys)}</div>", 
                            unsafe_allow_html=True
                        )
                def update_current_movie_selection():
                    st.session_state.current_movie_key = st.session_state.movie_selector
                    st.session_state._apply_changes_triggered = False 
                    st.session_state.temp_show_screenshots_for_current_movie = False 

                with nav_col_dropdown: 
                    st.selectbox("Select Movie:",
                                 options=valid_keys,
                                 format_func=lambda fp: movie_options.get(fp, "Unknown File"),
                                 key="movie_selector",
                                 index=current_index,
                                 on_change=update_current_movie_selection, 
                                 label_visibility="collapsed",
                                 disabled=(not valid_keys))
                with nav_col_rescrape: 
                    if st.button("Manual Re-Crawl", key="open_rescrape_dialog_nav_button", use_container_width=True): 
                        if st.session_state.current_movie_key and st.session_state.current_movie_key in st.session_state.all_movie_data:
                            st.session_state.show_rescrape_dialog_actual = True
                            st.rerun()
                        else:
                            st.toast("Please select a movie first.", icon="ℹ️")
                if st.session_state.current_movie_key: 
                    data = st.session_state.all_movie_data.get(st.session_state.current_movie_key, {})
                    field_sources = data.get('_field_sources', {}) 
                    if field_sources: 
                        contributing_scrapers = sorted(list(set(field_sources.values())))
                        if contributing_scrapers: st.caption(f"**Sources:** {', '.join([f'**`{s}`**' for s in contributing_scrapers])}")
                    elif data.get('source') == 'manual': st.caption("**Source:** Manual Entry (No scrapers found data)")
            else:
                st.warning("Movie data dictionary is empty or invalid.")
        elif st.session_state.movie_file_paths:
            st.warning("Processed input directory, but no data could be scraped.")
        else:
            st.info("Enter an Input Directory above and click 'Run Crawlers'.")

        if 'show_rescrape_dialog_actual' not in st.session_state: 
            st.session_state.show_rescrape_dialog_actual = False
        if st.session_state.get("show_rescrape_dialog_actual"):
            rescrape_dialog() 

        # --- Editor Form ---
        if st.session_state.current_movie_key and st.session_state.current_movie_key in st.session_state.all_movie_data:
            apply_changes_was_triggered = st.session_state.get('_apply_changes_triggered', False)
            if apply_changes_was_triggered:
                st.session_state._apply_changes_triggered = False
            else:
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
                auto_poster_url = get_auto_poster_url(data)
                default_poster_input_url = data.get('poster_manual_url');
                if default_poster_input_url is None: default_poster_input_url = auto_poster_url or ''
                st.session_state.editor_poster_url = to_str(default_poster_input_url)
                st.session_state._original_editor_poster_url = st.session_state.editor_poster_url
            
            with st.form(key="editor_form"):
                img_col, text_col = st.columns([1.2, 2])
                with img_col:
                    display_poster_url_from_editor_field = st.session_state.get('editor_poster_url', '') 
                    current_movie_data_for_poster = st.session_state.all_movie_data.get(st.session_state.current_movie_key, {})
                    source_page_url_for_poster_referer = current_movie_data_for_poster.get('url', '') 
                    if display_poster_url_from_editor_field:
                        try:
                            abs_display_poster_url = urljoin(source_page_url_for_poster_referer, display_poster_url_from_editor_field)
                            # Directly use st.image with the URL
                            source_lower = current_movie_data_for_poster.get('source', '').lower()
                            if source_lower.startswith('r18') or source_lower.startswith('mgs') or source_lower == 'manual':
                                st.image(abs_display_poster_url, caption="Poster Preview")
                            else:
                                st.image(abs_display_poster_url, use_container_width=True, caption="Poster Preview")
                        except Exception as img_e: # Catch potential errors from st.image (e.g., network, invalid URL)
                            st.warning(f"Could not load poster preview: {img_e}")
                    else:
                        st.info("No poster image URL provided. Add one below.")

                with text_col:
                    id_col1, id_col2 = st.columns(2);
                    with id_col1: st.text_input("ID", key="editor_id")
                    with id_col2: st.text_input("Content ID", key="editor_content_id")
                    st.text_input("Folder Name", key="editor_folder_name")
                    st.text_input("Title", key="editor_title")
                    st.text_input("Original Title", key="editor_original_title")
                    st.text_area("Description / Plot", height=120, key="editor_desc")
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
                        st.text_input("Genres", key="editor_genres");
                        st.text_input("Actresses", key="editor_actresses")
                    st.text_input("Cover", key="editor_poster_url")
                    apply_changes_submitted = st.form_submit_button(
                        "🖊️ Apply Changes",
                        on_click=apply_changes_callback 
                    )
            
            data = st.session_state.all_movie_data.get(st.session_state.current_movie_key, {}) 
            checkbox_key = f"cb_download_all_{st.session_state.current_movie_key}"
            st.checkbox( "Download all images for this movie",
                         value=data.get('download_all', False),
                         key=checkbox_key,
                         on_change=update_download_all_flag,
                         help="Downloads fanart (poster) and images. Folder image is always generated from fanart.")

            global_show_screenshots = st.session_state.get("editor_show_screenshots", True)
            temp_show_screenshots = st.session_state.get("temp_show_screenshots_for_current_movie", False)
            
            show_screenshots_for_this_movie = global_show_screenshots or temp_show_screenshots

            if not global_show_screenshots:
                st.checkbox(
                    "Show additional images",
                    value=temp_show_screenshots, 
                    key="temp_show_screenshots_for_current_movie", 
                    help="Temporarily display additional images."
                )

            if show_screenshots_for_this_movie:
                screenshots = data.get('screenshot_urls', [])
                source_page_url_for_ss_referer = data.get('url', '') 

                if screenshots:
                    auto_poster_url_display = get_auto_poster_url(data)
                    actual_poster_url_displayed = data.get('poster_manual_url', auto_poster_url_display)
                    
                    screenshots_to_display = [
                        ss_url for ss_url in screenshots 
                        if ss_url and ss_url != actual_poster_url_displayed 
                    ]

                    if screenshots_to_display:
                        num_screenshots = len(screenshots_to_display)
                        num_cols = min(num_screenshots, 4) 
                        
                        if num_cols > 0:
                            cols_imgs = st.columns(num_cols)
                            field_sources = data.get('_field_sources', {})
                            screenshots_list_source = field_sources.get('screenshot_urls')
                            overall_source = data.get('source', '').lower()
                            no_stretch = False 
                            if screenshots_list_source in ['r18dev', 'r18dev Ja']: no_stretch = True
                            elif overall_source == 'mgs': no_stretch = True
                            elif screenshots_list_source is None and overall_source.startswith('r18'): no_stretch = True
                            elif overall_source == 'manual': no_stretch = True

                            for idx, img_url_relative in enumerate(screenshots_to_display):
                                 with cols_imgs[idx % num_cols]:
                                     try:
                                         abs_ss_url = urljoin(source_page_url_for_ss_referer, img_url_relative)
                                         if no_stretch:
                                             st.image(abs_ss_url, caption=f"Image {idx+1}")
                                         else:
                                             st.image(abs_ss_url, use_container_width=True, caption=f"Image {idx+1}")
                                     except Exception as ss_e: 
                                         st.warning(f"Image {idx+1} ({os.path.basename(img_url_relative)}) error: {ss_e}")
                    elif 'screenshot_urls' in data and not data['screenshot_urls']:
                         if data.get('poster_manual_url') or data.get('cover_url'):
                             st.info("Additional images list is empty. This could be due to a manual Poster URL change, no scraped screenshots, or if the poster was the only image.")
                         else: st.info("No images (poster or screenshots) available for this movie.")
                    else: 
                        st.info("No screenshot data found for this movie.")

                elif 'screenshot_urls' in data and not data['screenshot_urls']:
                     if data.get('poster_manual_url') or data.get('cover_url'):
                         st.info("Screenshots list is empty. This could be due to a manual Poster URL change, no scraped screenshots, or if the poster was the only image.")
                     else: st.info("No images (poster or screenshots) available for this movie.")
                else: 
                    st.info("No screenshot information available for this movie.")

            elif not global_show_screenshots and not temp_show_screenshots: 
                st.info("Additional images display is turned off in Settings. Toggle above to see them.")
        # --- End Editor Form conditional block ---

    elif st.session_state.crawler_view == "Raw Data":
        st.subheader("Processed Movie Data")
        if st.session_state.current_movie_key and st.session_state.current_movie_key in st.session_state.all_movie_data:
            current_movie_data = st.session_state.all_movie_data[st.session_state.current_movie_key]
            display_key_name = (st.session_state.current_movie_key
                                if st.session_state.get("last_crawl_was_recursive", False)
                                else os.path.basename(st.session_state.current_movie_key))
            st.caption(f"Displaying processed data for: {display_key_name}")
            display_data = current_movie_data.copy()
            display_data.pop('folder_url', None)
            display_data.pop('folder_image_constructed_url', None)
            display_data.pop('folder_manual_url', None) 
            st.json(display_data, expanded=True)
        elif st.session_state.all_movie_data:
             st.info("Select a movie in the 'Editor' view to see its processed data here.")
        else:
            st.info("No data processed yet. Use 'Run Crawlers' first.")
    # --- End View Rendering ---

# --- Settings Page ---
def show_settings_page():
    sync_settings_from_file_to_state()
    st.markdown("<h1 style='padding-top: 0px; margin-top: 0px;'>⚙️ Settings</h1>", unsafe_allow_html=True)

    with st.form("settings_form"):

        # Enabled Scrapers
        st.subheader("Enabled Scrapers")
        st.caption("Select which scrapers to run when 'Run Crawlers' is clicked.")
        for scraper_name in AVAILABLE_SCRAPER_NAMES:
            specific_help = None 
            if scraper_name == "Javlibrary":
                specific_help = "Requires providing User-Agent and CF Clearance token when prompted on the Crawler page."
            elif scraper_name == "Mgs":
                specific_help = "May require a Japanese IP address."
            st.checkbox(scraper_name,
                         key=f"enable_{scraper_name}",
                         value=(scraper_name in st.session_state.get('enabled_scrapers', [])),
                         help=specific_help
                         )
            
        st.divider()

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
                            field_key, display_label = ordered_fields_with_labels[field_idx]
                            current_priority_list = st.session_state.field_priorities.get(field_key, [])
                            st.text_input(
                                label=display_label,
                                key=f"priority_{field_key}",
                                value=", ".join(current_priority_list)
                            )
                            field_idx += 1
                        else: break
        else:
             st.warning("Field priorities not found in session state or settings.")

        st.divider()

        st.subheader("Genre Blacklist")
        st.caption("Enter genres to exclude, separated by commas (e.g., Short, Parody, Featured). This is case-insensitive.")
        
        current_blacklist_display_str = ", ".join(st.session_state.get("genre_blacklist", []))
        st.text_area(
            "Blacklisted Genres:",
            key="ui_genre_blacklist_input_settings", 
            value=current_blacklist_display_str,
            height=100
        )

        st.divider()

        st.subheader("Naming Conventions")
        naming_placeholders_help = (
            "Available placeholders: `{id}`, `{content_id}`, `{title}` (semantic, post-translation), "
            "`{original_title}`, `{year}`, `{studio}` (maker), "
            "`{actress}` (all actress names, comma-separated), or `{actress:N}` (first N names), "
            "`{original_filename_base}` (video filename without ext), "
            "`{n}` (screenshot index, 1-based)."
        )
        st.caption(naming_placeholders_help)

        naming_col1, naming_col2 = st.columns(2)
        with naming_col1:
            st.text_input("Folder Name Pattern", key="ui_naming_folder_name_pattern", value=st.session_state.naming_folder_name_pattern)
            st.text_input("Title Pattern", key="ui_naming_nfo_title_pattern", value=st.session_state.naming_nfo_title_pattern)
            st.text_input("Poster Filename Pattern", key="ui_naming_poster_filename_pattern", value=st.session_state.naming_poster_filename_pattern)
        with naming_col2:
            st.text_input("Folder Image Filename Pattern", key="ui_naming_folder_image_filename_pattern", value=st.session_state.naming_folder_image_filename_pattern)
            st.text_input("Screenshot Filename Pattern", key="ui_naming_screenshot_filename_pattern", value=st.session_state.naming_screenshot_filename_pattern)


        st.divider()

        st.subheader("Translation")
        translator_options = ["None", "Google", "DeepL", "DeepSeek"]
        
        # Row 1 for main translation inputs
        trans_row1_col1, trans_row1_col2, _ = st.columns(3) # Third column is unused to control width
        with trans_row1_col1:
            st.selectbox("Translator Service", options=translator_options, key="translator_service")
            st.text_input("API Key", key="api_key", type="password", help="Required for DeepL and DeepSeek services.")
        with trans_row1_col2:
            st.text_input("Target Language Code", key="target_language", help="e.g., EN, DE, FR. Check service documentation.")

        # Row 2 for translation option checkboxes
        # These columns will also be 1/3 width each, aligning with the inputs above.
        trans_row2_col1, trans_row2_col2, _ = st.columns(3) # Third column unused
        with trans_row2_col1:
            st.checkbox("Translate Title", key="translate_title") 
        with trans_row2_col2:
            st.checkbox("Translate Description", key="translate_description")
            st.checkbox("Keep Original Description", key="keep_original_description", help="If 'Translate Description' is also checked, appends translation below original text.")

        st.divider()

        st.subheader("Additional Images") # Or a more appropriate subheader
        st.checkbox(
            "Show additional images in Editor view",
            key="editor_show_screenshots", # Uses the value from session_state if key exists
            help="If unchecked, additional images will not be displayed in the movie editor"
        )

        st.divider()

        st.subheader("Directories")
        # Input and Output Directory next to each other, taking full width of their columns
        dir_col1, dir_col2 = st.columns(2)
        with dir_col1:
            st.text_input("Default Input Directory", key="input_dir")
        with dir_col2:
            st.text_input("Default Output Directory", key="output_dir")

        # Save button
        save_button = st.form_submit_button("💾 Save All Settings", use_container_width=True, on_click=save_settings_callback)

# --- End Settings Page ---

# --- Sidebar ---
pg = st.navigation(
    [
        st.Page(show_crawler_page, title="🎬 Crawler", default=True), # Set one as default
        st.Page(show_settings_page, title="⚙️ Settings"),
    ]
)

if 'active_page_func_name' not in st.session_state:
    # Set a default based on which st.Page is 'default=True'
    st.session_state.active_page_func_name = show_crawler_page.__name__

if st.session_state.get("active_page_func_name") == show_crawler_page.__name__:
    crawler_view_options = ["Editor", "Raw Data"]
    current_crawler_view_index = 0
    if 'crawler_view' in st.session_state:
         try: current_crawler_view_index = crawler_view_options.index(st.session_state.crawler_view)
         except ValueError: current_crawler_view_index = 0 # Default to Editor
    st.sidebar.radio( 
        "View Mode", 
        options=crawler_view_options, 
        key="crawler_view", # This key is used by show_crawler_page
        index=current_crawler_view_index,
        # label_visibility="collapsed" # If you prefer no explicit "View Mode" label
    )

pg.run()
# --- End Sidebar ---
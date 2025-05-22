# settings.py - Default application settings
import collections # Import needed for OrderedDict if used later

# --- Scrapers ---
# Add the new scraper to the defaults
DEFAULT_ENABLED_SCRAPERS = ["Dmm", "r18dev", "Mgs"] # Example: Enable all by default

# --- Image Downloads ---
DEFAULT_DOWNLOAD_ALL_INITIAL_STATE = False

# --- Directories ---
DEFAULT_INPUT_DIRECTORY = ""
DEFAULT_OUTPUT_DIRECTORY = ""

# --- Translation ---
DEFAULT_TRANSLATOR_SERVICE = "None" # Options: "None", "Google", "DeepL", "DeepSeek"
DEFAULT_TARGET_LANGUAGE = ""      # e.g., "EN", "DE", "FR"
DEFAULT_API_KEY = ""
DEFAULT_TRANSLATE_TITLE = False
DEFAULT_TRANSLATE_DESCRIPTION = False
DEFAULT_KEEP_ORIGINAL_DESCRIPTION = False

# --- Genre Blacklist ---
DEFAULT_GENRE_BLACKLIST = [
        "featured actress",
        "female porn star",
        "digital mosaic",
        "actress best compilation"
    ]

# --- Field Priorities ---
# Default order of scrapers to try for obtaining each field's value.
# Added "R18.Dev JA" - adjust its position based on desired preference.
# Example: Place R18.Dev JA after R18.Dev for most fields, but prioritize it for originaltitle?
DEFAULT_FIELD_PRIORITIES = {
    # Order within this dict doesn't strictly matter, ORDERED_PRIORITY_FIELDS below controls UI order
    'id':          ['Dmm', 'r18dev', 'Mgs'], # ID is usually language independent
    'content_id':  ['Dmm', 'r18dev', 'Mgs'], # Usually language independent
    'title':       ['Dmm', 'Mgs', 'r18dev'], # Prefers EN/other sources first generally
    'originaltitle':['Dmm', 'Mgs', 'r18dev'], # PRIORITIZE JA scraper for original title
    'description': ['Dmm', 'Mgs', 'r18dev'], # Usually prefer translated/EN description
    'release_date':['r18dev', 'Dmm', 'Mgs'],
    'release_year':['r18dev', 'Dmm', 'Mgs'],
    'runtime':     ['r18dev', 'Dmm', 'Mgs'],
    'director':    ['r18dev', 'Dmm', 'Mgs'], # Prefers EN/other sources first generally
    'maker':       ['r18dev', 'Dmm', 'Mgs'], # Studio
    'label':       ['r18dev', 'Dmm', 'Mgs'],
    'series':      ['r18dev', 'Dmm', 'Mgs'],
    'genres':      ['r18dev', 'Dmm', 'Mgs'], # Get EN genres first usually
    'actresses':   ['r18dev', 'Dmm', 'Mgs'], # Prefers Romaji generally
    'cover_url':   ['r18dev', 'Dmm', 'Mgs'], # URLs are agnostic
    # 'folder_image_constructed_url': ['DMM', 'MGS', 'R18.Dev', 'R18.Dev JA'], # URLs are agnostic
    'screenshot_urls': ['Dmm', 'Mgs', 'r18dev'], # URLs are agnostic
}

# List of fields managed by the priority setting AND their desired display order & labels
# (No changes needed here - this defines fields, not scrapers)
ORDERED_PRIORITY_FIELDS_WITH_LABELS = [
    ('id', 'ID'),
    ('content_id', 'Content ID'),
    ('title', 'Title'),
    ('originaltitle', 'Original Title'),
    ('description', 'Description'),
    ('release_year', 'Release Year'),
    ('release_date', 'Release Date'),
    ('runtime', 'Runtime'),
    ('director', 'Director'),
    ('maker', 'Maker/Studio'),
    ('label', 'Label'),
    ('series', 'Series'),
    ('genres', 'Genres'),
    ('actresses', 'Actresses'),
    ('cover_url', 'Cover Image'),
    # ('folder_image_constructed_url', 'Folder Image'),
    ('screenshot_urls', 'Additional Images'),
]

# Extract just the keys in the correct order for processing
# (No changes needed here)
PRIORITY_FIELDS_ORDERED = [item[0] for item in ORDERED_PRIORITY_FIELDS_WITH_LABELS]
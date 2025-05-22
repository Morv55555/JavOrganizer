# Movie Scraper & Organizer

A Streamlit-based desktop application designed to automatically fetch metadata and artwork for movie files, organize them, and generate NFO files compatible with media managers.

## Features

*   **Automated Metadata Scraping:**
    *   Supports multiple online sources:
    *   Retrieves information like title, original title, description, release date, runtime, director, studio (maker), label, series, genres, and cast.
*   **Artwork Downloading:**
    *   Downloads cover images.
    *   Optionally downloads additional screenshot/fanart images.
    *   Automatically generates a `folder.jpg` for better display in some file explorers.
*   **NFO File Generation:**
    *   Creates `.nfo` files in a format compatible with popular media centers.
    *   Includes all scraped metadata, actor details, and links to downloaded artwork.
*   **File Organization:**
    *   **Standard Mode:** Moves processed movie files and their associated metadata/artwork into new, neatly named subfolders within a specified output directory (e.g., `[ID] [Studio] - Title/`).
    *   **Recursive Mode:** Scans an input directory and its subfolders. Instead of moving files, it places NFO files and artwork directly alongside the original movie files in their existing locations.
*   **Metadata Editing:**
    *   Built-in editor to review and modify scraped data before final organization.
    *   Manually specify poster URLs.
    *   Re-scrape a movie using a specific URL if the initial automatic scrape was incorrect.
*   **Translation:**
    *   Translate titles and descriptions using:
        *   Google Translate (via `googletrans` library)
        *   DeepL (requires API key)
        *   DeepSeek (requires API key)
    *   Option to keep the original description alongside the translated one.
*   **Customizable Settings:**
    *   Enable/disable specific scrapers.
    *   Define field priority (e.g., prefer DMM for title, R18.dev for release date).
    *   Configure default input/output directories.
    *   Manage a genre blacklist to exclude unwanted genres.

## Prerequisites

*   Python 3.8+
*   `pip` (Python package installer)

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Morv55555/JavOrganizer.git
    cd your-repository-name
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application
```bash
streamlit run app.py
```


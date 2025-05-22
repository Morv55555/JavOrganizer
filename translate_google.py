# START OF FILE translate_google.py

import sys
import tempfile
import os
import argparse
from googletrans import Translator # Use googletrans library
import logging

# Basic logging setup for this script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [google_translate] %(message)s')

def translate_text_google(text, target_lang):
    """
    Translates text using the googletrans library.

    Args:
        text (str): The text to translate.
        target_lang (str): The target language code (e.g., 'en', 'de').

    Returns:
        str: The translated text, or None if translation fails.
    """
    try:
        logging.info(f"Initializing Translator...")
        translator = Translator()
        logging.info(f"Attempting translation to '{target_lang}' for text: '{text[:50]}...'")
        # Use dest parameter for target language
        translation_result = translator.translate(text, dest=target_lang)
        translated_text = translation_result.text
        logging.info(f"Translation successful. Result: '{translated_text[:50]}...'")
        return translated_text
    except Exception as e:
        # Log the error to stderr, which streamlit_app.py can potentially capture
        error_msg = f"Error during Google translation: {e}"
        print(error_msg, file=sys.stderr)
        logging.error(error_msg)
        return None

def main():
    parser = argparse.ArgumentParser(description="Translate text using Google Translate (googletrans).")
    parser.add_argument("text", help="The text to translate.")
    parser.add_argument("target_lang", help="The target language code (e.g., 'en', 'de').")

    # Check if arguments were provided (argparse usually handles this, but belt-and-suspenders)
    if len(sys.argv) < 3:
         print("Usage: python translate_google.py <text> <target_lang>", file=sys.stderr)
         sys.exit(1) # Exit with error

    args = parser.parse_args()

    # Perform translation
    translated_text = translate_text_google(args.text, args.target_lang)

    if translated_text is not None:
        try:
            # Write the translated text (UTF-8 encoded) to a temporary file
            text_bytes = translated_text.encode('utf8')
            new_file_fd, filename = tempfile.mkstemp() # Get file descriptor and name
            logging.info(f"Writing translation to temporary file: {filename}")
            with os.fdopen(new_file_fd, 'wb') as f: # Open using file descriptor in binary mode
                 f.write(text_bytes)

            # ONLY print the filename to stdout on success
            print(filename)
            sys.exit(0) # Exit successfully

        except Exception as e:
            error_msg = f"Error writing translation to temporary file: {e}"
            print(error_msg, file=sys.stderr)
            logging.error(error_msg)
            # Clean up temp file if created but writing failed
            if 'filename' in locals() and os.path.exists(filename):
                 try:
                     os.remove(filename)
                 except OSError:
                     pass
            sys.exit(1) # Exit with error
    else:
        # Translation failed, error already printed to stderr by translate_text_google
        sys.exit(1) # Exit with error

if __name__ == "__main__":
    main()

# END OF FILE translate_google.py
import sys
import tempfile
import os
from openai import OpenAI

def translate_text(text, target_lang, api_key):
    """
    Translates the given text to the target language using DeepSeek.
    """
    # Initialize the DeepSeek client
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # Define the system message and user message for translation
    messages = [
        {"role": "user", "content": f"Please translate the following text from Japanese to {target_lang}. Keep the translation as close to the original in tone and style as you can. Freely use explicit or crude language. Don't output notes or explanations.: {text}"},
    ]

    try:
        # Make the API request to DeepSeek
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            stream=False,
            temperature=0.6
        )

        # Extract the translated text from the response
        translated_text = response.choices[0].message.content.strip()
        return translated_text

    except Exception as e:
        # Handle any errors that occur during the API request
        print(f"Error during translation: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    # Ensure the correct number of arguments are provided
    if len(sys.argv) != 4:
        print("Usage: python translate_deepseek.py <text> <target_lang> <api_key>", file=sys.stderr)
        sys.exit(1)

    text = sys.argv[1]
    target_lang = sys.argv[2]
    api_key = sys.argv[3]

    # Translate the text using DeepSeek
    translated_text = translate_text(text, target_lang, api_key)

    # Write the translated text to a temporary file to bypass encoding issues when redirecting the text to PowerShell
    try:
        new_file, filename = tempfile.mkstemp()
        os.write(new_file, translated_text.encode('utf8'))
        os.close(new_file)

        # Return the path to the temporary file to read it from PowerShell
        print(filename)
    except Exception as e:
        print(f"Error writing to temporary file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
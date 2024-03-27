import os
import requests
import re
import json

from openai import OpenAI
from exa_py import Exa
from bs4 import BeautifulSoup

from dotenv import load_dotenv
load_dotenv()

def print_success(message):
    print("\033[92m" + message + "\033[0m")  # Green
def print_request(message):
    print("\033[93m" + message + "\033[0m")  # Yellow
def print_error(message):
    print("\033[91m" + message + "\033[0m")  # Redz


def call_llm(system_prompt: str, user_prompt: str) -> dict:
    """
    Calls the GPT-3.5-Turbo model with given system and user prompts.

    Parameters:
    - system_prompt (str): The system prompt to provide context for the model.
    - user_prompt (str): The user prompt to specify the task for the model.

    Returns:
    - dict: A dictionary representing the JSON response from the model. If an error occurs, returns an empty dictionary.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        print_request(f"Sending request to llm with prompt: '{user_prompt}'")
        
        chat_completion = client.chat.completions.create(
            messages=messages,
            model="gpt-3.5-turbo",  # Adjust the model name if necessary
            max_tokens=200
        )

        raw_response = chat_completion.choices[0].message.content if chat_completion.choices else ""
        
        return raw_response.strip()

    except Exception as e:
        print_error(f"\n\nAn error occurred: {e}")

    return ""


def generate_keyword_query(natural_language_query: str) -> str:
    """
    Generates a keyword query from a natural language query using the GPT-3.5 model.

    Parameters:
    - natural_language_query (str): The natural language query provided by the user.

    Returns:
    - str: A keyword query suitable for the Exa search engine.
    """
    system_prompt = "You are a highly intelligent AI trained to refine natural language queries into concise keyword queries suitable for search engines. Given a natural language query, return a refined keyword query."
    user_prompt = f"Refine the following natural language query into a concise keyword query for a search engine: '{natural_language_query}'"

    # Call the existing function to interact with the GPT model
    keyword_query = call_llm(system_prompt, user_prompt)

    if keyword_query:
        print_success(f"Refined keyword query: {keyword_query}")
    else:
        print_error("Failed to generate a keyword query. Using the original query as a fallback.")
        keyword_query = natural_language_query  # Fallback to the original query if GPT fails to refine it

    return keyword_query


def search_with_exa(query: str, num_results: int):
    """
    Searches the internet using the Exa search engine and returns formatted results.

    Parameters:
    query (str): The search query.
    num_results (int): The number of search results to return.

    Returns:
    str: A formatted string containing the search results.
    """
    print_request(f"\n\nSearching Exa for: '{query}'...\n\n")
    # Directly use the query provided by the user for the Exa search
    exa = Exa(api_key=os.environ["EXA_API_KEY"])
    results = exa.search(query, type="keyword", use_autoprompt=False, num_results=num_results)
    print_success(f"\n\nResults:\n\n {results}")
    return results


def get_developer_doc_urls(search_results, query):
    """
    Evaluates the quality of search results from Exa using the GPT API.

    Parameters:
    - search_results (list): A list of dictionaries containing 'url' and 'snippet' from Exa search results.
    - query (str): The search query used to obtain the search results.

    Returns:
    - list: A list of URLs deemed high quality by the GPT model.
    """
    # Format search results for the prompt
    formatted_results = search_results
    user_prompt = f"These are the links and their summaries related to query '{query}':\n\n{formatted_results}\n\nPlease return a list of the links that are likely to contain developer documentation related to {query}. **Do not comment before or after your comma separated list of URLs."
    system_prompt = "You are a highly intelligent AI trained to evaluate the quality of web content and return comma separated URLs. Given a list of links and their summaries, identify and return only those links that represent high-quality, reliable, and relevant developer docs and how-to information related to the query. The links should be returned as a comma-separated list. **Do not comment before or after your comma separated list of the most likely to be formal developer documentation urls."

    # Call the existing function to interact with the GPT model
    response = call_llm(system_prompt, user_prompt)

    dev_doc_urls = [url.strip() for url in response.split(',') if url.strip()] if response else []
    print(f"Developer documentation URLs: {dev_doc_urls}")
    return dev_doc_urls


def save_website_as_markdown(urls):
    """Scrapes websites using browserless, partitions HTML, converts them to Markdown, and saves them to files."""
    # Check if urls is a string and split it into a list if necessary
    if isinstance(urls, str):
        urls = [url.strip() for url in urls.split(",") if url.strip()]

    for url in urls:
        print(f"Processing URL: {url}") 

        try:
            # Use browserless to get website content
            browserless_url = f"https://chrome.browserless.io/content?token={os.environ['BROWSERLESS_API_KEY']}"
            payload = json.dumps({"url": url})
            headers = {'cache-control': 'no-cache', 'content-type': 'application/json'}

            print_request(f"Sending request to Browserless for URL: {url}\n\n")
            response = requests.request("POST", browserless_url, headers=headers, data=payload)
            response.raise_for_status()  # Raises an HTTPError if the response status code is 4XX/5XX
            print_success(f"Received response from Browserless for URL: {url}")

            # Parse HTML content to retain text and code blocks using BeautifulSoup
            print("Parsing HTML content to retain text and code blocks...")
            soup = BeautifulSoup(response.text, 'html.parser')

            # Initialize an empty list to hold the content parts
            content_parts = []

            # Function to capture <pre> and <code> blocks as they are
            def capture_code_blocks(soup_element):
                for element in soup_element.descendants:
                    if element.name == 'pre':
                        # For <pre> blocks, preserve as block code with newlines
                        content_parts.append(f"\n\n```{element.get_text()}```\n\n")
                    elif element.name == 'code':
                        # For <code> blocks, check if they are within <pre> (handled above) or standalone
                        # Standalone <code> blocks are treated as inline code without added newlines
                        parent = element.find_parent('pre')
                        if not parent:  # If <code> is not within <pre>, treat as inline
                            content_parts.append(f"`{element.get_text()}`")
                    elif element.name is None:
                        # For NavigableString elements outside <pre> and <code>, append their text content
                        stripped_string = element.string.strip()
                        if stripped_string:  # Only append if the string is not empty after stripping
                            content_parts.append(stripped_string)

            # Start capturing from the body tag to exclude head content
            body_content = soup.body if soup.body else soup
            capture_code_blocks(body_content)

            # Join all parts into a single string
            content = ''.join(content_parts)
            print_success("HTML content has been successfully parsed and prepared with text and code blocks.\n\n")

            # Use GPT to generate a filename based on the URL
            file_title = generate_filename_from_url(url)

            # Define the folder path as 'cursor-knowledge' in the parent directory of the script
            folder_path = os.path.join(os.path.dirname(__file__), 'cursor-knowledge')
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)

            output_file = os.path.join(folder_path, f"{file_title}.md")
            with open(output_file, 'w', encoding='utf-8') as file:
                file.write(content)

            # Use os.path.sep to split the path according to the system's directory separator
            path_components = output_file.split(os.path.sep)
            # Take the last 3 components of the path for abbreviation, or adjust the number as needed
            abbreviated_path_components = path_components[-3:]
            abbreviated_path = "/.../" + os.path.join(*abbreviated_path_components)
            print_success(f"Markdown content for {url} has been successfully saved to {abbreviated_path}")
        except requests.exceptions.HTTPError as e:
            print_error(f"\n\nHTTP Error occurred while processing {url}: {e}\n\n")
        except requests.exceptions.RequestException as e:
            print_error(f"\n\nError fetching the URL {url}: {e}\n\n")
        except Exception as e:
            print_error(f"\n\nAn error occurred while processing {url}: {e}\n\n")


def generate_filename_from_url(url: str) -> str:
    """
    Generates a filename for saving markdown content by asking GPT for a title based on the URL.

    Parameters:
    - url (str): The URL of the webpage to generate a filename for.

    Returns:
    - str: A sanitized filename suggested by GPT.
    """
    system_prompt = "Given a URL, suggest a concise, descriptive, and readable title for a markdown file that will contain content from this webpage. The title should avoid special characters like /, *, ?, :, <, >, |), use natural language-like word separation (prefer dashes over underscores), and provide insight into the main topic or utility of the content. It's important that the provider or publisher of the content is clear, as well as the specific focus within the broader subject of the content. These files are used and read by people, so they should be distinguishable and informative based on titles alone. Return only a filename with no comments before or after. Do not add the file extension, you are only naming the file."
    user_prompt = f"Suggest a title for a file based on this URL, emphasizing its main topic or utility: {url}"

    # Call the existing function to interact with the GPT model
    suggested_title = call_llm(system_prompt, user_prompt)

    # Sanitize the suggested title to ensure it's filesystem-safe
    sanitized_title = re.sub(r'[\\/*?:"<>|]', "", suggested_title).strip()

    # Provide a fallback in case GPT's response is not usable
    if not sanitized_title:
        sanitized_title = "content_from_web"

    return sanitized_title


def main():
    natural_language_query = input("\n\n\nWhat developer documentation are you looking to search and save?\n\n")
    keyword_query = generate_keyword_query(natural_language_query)
    search_results = search_with_exa(keyword_query, 5)
    dev_doc_urls = get_developer_doc_urls(search_results, keyword_query)
    save_website_as_markdown(dev_doc_urls)

if __name__ == "__main__":
    main()
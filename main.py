import openai
from playwright.sync_api import sync_playwright
import json
import os
import re

# OpenAI API Setup
openai.api_key = os.environ.get('OPENAI_API_KEY')
if not openai.api_key:
    raise ValueError("Please set the OPENAI_API_KEY environment variable.")

# Define the actions
ACTIONS = ['CLICK', 'WRITE_TEXT', 'SUBMIT_FORM', 'NAVIGATE_TO', 'SCROLL']

def parse_and_simplify_html(page):
    elements = page.query_selector_all("a, button, input, textarea, form")

    structured_dom = {
        "clickables": [],
        "inputs": [],
        "forms": []
    }
    
    used_ids = {}  # Store IDs and their counts
    
    for e in elements:
        if not e.is_visible():
            continue
        
        tag_name = page.evaluate("el => el.tagName", e)
        element_id = e.get_attribute('id') or e.get_attribute('class')
        inner_text = page.evaluate("el => el.innerText", e).strip()
        input_type = e.get_attribute("type")

        # Check if ID has been used before, and append index if needed
        if element_id in used_ids:
            used_ids[element_id] += 1
            element_id = f"{element_id}_{used_ids[element_id]}"
        else:
            used_ids[element_id] = 0

        if tag_name in ["A", "BUTTON"] or (tag_name == "INPUT" and input_type == "submit"):
            # If the input element is of type "submit", use its value attribute as the text
            if tag_name == "INPUT" and input_type == "submit":
                inner_text = e.get_attribute("value").strip()
            
            structured_dom["clickables"].append({"id": element_id, "text": inner_text})

        elif tag_name in ["INPUT", "TEXTAREA"] and input_type != "submit":
            placeholder = page.evaluate("el => el.placeholder", e)
            structured_dom["inputs"].append({"id": element_id, "placeholder": placeholder})
        elif tag_name == "FORM":
            structured_dom["forms"].append(element_id)

    return structured_dom

def get_action_from_gpt(structured_dom, objective, last_action=None):
    """Get the next action from GPT-3.5-turbo-instruct."""
    
    actions_str = ', '.join(ACTIONS)
    
    # Create a more structured prompt
    last_action_str = (f"Given the last action was {json.dumps(last_action)}, " if last_action else "")
    prompt = (f"{last_action_str}Given the current state of the webpage {json.dumps(structured_dom)} and the "
              "objective '{objective}', determine the most appropriate action from the following list: {actions_str}. "
              "Please respond in a structured JSON format. For example:\n"
              "- If the action is CLICK, your response should be: {\"action\": \"CLICK\", \"target\": \"ELEMENT_ID\"}\n"
              "- If the action is WRITE_TEXT, your response should be: {\"action\": \"WRITE_TEXT\", \"target\": \"ELEMENT_ID\", \"text\": \"SOME_TEXT\"}\n"
              "- If the action is NAVIGATE_TO, your response should be: {\"action\": \"NAVIGATE_TO\", \"target\": \"URL\"}\n"
              "... and so on for other actions. Provide the necessary details for each action. You are only allowed to provide one action at a time.")

    response = openai.Completion.create(engine="gpt-3.5-turbo-instruct", prompt=prompt, temperature=0, max_tokens=150)
    print(response)

    # Split the response text by newline
    action_texts = response.choices[0].text.strip().split("\n")
    
    for action_text in action_texts:
        try:
            action_data = json.loads(action_text)
            action = action_data.get('action')
            
            if action == "WRITE_TEXT":
                # For WRITE_TEXT, expect both "target" and "text"
                details = {
                    "element_id": action_data.get('target'),
                    "text": action_data.get('text')
                }
            else:
                details = action_data.get('target')  # Use "target" for other actions
            return action, details
        except json.JSONDecodeError:
            continue

    print(f"Could not extract a valid action from: {response.choices[0].text.strip()}")
    return None, None


def execute_action(page, action, details):
    """Execute the given action on the webpage using Playwright."""
    if action is None or details is None:
        print("Action or details are None. Cannot execute.")
        return
    
    # Check if there are multiple class names and format them correctly
    if ' ' in details:
        selector = '.' + '.'.join(details.split())
    else:
        selector = f"#{details}"

    if action == 'CLICK':
        page.click(selector)
    elif action == 'WRITE_TEXT':
        element_id = details.get('element_id')
        text = details.get('text')
        page.fill(f"#{element_id}", text)
    elif action == 'SUBMIT_FORM':
        page.click(f"form#{details} [type=submit]")
    elif action == 'NAVIGATE_TO':
        if details.startswith('http'):
            page.goto(details)
        else:
            # If it doesn't start with http, you can prefix it with "http://"
            page.goto(f"http://{details}")
    elif action == 'SCROLL':
        if details == 'down':
            page.scroll(0, 100)
        elif details == 'up':
            page.scroll(0, -100)
    else:
        print(f"Unknown action: {action}")


def wait_for_page_load(page):
    """Wait for the page to fully load."""
    page.wait_for_load_state("load")




def main():
    objective = input("Please enter your objective (e.g., 'SIGN IN TO THE ACCOUNT'): ")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://dominos.com")  # Start URL

        last_action = None  # Initialize with None since there's no action taken yet

        for _ in range(10):  # Limit to 10 actions for this example
            structured_dom = parse_and_simplify_html(page)
            print(structured_dom)
            action, details = get_action_from_gpt(structured_dom, objective, last_action)

            # Confirm action
            confirm = input(f"Do you want to execute: {action} with details {details}? (yes/no) ")
            if confirm.lower() == 'yes':
                execute_action(page, action, details)
                wait_for_page_load(page)  # Wait for the page to fully load
                last_action = {"action": action, "details": details}  # Store the last action taken
            else:
                print("Action aborted by user.")


        browser.close()

if __name__ == "__main__":
    main()


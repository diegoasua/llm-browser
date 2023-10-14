import openai
from playwright.sync_api import sync_playwright
import json
import os
import re

# OpenAI API Setup
openai.api_key = os.environ.get('OPENAI_API_KEY')
if not openai.api_key:
    raise ValueError("Please set the OPENAI_API_KEY environment variable.")

# openai.api_key = 'YOUR_OPENAI_API_KEY'

# Define the actions
ACTIONS = ['CLICK', 'WRITE_TEXT', 'SUBMIT_FORM', 'NAVIGATE_TO', 'SCROLL']

def parse_and_simplify_html(page):
    """Simplify the webpage's DOM and return a structured representation."""
    # This is a basic example, you might want to expand it
    elements = page.query_selector_all("a, button, input, textarea, form")

    structured_dom = {
        "clickables": [],
        "inputs": [],
        "forms": []
    }
    
    for e in elements:
        if not e.is_visible():
            continue
        
        tag_name = page.evaluate("el => el.tagName", e)
        element_id = e.get_attribute('id') or e.get_attribute('class')

        if tag_name in ["A", "BUTTON"]:
            structured_dom["clickables"].append(element_id)
        elif tag_name in ["INPUT", "TEXTAREA"]:
            structured_dom["inputs"].append(element_id)
        elif tag_name == "FORM":
            structured_dom["forms"].append(element_id)

    return structured_dom

def get_action_from_gpt(structured_dom, objective):
    """Get the next action from GPT-3.5-turbo-instruct."""
    
    actions_str = ', '.join(ACTIONS)
    
    # Prompt
    prompt = f"Given the current state of the webpage {json.dumps(structured_dom)} and the objective of '{objective}', please specify which of the following actions ({actions_str}) should be taken and provide the necessary parameters for that action."

    response = openai.Completion.create(engine="gpt-3.5-turbo-instruct", prompt=prompt, temperature=0, max_tokens=150)
    action_text = response.choices[0].text.strip()

    # Updated regex to capture the format "NAVIGATE_TO Parameters: URL = "https://www.dominos.com/""
    match = re.search(r"(NAVIGATE_TO|CLICK|WRITE_TEXT|SUBMIT_FORM|SCROLL)(?:\s*Parameters:\s*URL\s*=\s*\"(.*)\")?", action_text)
    if match:
        action = match.group(1)
        details = match.group(2) if match.group(2) else ""

        print(f"Extracted action: {action}, Details: {details}")
        
        # If the action is WRITE_TEXT, additional parsing might be needed
        if action == 'WRITE_TEXT':
            text_match = re.search(r"WRITE_TEXT\s*Parameters:\s*Element\s*=\s*([a-zA-Z_\-#]+)\s*Text\s*=\s*\"(.*)\"", action_text)
            if text_match:
                element_id, text = text_match.groups()
                return f"{action} {element_id} {text.strip()}"
        
        return f"{action} {details.strip()}"

    else:
        print(f"Could not extract a valid action from: {action_text}")
        return None

def execute_action(page, action):
    """Execute the given action on the webpage using Playwright."""

    if action is None:
        print("Action is None. Cannot execute.")
        return

    # Split action to identify type and target
    action_type, _, target = action.partition(' ')
    
    if action_type == 'CLICK':
        page.click(f"#{target}")
    elif action_type == 'WRITE_TEXT':
        target, _, text = target.partition(' ')
        page.fill(f"#{target}", text)
    elif action_type == 'SUBMIT_FORM':
        page.click(f"form#{target} [type=submit]")
    elif action_type == 'NAVIGATE_TO':
        if target.startswith('http'):
            page.goto(target)
        else:
            print(f"Invalid URL: {target}")
    elif action_type == 'SCROLL':
        if target == 'down':
            page.scroll(0, 100)
        elif target == 'up':
            page.scroll(0, -100)
    else:
        print(f"Unknown action: {action}")


def main():
    objective = input("Please enter your objective (e.g., 'SIGN IN TO THE ACCOUNT'): ")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("https://google.com")  # Start URL

        for _ in range(10):  # Limit to 10 actions for this example
            structured_dom = parse_and_simplify_html(page)
            action = get_action_from_gpt(structured_dom, objective)

            # Confirm action
            confirm = input(f"Do you want to execute: {action}? (yes/no) ")
            if confirm.lower() == 'yes':
                execute_action(page, action)
            else:
                print("Action aborted by user.")

        browser.close()

if __name__ == "__main__":
    main()


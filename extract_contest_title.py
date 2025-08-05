import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


def contest_title(contest_link, driver):
    """
    Extract the title of a contest from its page.
    
    Args:
        contest_link (str): URL of the contest page
        driver: Selenium WebDriver instance
        
    Returns:
        str: Contest title or None if not found
    """
    try:
        driver.get(contest_link)
        
        # Wait for page to load and find the title
        title_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        
        title = title_element.text.strip()
        print(f"Found title: {title}")
        return title
        
    except Exception as e:
        print(f"Error extracting title from {contest_link}: {e}")
        return None

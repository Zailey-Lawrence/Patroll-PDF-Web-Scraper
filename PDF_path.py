import time
import re
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


def normalize_text(text):
    """Remove all formatting and convert to lowercase for comparison."""
    return re.sub(r'[^a-z0-9]', '', text.lower())


def strip_us_prefix(patent_id):
    """Remove US prefix from patent IDs if present."""
    return patent_id[2:] if patent_id.upper().startswith("US") else patent_id


def get_prior_art_link(contest_link, driver):
    """
    Get the prior art download link from a contest page using multiple strategies.
    
    Args:
        contest_link (str): URL of the contest page
        driver: Selenium WebDriver instance
        
    Returns:
        str: Prior art download link or None if not found
    """
    try:
        driver.get(contest_link)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Strategy 1: Look for "DOWNLOAD WINNING PRIOR ART HERE:" text with following link
        try:
            download_link_element = WebDriverWait(driver, 2).until(  # Reduced wait time
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'DOWNLOAD WINNING PRIOR ART HERE:')]/following-sibling::a")
                )
            )
            href = download_link_element.get_attribute("href")
            if href:
                return href  # Return immediately without printing for speed
        except:
            pass
        
        # Strategy 2: Look for "DOWNLOAD WINNING PRIOR ART HERE:" text in same element as link
        try:
            download_link_element = driver.find_element(
                By.XPATH, "//a[contains(text(), 'DOWNLOAD WINNING PRIOR ART HERE:')]"
            )
            href = download_link_element.get_attribute("href")
            if href:
                return href  # Return immediately
        except:
            pass
        
        # Strategy 3: Look for any link containing "DOWNLOAD" and "PRIOR ART"
        try:
            download_link_element = driver.find_element(
                By.XPATH, "//a[contains(text(), 'DOWNLOAD') and contains(text(), 'PRIOR ART')]"
            )
            href = download_link_element.get_attribute("href")
            if href:
                return href  # Return immediately
        except:
            pass
        
        # Strategy 4: Quick BeautifulSoup parsing (faster than multiple Selenium calls)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Look for insights links first (most common)
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href and 'insights' in href:
                full_url = href if href.startswith('http') else f"https://www.unifiedpatents.com{href}"
                return full_url
        
        # Strategy 5: Look for text patterns (only if insights not found)
        for link in soup.find_all('a', href=True):
            link_text = link.get_text().lower()
            if any(keyword in link_text for keyword in ['download', 'prior art', 'winning']):
                href = link.get('href')
                if href:
                    full_url = href if href.startswith('http') else f"https://www.unifiedpatents.com{href}"
                    return full_url
        
        return None  # No verbose logging for speed
        
    except Exception as e:
        print(f"Error getting prior art link from {contest_link}: {e}")
        return None


def pdf_path(contest_link, patent_id, driver):
    """
    Get the PDF download path for a specific contest and patent ID.
    
    Args:
        contest_link (str): URL of the contest page
        patent_id (str): Patent ID to search for
        driver: Selenium WebDriver instance
        
    Returns:
        str: PDF download URL or None if not found
    """
    try:
        # Get the prior art page link
        art_link = get_prior_art_link(contest_link, driver)
        if not art_link:
            print(f"⚠️  No prior art link found for contest: {contest_link}")
            # Check if this might be a newer contest without results yet
            driver.get(contest_link)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            page_text = soup.get_text().lower()
            
            if any(keyword in page_text for keyword in ['pending', 'in progress', 'not yet', 'coming soon', 'active']):
                print(f"ℹ️  Contest appears to be pending/active - prior art may not be available yet")
            else:
                print(f"❌ Contest appears complete but no prior art link found")
            
            return None

        driver.get(art_link)

        # Wait for content to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")
        p_tags = soup.find_all('p')
        
        search_id = strip_us_prefix(patent_id)
        found_match = False

        # Search through paragraph tags to find the matching patent ID
        for i, p in enumerate(p_tags):
            paragraph_text = p.get_text(strip=True)

            # Check if this paragraph contains our patent ID
            if normalize_text(search_id) in normalize_text(paragraph_text):
                found_match = True
                print(f"✅ Found patent match: {search_id} in paragraph {i}")
                
                # Look for download links in the next few paragraphs
                for j in range(i + 1, min(i + 4, len(p_tags))):
                    for a in p_tags[j].find_all("a"):
                        href = a.get("href", "")
                        link_text = a.get_text(strip=True).lower()
                        
                        if "download" in link_text or href.lower().endswith(".pdf"):
                            full_url = urljoin(art_link, href)
                            print(f"✅ Found PDF link: {full_url}")
                            return full_url

                # If not found in paragraphs, search all links on the page
                for a in soup.find_all("a"):
                    link_text = a.get_text(strip=True).lower()
                    href = a.get("href", "")
                    
                    if "download" in link_text and href:
                        full_url = urljoin(art_link, href)
                        print(f"✅ Found general download link: {full_url}")
                        return full_url

        if not found_match:
            print(f"❌ No patent ID match found for: {patent_id} in prior art page")
            print(f"🔍 Available text content preview: {soup.get_text()[:200]}...")
            return None

    except Exception as e:
        print(f"❌ Error getting PDF path for {contest_link}: {e}")
        return None

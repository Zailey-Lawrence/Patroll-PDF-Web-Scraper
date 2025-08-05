from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import threading
import sys
import select

from extract_contest_title import contest_title
from PDF_path import pdf_path


def debug_contest_page(contest_url, driver):
    """
    Debug function to examine the content of a contest page when prior art link is not found.
    
    Args:
        contest_url (str): URL of the contest page to debug
        driver: Selenium WebDriver instance
    """
    try:
        print(f"\n🔍 DEBUG: Examining contest page: {contest_url}")
        driver.get(contest_url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Look for any text containing "download", "prior art", or "winning"
        all_text = soup.get_text().lower()
        keywords = ['download', 'prior art', 'winning', 'submission']
        
        print("📝 Text content analysis:")
        for keyword in keywords:
            if keyword in all_text:
                print(f"  ✅ Found keyword: '{keyword}'")
            else:
                print(f"  ❌ Missing keyword: '{keyword}'")
        
        # Look for all links on the page
        links = soup.find_all('a', href=True)
        print(f"\n🔗 Found {len(links)} links on the page:")
        
        for i, link in enumerate(links[:10]):  # Show first 10 links
            href = link.get('href')
            text = link.get_text().strip()
            print(f"  {i+1}. Text: '{text}' | Href: '{href}'")
        
        if len(links) > 10:
            print(f"  ... and {len(links) - 10} more links")
        
        # Look for specific patterns
        print(f"\n🎯 Searching for specific patterns:")
        download_patterns = [
            'download.*prior.*art',
            'winning.*prior.*art',
            'prior.*art.*here',
            'download.*winning'
        ]
        
        import re
        for pattern in download_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                print(f"  ✅ Found pattern '{pattern}': {matches[:3]}")
            else:
                print(f"  ❌ No matches for pattern '{pattern}'")
                
    except Exception as e:
        print(f"❌ Error during debug: {e}")


def get_user_choice_with_timeout(prompt, timeout=5, default_choice=False):
    """
    Get user input with a timeout. If no input within timeout, return default choice.
    
    Args:
        prompt (str): The prompt message to display
        timeout (int): Timeout in seconds
        default_choice (bool): Default choice if timeout occurs
    
    Returns:
        bool: User's choice or default if timeout
    """
    print(f"\n{prompt}")
    print(f"You have {timeout} seconds to respond (default: {'No' if not default_choice else 'Yes'})")
    print("Enter 'y' for Yes, 'n' for No, or press Enter for default: ", end="", flush=True)
    
    result = [default_choice]  # Use list to make it mutable in nested function
    
    def get_input():
        try:
            user_input = input().strip().lower()
            if user_input in ['y', 'yes']:
                result[0] = True
            elif user_input in ['n', 'no']:
                result[0] = False
            # If empty or invalid, keep default
        except:
            pass  # Keep default on any error
    
    # Start input thread
    input_thread = threading.Thread(target=get_input, daemon=True)
    input_thread.start()
    
    # Wait for timeout
    input_thread.join(timeout)
    
    if input_thread.is_alive():
        print(f"\n⏰ Timeout! Using default choice: {'Yes' if result[0] else 'No'}")
    else:
        print(f"✅ Choice selected: {'Yes' if result[0] else 'No'}")
    
    return result[0]


def process_contests_sequential(contest_urls, patent_ids, scraper):
    """
    Process contests sequentially (one at a time) for compatibility.
    
    Args:
        contest_urls (list): List of contest URLs
        patent_ids (list): List of corresponding patent IDs
        scraper: Selenium WebDriver instance
    
    Returns:
        tuple: (contest_titles, pdf_paths) in original order
    """
    contest_titles = []
    pdf_paths = []
    
    print(f"🔄 Processing {len(contest_urls)} contests sequentially...")
    
    for i, (contest_url, patent_id) in enumerate(zip(contest_urls, patent_ids)):
        try:
            print(f"[{i+1}/{len(contest_urls)}] Processing contest: {contest_url}")
            
            title = contest_title(contest_url, scraper)
            path = pdf_path(contest_url, patent_id, scraper)
            
            if path is None:
                print(f"⚠️  PDF path not found for {contest_url}")
            
            contest_titles.append(title)
            pdf_paths.append(path)
            
        except Exception as e:
            print(f"❌ Error processing contest {contest_url}: {e}")
            contest_titles.append(None)
            pdf_paths.append(None)
    
    return contest_titles, pdf_paths


@contextmanager
def chrome_driver_context():
    """Context manager for Chrome driver to ensure proper cleanup."""
    driver = create_chrome_driver()
    try:
        yield driver
    finally:
        driver.quit()


def process_single_contest(contest_data):
    """
    Process a single contest to extract title and PDF path.
    This function runs in a separate thread with its own driver.
    
    Args:
        contest_data (tuple): (contest_url, patent_id, index)
    
    Returns:
        dict: Contest processing results
    """
    contest_url, patent_id, index = contest_data
    
    # Create a new driver for this thread
    with chrome_driver_context() as scraper:
        try:
            print(f"[Thread {index}] Processing contest: {contest_url}")
            
            title = contest_title(contest_url, scraper)
            path = pdf_path(contest_url, patent_id, scraper)
            
            if path is None:
                print(f"[Thread {index}] ⚠️  PDF path not found for {contest_url}")
                # We can optionally run debug here, but it might be too verbose in parallel
            
            return {
                'index': index,
                'contest_url': contest_url,
                'patent_id': patent_id,
                'title': title,
                'path': path,
                'success': True
            }
            
        except Exception as e:
            print(f"[Thread {index}] ❌ Error processing contest {contest_url}: {e}")
            return {
                'index': index,
                'contest_url': contest_url,
                'patent_id': patent_id,
                'title': None,
                'path': None,
                'success': False,
                'error': str(e)
            }


def process_contests_parallel(contest_urls, patent_ids, max_workers=4):
    """
    Process multiple contests in parallel using ThreadPoolExecutor.
    
    Args:
        contest_urls (list): List of contest URLs
        patent_ids (list): List of corresponding patent IDs
        max_workers (int): Maximum number of parallel threads
    
    Returns:
        tuple: (contest_titles, pdf_paths) in original order
    """
    contest_titles = [None] * len(contest_urls)
    pdf_paths = [None] * len(contest_urls)
    
    # Prepare data for parallel processing
    contest_data = [(url, pid, i) for i, (url, pid) in enumerate(zip(contest_urls, patent_ids))]
    
    print(f"🚀 Processing {len(contest_data)} contests with {max_workers} parallel workers...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_contest = {executor.submit(process_single_contest, data): data for data in contest_data}
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_contest):
            result = future.result()
            
            # Store results in original order
            idx = result['index']
            contest_titles[idx] = result['title']
            pdf_paths[idx] = result['path']
            
            completed += 1
            if completed % 5 == 0:  # Progress update every 5 completions
                print(f"📊 Progress: {completed}/{len(contest_data)} contests completed")
    
    return contest_titles, pdf_paths


def save_results_to_json(contest_links, patent_ids, contest_titles, pdf_paths, filename="scraped_data.json"):
    """Save the scraped data to a JSON file."""
    data = {
        "contest_links": contest_links,
        "patent_ids": patent_ids,
        "contest_titles": contest_titles,
        "pdf_paths": pdf_paths,
        "total_count": len(contest_links)
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Data saved to {filename}")
    except Exception as e:
        print(f"Error saving data to JSON: {e}")


def create_chrome_driver():
    """Create a highly optimized headless Chrome driver for fast web scraping."""
    options = Options()
    
    # Core headless configuration with fastest settings
    options.add_argument("--headless=new")  # Use new headless mode (more efficient)
    options.add_argument("--window-size=1280,720")  # Smaller window for faster rendering
    
    # Maximum performance optimizations
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-features=TranslateUI,VizDisplayCompositor")
    options.add_argument("--disable-ipc-flooding-protection")
    
    # Aggressive memory and CPU optimizations
    options.add_argument("--memory-pressure-off")
    options.add_argument("--max_old_space_size=2048")  # Reduced memory footprint
    options.add_argument("--aggressive-cache-discard")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-component-update")
    
    # Network and loading optimizations (keep JS enabled for dynamic content)
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Don't load images
    # Removed --disable-javascript since the site needs it for dynamic content
    options.add_argument("--disable-web-security")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    
    # Set minimal user agent
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # Page load strategy for better compatibility
    options.page_load_strategy = 'normal'  # Wait for page to fully load
    
    # Block all unnecessary content
    prefs = {
        "profile.default_content_setting_values": {
            "images": 2,  # Block images
            "plugins": 2,  # Block plugins
            "popups": 2,  # Block popups
            "geolocation": 2,  # Block location sharing
            "notifications": 2,  # Block notifications
            "media_stream": 2,  # Block microphone/camera
            "cookies": 2,  # Block cookies
        },
        "profile.managed_default_content_settings": {
            "images": 2
        }
    }
    options.add_experimental_option("prefs", prefs)
    
    # Service arguments for faster startup
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    return webdriver.Chrome(options=options)


# Ask user for processing preference with timeout
use_parallel = get_user_choice_with_timeout(
    "🚀 Do you want to use parallel processing for faster scraping?", 
    timeout=5, 
    default_choice=False  # Default to sequential processing for safety
)

if use_parallel:
    print("✅ Parallel processing enabled - Using 4 threads for maximum speed!")
else:
    print("🔄 Sequential processing enabled - Processing one contest at a time for stability.")


def main_scraping_logic(driver, use_parallel, scraper):
    """Main scraping logic that can work with either parallel or sequential processing."""
    
    # Open the page
    url = "https://patroll.unifiedpatents.com/contests?category=won"
    driver.get(url)
    
    # Wait for initial page load with longer timeout for dynamic content
    WebDriverWait(driver, 10).until(  # Increased back to 10 seconds for reliability
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    
    # Additional wait for dynamic content to load
    time.sleep(2)  # Give the page time to render contest list

    # Initialize lists to store contest data
    patentID = []
    pdfpath = []
    # all pdfpath stuff can be removed later but is there now to check if the code is working.
    priorartPDF_1 = []
    priorartPDF_1a = []
    contestTitles = []
    contestLinks = []

    # Constants
    PREFIX = 'https://www.google.com'
    BASE_CONTEST_URL = 'https://patroll.unifiedpatents.com/'
    MAX_PAGES = 10

    # loops through all the pages
    try:
        for page_num in range(1, MAX_PAGES + 1):
            print(f"Processing page {page_num}...")

            # Reduced sleep time for faster execution
            time.sleep(0.2)  # Further reduced from 0.5 to 0.2 seconds

            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Locate each contest
            ul = soup.find("ul", class_="ant-list-items")

            if ul:
                # Find the links each sections goes to
                temp = [a['href'] for a in ul.find_all('a', href=True)]
                print(f"🔍 DEBUG: Found {len(temp)} total links on page {page_num}")

                contest_link = [BASE_CONTEST_URL + link.lstrip('/') for link in temp if
                                link.startswith('/contests/')]
                contestLinks.extend(contest_link)
                print(f"🔍 DEBUG: Found {len(contest_link)} contest links on page {page_num}")

                # Leaves only google patent links
                patent_links = [link[31:] for link in temp if link.startswith(PREFIX)]
                patentID.extend(patent_links)
                print(f"🔍 DEBUG: Found {len(patent_links)} patent links on page {page_num}")

            else:
                print(f"❌ DEBUG: No 'ant-list-items' element found on page {page_num}")
                # Let's check what elements are available
                all_uls = soup.find_all("ul")
                print(f"🔍 DEBUG: Found {len(all_uls)} total <ul> elements")
                for i, ul_elem in enumerate(all_uls[:3]):  # Show first 3
                    classes = ul_elem.get('class', [])
                    print(f"  UL {i+1}: classes = {classes}")
                print(f"No contests found on page {page_num}. Stopping pagination.")
                break

            # Process contest data for this page
            if contest_link and patent_links:
                print(f"📋 Found {len(contest_link)} contests on page {page_num}")
                
                if use_parallel:
                    # Process contests in parallel (using 4 workers for optimal performance)
                    page_titles, page_paths = process_contests_parallel(contest_link, patent_links, max_workers=4)
                else:
                    # Process contests sequentially (one at a time)
                    page_titles, page_paths = process_contests_sequential(contest_link, patent_links, scraper)
                
                # Add results to main lists
                contestTitles.extend(page_titles)
                pdfpath.extend(page_paths)
                
                # Optional: Debug contests where PDF path was not found
                for i, (url, path) in enumerate(zip(contest_link, page_paths)):
                    if path is None:
                        print(f"⚠️  Consider debugging contest: {url}")
                        # Uncomment the next line if you want to debug immediately
                        # debug_contest_page(url, scraper if scraper else driver)

                # when PDF scraper is finished we can record that info here
                """try:
                    priorartPDF_1.append(pdf_link(contest_url, scraper))
                except:
                    priorartPDF_1.append(0)
                try:
                    priorartPDF_1a.append(prior_art(contest_url, scraper))
                except:
                    priorartPDF_1a.append(0)"""

            # Navigate to next page
            try:
                next_button = WebDriverWait(driver, 5).until(  # Reduced wait time
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "li.ant-pagination-next[title='Next Page']"))
                )
                driver.execute_script("arguments[0].scrollIntoView();", next_button)
                time.sleep(0.2)  # Reduced pause for scroll
                driver.execute_script("arguments[0].click();", next_button)
                print(f"Successfully navigated to page {page_num + 1}")
                
            except Exception as e:
                print(f"Could not navigate to next page: {e}")
                print("Reached end of pagination or encountered an error.")
                break

    except Exception as e:
        print(f"An error occurred during scraping: {e}")

    # Print summary and save results
    print(f"\nScraping completed!")
    print(f"Total contests found: {len(contestLinks)}")
    print(f"Total patent IDs: {len(patentID)}")
    print(f"Total contest titles: {len(contestTitles)}")
    print(f"Total PDF paths: {len(pdfpath)}")
    
    # Save results to JSON
    save_results_to_json(contestLinks, patentID, contestTitles, pdfpath)


# Set up Chrome drivers and execute scraping
# For parallel processing, we only need one driver for navigation
# For sequential processing, we need both drivers (navigation + scraping)
if use_parallel:
    with chrome_driver_context() as driver:
        main_scraping_logic(driver, use_parallel, None)
else:
    with chrome_driver_context() as driver, chrome_driver_context() as scraper:
        main_scraping_logic(driver, use_parallel, scraper)

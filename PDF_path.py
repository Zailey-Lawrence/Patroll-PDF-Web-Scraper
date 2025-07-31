import time
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re


#get rid of all formatting
def normalize(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

#gets rid of US prefix on patents
def strip_us_prefix(patentID):
    return patentID[2:] if patentID.upper().startswith("US") else patentID



options = Options()
options.add_argument("--headless")
driver = webdriver.Chrome(options=options)

# Get the prior art link from the contest page
def priorartlink(contestlink, driver):
    try:
        driver.get(contestlink)
        download_link_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'DOWNLOAD WINNING PRIOR ART HERE:')]/following-sibling::a")
            )
        )
        return download_link_element.get_attribute("href")
    except:
        print("Tag can't be found :(")
        return None
    finally:
        print("Done loading contest page.")

# Get the PDF link from the prior art page for the correct contest
def pdf_path(contestlink, patentID, driver):
    #loads the page
    artlink = priorartlink(contestlink, driver)
    if not artlink:
        return None

    driver.get(artlink)

    # Wait for content to load
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, 'body'))
    )

    #to be used later in the code
    soup = BeautifulSoup(driver.page_source, "html.parser")
    p_tags = soup.find_all('p')
    found_match = False

    # Loop through all <p> tags to find one with the contest title
    for i, p in enumerate(p_tags):
        #all paragraph text
        paragraph_text = p.get_text(strip=True)

        search_id = strip_us_prefix(patentID)

        #finds the right contest by the patent ID then gets the PDF link
        if normalize(search_id) in normalize(paragraph_text):
            found_match = True
            # Found the contest section — now check the next few <p> for a download link
            for j in range(i + 1, min(i + 4, len(p_tags))):
                for a in p_tags[j].find_all("a"):
                    href = a.get("href", "")
                    if "download" in a.get_text(strip=True).lower() or href.lower().endswith(".pdf"):
                        return urljoin(artlink, href)
                    #in case its not in a <p> tag and instead in a seperate <a> tag
                    else:
                        for a in soup.find_all("a"):
                            link_text = a.get_text(strip=True).lower()
                            href = a.get("href", "")
                            if "download" in link_text:
                                return href


    if not found_match:
        print(f"No Patent ID match for: {patentID}")
        return None

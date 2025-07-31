from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import json

from extract_contest_title import contest_title
from PDF_path import pdf_path

# Set up headless Chrome browser
options = Options()

options.add_argument("--headless")
options.add_argument("--window-size=1920,1080")
driver = webdriver.Chrome(options=options)

# Open the page
url = "https://patroll.unifiedpatents.com/contests?category=won"
driver.get(url)

# Initialize lists to store contest data
patentID = []
pdfpath = []
#all pdfpath stuff can be removed later but is there now to check if the code is working.
priorartPDF_1 = []
priorartPDF_1a = []
contestTitles = []
contestLinks = []

prefix = 'https://www.google.com'
contestlink = 'https://patroll.unifiedpatents.com/'
max_pages = 10

# Create driver just for going into different webpages and scraping stuff, other driver is used for getting contest links
options = Options()

options.add_argument("--headless")
options.add_argument("--window-size=1920,1080")
scraper = webdriver.Chrome(options=options)

#loops through all the pages
try:
    for page_num in range(1, max_pages + 1):
        print(f"Processing page {page_num}...")

        time.sleep(1)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Locate each contest
        ul = soup.find("ul", class_="ant-list-items")

        if ul:
            # Find the links each sections goes to
            temp = [a['href'] for a in ul.find_all('a', href=True)]

            contest_link = ["https://patroll.unifiedpatents.com" + link for link in temp if
                            link.startswith('/contests/')]
            contestLinks.extend(contest_link)

            # Leaves only google patent links
            patent_links = [link[31:] for link in temp if link.startswith(prefix)]
            patentID.extend(patent_links)

        else:
            break

        # finds the contest titles, the winning art PDFs and eventually the 1 and 1a section form the PDF
        num = 1
        for num, (a, pid) in enumerate(zip(contest_link, patent_links), start=1):
            print(num, a)
            contestTitles.append(contest_title(a, scraper))
            #this is to record the PDF links but it doesn't have to stay in the final version.
            path = pdf_path(a, pid, scraper)  # pass contest page + matching patent ID
            print(pdf_path)
            pdfpathL.append(pdf_path)

            #when PDF scraper is finished we can record that info here
            """try:
                priorartPDF_1.append(pdf_link(a, scraper))
            except:
                priorartPDF_1.append(0)
            try:
                priorartPDF_1a.append(prior_art(a, scraper))
            except:
                priorartPDF_1a.append(0)"""

            num += 1

        # Clicks the next page and begins to repeat the same process
        try:
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "li.ant-pagination-next[title='Next Page']"))
            )
            driver.execute_script("arguments[0].scrollIntoView();", next_button)
            driver.execute_script("arguments[0].click();", next_button)
            print("Clicked the 'Next Page' button")
        except Exception as e:
            print(f"Could not find/click 'Next Page' button: {e}")
            break

finally:
    driver.quit()
    scraper.quit()

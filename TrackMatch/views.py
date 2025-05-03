import os
import time
import logging
import traceback
from django.http import JsonResponse
from django.views import View
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from selenium.common.exceptions import WebDriverException
import asyncio

logger = logging.getLogger(__name__)

def run_scraper():
    LOGIN_URL = os.getenv("SCRAPER_URL")
    PASSWORD = os.getenv("SCRAPER_PASSWORD")
    MAX_PAGES = int(os.getenv("MAX_PAGES", 5))
    TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", 15))

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--no-first-run")
    options.add_argument("--mute-audio")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    data = []

    try:
        driver.get(LOGIN_URL)

        # Wait for login password field and enter password
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
        ).send_keys(PASSWORD)

        driver.find_element(By.XPATH, "//button[contains(text(), 'Sign in')]").click()

        # Wait for table to load after login
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".display.view-imeis-table tbody tr"))
        )

        # Change items per page to 100
        try:
            select_element = driver.find_element(By.CSS_SELECTOR, "select[name='DataTables_Table_0_length']")
            driver.execute_script(
                "arguments[0].value = '100'; arguments[0].dispatchEvent(new Event('change'))",
                select_element
            )

            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".display.view-imeis-table tbody tr"))
            )
        except Exception:
            logger.warning("Failed to change table length to 100; continuing with default")

        # Scrape all table pages
        for page in range(MAX_PAGES):
            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select(".display.view-imeis-table tbody tr")

            if not rows:
                break

            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 6:
                    data.append({
                        "date": cols[3].text.strip(),
                        "product_name": cols[1].text.strip(),
                        "price": cols[2].text.strip(),
                        "tracking": cols[5].text.strip()
                    })

            try:
                next_btn = driver.find_element(By.ID, "DataTables_Table_0_next")
                if "disabled" in next_btn.get_attribute("class"):
                    break

                first_row = driver.find_element(By.CSS_SELECTOR, ".display.view-imeis-table tbody tr")
                driver.execute_script("arguments[0].click();", next_btn)
                WebDriverWait(driver, 3).until(EC.staleness_of(first_row))

            except Exception:
                break

        return data

    except Exception as e:
        logger.error(f"Scraper failed: {str(e)}")
        logger.error(traceback.format_exc())
        return []

    finally:
        driver.quit()

def run_scraper_with_retries(retries=3):
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"Scraper attempt {attempt}")
            result = run_scraper()
            if result:
                return result
        except WebDriverException as e:
            if "tab crashed" in str(e).lower():
                logger.warning("Chrome tab crashed. Retrying...")
            else:
                logger.error("WebDriver error (non-tab crash):")
                logger.error(traceback.format_exc())
                break
        except Exception as e:
            logger.error("Unexpected error during scraping:")
            logger.error(traceback.format_exc())
            break
        time.sleep(2)
    return []

class AsyncScraperView(View):
    async def get(self, request, *args, **kwargs):
        loop = asyncio.get_running_loop()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                data = await loop.run_in_executor(executor, run_scraper_with_retries)

            if data:
                return JsonResponse({'status': 'success', 'data': data}, status=200)
            else:
                return JsonResponse({'status': 'error', 'message': 'No data found'}, status=404)

        except Exception as e:
            logger.error(f"View failed: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({'status': 'error', 'message': 'Internal server error'}, status=500)

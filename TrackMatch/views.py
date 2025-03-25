import os
import logging
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
import asyncio
import traceback

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
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    data = []

    try:
        driver.get(LOGIN_URL)
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
        ).send_keys(PASSWORD)

        driver.find_element(By.XPATH, "//button[contains(text(), 'Sign in')]").click()

        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".display.view-imeis-table tbody tr"))
        )

        select_element = driver.find_element(By.CSS_SELECTOR, "select[name='DataTables_Table_0_length']")
        driver.execute_script(
            "arguments[0].value = '100'; arguments[0].dispatchEvent(new Event('change'))",
            select_element
        )

        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".display.view-imeis-table tbody tr"))
        )

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

class AsyncScraperView(View):
    async def get(self, request, *args, **kwargs):
        loop = asyncio.get_running_loop()

        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                data = await loop.run_in_executor(executor, run_scraper)

            if data:
                return JsonResponse({'status': 'success', 'data': data}, status=200)
            else:
                return JsonResponse({'status': 'error', 'message': 'No data found'}, status=404)

        except Exception as e:
            logger.error(f"View failed: {str(e)}")
            return JsonResponse({'status': 'error', 'message': 'Internal server error'}, status=500)

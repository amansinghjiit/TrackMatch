import os
import time
import logging
import traceback
from django.http import JsonResponse
from django.views import View
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
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
    TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", 20))

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.page_load_strategy = "normal"

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    data = []

    try:
        driver.get(LOGIN_URL)

        try:
            password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
            )
            password_input.send_keys(PASSWORD)

            driver.find_element(
                By.XPATH,
                "//button[contains(., 'Sign') or contains(., 'Login')]"
            ).click()
        except:
            pass

        WebDriverWait(driver, TIMEOUT).until(
            EC.visibility_of_all_elements_located((By.CSS_SELECTOR, "table.display tbody tr"))
        )

        time.sleep(2)

        try:
            select_element = Select(driver.find_element(By.TAG_NAME, "select"))
            select_element.select_by_visible_text("100")
            time.sleep(2)
        except:
            pass

        for _ in range(MAX_PAGES):
            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select("table.display tbody tr")

            if not rows:
                break

            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 6:
                    data.append({
                        "date": cols[3].get_text(strip=True),
                        "product_name": cols[1].get_text(strip=True),
                        "price": cols[2].get_text(strip=True),
                        "tracking": cols[5].get_text(strip=True)
                    })

            try:
                next_btn = driver.find_element(
                    By.XPATH,
                    "//a[contains(@class,'next')]"
                )

                if "disabled" in next_btn.get_attribute("class").lower():
                    break

                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(2)

            except:
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
                logger.error(traceback.format_exc())
                break
        except Exception:
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
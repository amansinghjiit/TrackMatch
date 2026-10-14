
import os
import time
import logging
import traceback
import asyncio

from concurrent.futures import ThreadPoolExecutor

from django.http import JsonResponse
from django.views import View

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    WebDriverException,
    TimeoutException,
    StaleElementReferenceException,
)

from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager


logger = logging.getLogger(__name__)


def run_scraper():
    LOGIN_URL = os.getenv("SCRAPER_URL")
    PASSWORD = os.getenv("SCRAPER_PASSWORD")
    MAX_PAGES = int(os.getenv("MAX_PAGES", 5))
    TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", 20))

    if not LOGIN_URL:
        logger.error("SCRAPER_URL environment variable is missing")
        return []

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,800")
    options.page_load_strategy = "normal"

    driver = None
    data = []

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
        )

        driver.get(LOGIN_URL)

        # Login, if the password field is present.
        try:
            password_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input[type='password']")
                )
            )

            if not PASSWORD:
                raise ValueError("SCRAPER_PASSWORD is missing")

            password_input.send_keys(PASSWORD)

            login_button = driver.find_element(
                By.XPATH,
                "//button[contains(., 'Sign') or contains(., 'Login')]"
            )
            login_button.click()

        except TimeoutException:
            # Password field not found; possibly already logged in.
            logger.info("Password field not found; checking current page")

        # Wait for the product table.
        WebDriverWait(driver, TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table.display tbody")
            )
        )

        # Try to display 100 records per page.
        try:
            select_element = Select(
                driver.find_element(By.TAG_NAME, "select")
            )
            select_element.select_by_visible_text("100")

            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "table.display tbody tr")
                )
            )
        except Exception:
            logger.info("Could not select 100 rows; using current page size")

        for page_number in range(MAX_PAGES):
            # Wait until the table is present before parsing.
            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "table.display tbody")
                )
            )

            soup = BeautifulSoup(driver.page_source, "html.parser")
            rows = soup.select("table.display tbody tr")

            if not rows:
                logger.warning("No rows found on page %s", page_number + 1)
                break

            for row in rows:
                cols = row.find_all("td", recursive=False)

                # Ignore empty rows or DataTables placeholder rows.
                if not cols:
                    continue

                # Updated price selector from the new website HTML.
                price_cell = row.select_one("td.bk-amount")

                price = (
                    price_cell.get_text(" ", strip=True)
                    if price_cell
                    else ""
                )

                # Log missing prices to help diagnose future changes.
                if not price_cell:
                    logger.warning(
                        "Price cell missing. Row HTML: %s",
                        str(row)[:1000],
                    )

                # The supplied table has columns:
                # 0: #, 1: Product, 2: Price,
                # 3: Date, 4: IMEI, 5: Tracking, 6: Action
                if len(cols) >= 6:
                    data.append({
                        "date": cols[3].get_text(" ", strip=True),
                        "product_name": cols[1].get_text(" ", strip=True),
                        "price": price,
                        "tracking": cols[5].get_text(" ", strip=True),
                    })

            logger.info(
                "Page %s scraped; total records: %s",
                page_number + 1,
                len(data),
            )

            if page_number + 1 >= MAX_PAGES:
                break

            # Find the next-page control.
            try:
                next_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "a.next"
                )

                classes = (next_btn.get_attribute("class") or "").lower()
                aria_disabled = (
                    next_btn.get_attribute("aria-disabled") or ""
                ).lower()

                if (
                    "disabled" in classes
                    or aria_disabled == "true"
                ):
                    break

                # Wait for the old table rows to become stale.
                old_rows = driver.find_elements(
                    By.CSS_SELECTOR,
                    "table.display tbody tr"
                )
                old_first_row = old_rows[0] if old_rows else None

                driver.execute_script("arguments[0].click();", next_btn)

                if old_first_row:
                    try:
                        WebDriverWait(driver, TIMEOUT).until(
                            EC.staleness_of(old_first_row)
                        )
                    except TimeoutException:
                        logger.info(
                            "Table row did not become stale after pagination"
                        )

                time.sleep(0.5)

            except (WebDriverException, StaleElementReferenceException):
                logger.info("No usable next-page button; stopping pagination")
                break

        return data

    except Exception as e:
        logger.error("Scraper failed: %s", str(e))
        logger.error(traceback.format_exc())
        return []

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                logger.warning("Could not close WebDriver cleanly")


def run_scraper_with_retries(retries=3):
    for attempt in range(1, retries + 1):
        try:
            logger.info("Scraper attempt %s/%s", attempt, retries)

            result = run_scraper()

            if result:
                return result

            logger.warning("Scraper returned no records")

        except WebDriverException:
            logger.error(
                "WebDriver error on attempt %s:\n%s",
                attempt,
                traceback.format_exc(),
            )

        except Exception:
            logger.error(
                "Unexpected error on attempt %s:\n%s",
                attempt,
                traceback.format_exc(),
            )
            break

        if attempt < retries:
            time.sleep(2)

    return []


class AsyncScraperView(View):
    async def get(self, request, *args, **kwargs):
        loop = asyncio.get_running_loop()

        try:
            # Run Selenium outside Django's async event loop.
            with ThreadPoolExecutor(max_workers=1) as executor:
                data = await loop.run_in_executor(
                    executor,
                    run_scraper_with_retries,
                )

            if data:
                return JsonResponse({
                    "status": "success",
                    "data": data,
                }, status=200)

            return JsonResponse({
                "status": "error",
                "message": "No data found",
            }, status=404)

        except Exception as e:
            logger.error("View failed: %s", str(e))
            logger.error(traceback.format_exc())

            return JsonResponse({
                "status": "error",
                "message": "Internal server error",
            }, status=500)

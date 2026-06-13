"""
Data ingestion tool for Vietnamese legal documents (vbpl.vn).
"""

import os
import json
import time
import argparse
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
)
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from src.utils.log import get_logger
from src.utils.config_loader import get_config   # use existing function

logger = get_logger("crawler")


class DataIngestionTool:
    def __init__(self, web_link: str = "https://vbpl.vn/pages/portal.aspx"):
        self.webpage_link = web_link
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service)
            logger.info("WebDriver initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            self.driver = None

    def _wait_for_list(self, timeout: int = 15) -> list:
        WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "ul.ant-list-items li.ant-list-item")
            )
        )
        return self.driver.find_elements(
            By.CSS_SELECTOR, "ul.ant-list-items li.ant-list-item"
        )

    def _get_detail_url_and_content(self, li_index: int, list_url: str) -> dict:
        items = self.driver.find_elements(By.CSS_SELECTOR, "ul.ant-list-items li.ant-list-item")
        if li_index >= len(items):
            return {}

        item = items[li_index]
        original_handles = self.driver.window_handles

        span = item.find_element(By.CSS_SELECTOR, "span.block.cursor-pointer")
        self.driver.execute_script("arguments[0].click();", span)

        metadata = {}
        detail_url = ""
        content = ""

        try:
            WebDriverWait(self.driver, 10).until(
                lambda d: len(d.window_handles) > len(original_handles)
            )
            new_handle = [h for h in self.driver.window_handles if h not in original_handles][0]
            self.driver.switch_to.window(new_handle)

            detail_url = self.driver.current_url
            WebDriverWait(self.driver, 15).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(1)

            content = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'preview-content')]"))
            ).text.strip()

            try:
                luoc_do_tab = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-node-key='luoc-do']"))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", luoc_do_tab)
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", luoc_do_tab)

                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.ant-descriptions-view"))
                )
                try:
                    title = self.driver.find_element(
                        By.CSS_SELECTOR, "div.border-solid span.whitespace-pre-wrap"
                    ).text.strip()
                    metadata["Tên văn bản"] = title
                except:
                    pass

                rows = self.driver.find_elements(By.CSS_SELECTOR, "div.ant-descriptions-item-container")
                for row in rows:
                    try:
                        label = row.find_element(By.CSS_SELECTOR, "span.ant-descriptions-item-label").text.strip()
                        value = row.find_element(By.CSS_SELECTOR, "span.ant-descriptions-item-content").text.strip()
                        metadata[label] = value
                    except NoSuchElementException:
                        continue
            except Exception as e:
                logger.warning(f"Failed to extract metadata from 'luoc-do' tab: {e}")

        except Exception as e:
            logger.error(f"Error processing document: {e}")
        finally:
            if len(self.driver.window_handles) > len(original_handles):
                self.driver.close()
            self.driver.switch_to.window(original_handles[0])
            self._wait_for_list(timeout=20)

        metadata["url"] = detail_url
        metadata["nội dung"] = content
        logger.info(f"Processed document: {detail_url} ({len(content)} characters)")
        return metadata

    def _click_next_page(self) -> bool:
        try:
            next_btn = self.driver.find_element(
                By.XPATH, "//button[contains(@class, 'CustomPagination_paginationButton')]//span[text()='Sau']/.."
            )
            if next_btn.get_attribute("aria-disabled") == "true":
                return False

            try:
                current_page = self.driver.find_element(
                    By.CSS_SELECTOR, "li.ant-pagination-item-active"
                ).text.strip()
            except NoSuchElementException:
                current_page = "-1"

            self.driver.execute_script("arguments[0].click();", next_btn)
            logger.info("Moving to next page...")

            try:
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, "li.ant-pagination-item-active").text.strip() != current_page
                )
            except TimeoutException:
                logger.info("Page number unchanged - reached last page.")
                return False

            self._wait_for_list(timeout=15)
            return True

        except NoSuchElementException:
            return False

    def ingest_data(self, keyword: str, output_dir: str, limit_page: int = 999):
        if not self.driver:
            logger.error("WebDriver not initialized. Aborting.")
            return

        self.driver.get(self.webpage_link)
        keyword = keyword.strip()
        all_documents = []
        logger.info(f'Starting search: "{keyword}"')

        try:
            search_box = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "keyword"))
            )
            search_box.clear()
            search_box.send_keys(keyword)
            search_box.send_keys(Keys.ENTER)

            WebDriverWait(self.driver, 20).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "[class^='SearchResultsSummary_text'] strong").text != "0 văn bản"
            )

            count_el = self.driver.find_element(By.CSS_SELECTOR, "[class^='SearchResultsSummary_text'] strong")
            number_of_results = int(count_el.text.replace(" văn bản", "").replace(".", "").strip())
            logger.info(f"Found {number_of_results} documents.")
            if number_of_results == 0:
                return

        except TimeoutException:
            logger.warning(f"No results for keyword '{keyword}' or page load timeout.")
            return
        except Exception as e:
            logger.error(f"Search error: {e}")
            return

        page_number = 1
        while True:
            try:
                list_url = self.driver.current_url
                li_elements = self._wait_for_list()
                logger.info(f"Processing page {page_number} – {len(li_elements)} results")

                page_data = []
                for idx in range(len(li_elements)):
                    logger.info(f"  [{idx+1}/{len(li_elements)}]")
                    try:
                        li_elements = self.driver.find_elements(By.CSS_SELECTOR, "ul.ant-list-items li.ant-list-item")

                        try:
                            status = li_elements[idx].find_element(
                                By.CSS_SELECTOR, "span.text-xs.white-space-nowrap"
                            ).text.strip()
                            if status == "Hết hiệu lực toàn bộ":
                                logger.info("  Document fully expired – skipping")
                                continue
                        except NoSuchElementException:
                            pass

                        try:
                            title = li_elements[idx].find_element(
                                By.CSS_SELECTOR, "div.DocumentCard_documentTitle__aE_F_"
                            ).text.strip().lower()
                            allowed_types = ["luật", "sửa đổi"]
                            if not any(t in title for t in allowed_types):
                                logger.info("  Document type not required – skipping")
                                continue
                        except NoSuchElementException:
                            continue

                        doc = self._get_detail_url_and_content(idx, list_url)
                        if doc:
                            logger.info(f"    {doc.get('Tên văn bản', '')[:60]}...")
                            page_data.append(doc)
                    except StaleElementReferenceException:
                        logger.warning(f"Stale element at index {idx}, retrying...")
                        li_elements = self._wait_for_list()
                    except Exception as e:
                        logger.error(f"Error processing index {idx}: {e}")

                all_documents.extend(page_data)
                self._save_to_json(all_documents, keyword, output_dir)

                if page_number >= limit_page:
                    logger.info("Reached page limit.")
                    break

                if not self._click_next_page():
                    logger.info("Finished all pages.")
                    break

                page_number += 1
                time.sleep(0.5)

            except NoSuchElementException as e:
                logger.info(f"Reached end of results: {e}")
                break

        self._save_to_json(all_documents, keyword, output_dir)

    def _save_to_json(self, data: list, keyword: str, output_dir: str):
        if not data:
            logger.info("No data to save.")
            return

        os.makedirs(output_dir, exist_ok=True)
        safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (" ", "_")).rstrip()
        filename = f"metadata_law_{safe_keyword.replace(' ', '_')}.json"
        json_path = os.path.join(output_dir, filename)

        df = pd.DataFrame(data)
        before = len(df)
        df = df[df["Tên văn bản"].notna() & (df["Tên văn bản"] != "") &
                df["nội dung"].notna() & (df["nội dung"] != "")]
        logger.info(f"Removed {before - len(df)} records with missing title/content.")

        if "url" in df.columns:
            df = df.drop_duplicates(subset=["url"])
        else:
            logger.warning("Column 'url' not found – skipping duplicate removal.")

        df.to_json(json_path, orient="records", force_ascii=False, indent=4)
        logger.info(f"Saved {len(df)} documents to {json_path}")

    def quit(self):
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed.")


def merge_json_files(file_paths: list[str], output_path: str):
    all_data = []
    for path in file_paths:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            all_data.extend(data)
            logger.info(f"Loaded {len(data)} records from {path}")

    logger.info(f"Total before deduplication: {len(all_data)}")
    df = pd.DataFrame(all_data)
    if "url" in df.columns:
        df = df.drop_duplicates(subset=["url"])
    else:
        logger.warning("Column 'url' not found – cannot deduplicate.")
    df.to_json(output_path, orient="records", force_ascii=False, indent=4)
    logger.info(f"Saved {len(df)} unique documents to {output_path}")


def main(config_path: str):
    config = get_config(config_path)          # from existing config_loader
    crawl_cfg = config.get("crawl", {})
    keywords = crawl_cfg.get("search_keywords", [])
    output_dir_rel = crawl_cfg.get("output_dir", "data/legal_document")
    limit_page = crawl_cfg.get("limit_page", 300)
    web_link = crawl_cfg.get("webpage_link", "https://vbpl.vn/pages/portal.aspx")

    project_root = Path(__file__).resolve().parent.parent.parent
    output_dir_abs = project_root / output_dir_rel

    logger.info(f"Starting crawler with config from {config_path}")
    logger.info(f"Keywords: {keywords}")
    logger.info(f"Output directory: {output_dir_abs}")

    ingestion_tool = DataIngestionTool(web_link=web_link)
    try:
        if ingestion_tool.driver:
            for kw in keywords:
                ingestion_tool.ingest_data(
                    keyword=kw,
                    output_dir=str(output_dir_abs),
                    limit_page=limit_page
                )
    finally:
        ingestion_tool.quit()

    import glob
    json_files = glob.glob(str(output_dir_abs / "metadata_law_*.json"))
    if json_files:
        merge_json_files(
            file_paths=json_files,
            output_path=str(output_dir_abs / "metadata_law_ALL.json")
        )
    else:
        logger.warning("No JSON files found to merge.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl legal documents from vbpl.vn")
    parser.add_argument(
        "--config_file",
        type=str,
        required=True,
        help="Path to YAML configuration file (e.g., config/data_preprocessing/crawl_config.yml)"
    )
    args = parser.parse_args()
    main(args.config_file)

    # python -m src.pipelines.crawling.main --config_file=config/data_preprocessing/crawl_config.yml
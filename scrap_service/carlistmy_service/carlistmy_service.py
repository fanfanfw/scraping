import os
import time
import logging
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from .database import get_connection
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

INPUT_FILE = "scrap_service/carlistmy_service/storage/input_files/carlistMY_scraplist.csv"

class CarlistMyService:
    def __init__(self):
        # kita akan inisialisasi manual melalui init_driver()
        self.driver = None
        self.stop_flag = False
        self.conn = get_connection()
        self.cursor = self.conn.cursor()
        
        # Pengaturan batch
        self.batch_size = 25   
        self.listing_count = 0  

    def init_driver(self):
        logging.info("Menginisialisasi ChromeDriver...")

        # Kita siapkan ChromeOptions
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920x1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Di Selenium 4, kita bisa set capability via set_capability:
        options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
        # Boleh juga menambahkan capability lain di sini.

        # Set page load timeout nanti kita panggil setelah driver terbentuk
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        # Page load timeout
        self.driver.set_page_load_timeout(120)

        logging.info("ChromeDriver berhasil diinisialisasi.")

    def quit_driver(self):
        """Menutup driver untuk membebaskan resource."""
        if self.driver:
            logging.info("Menutup ChromeDriver...")
            try:
                self.driver.quit()
                logging.info("ChromeDriver berhasil ditutup.")
            except Exception as e:
                logging.error(f"Gagal menutup ChromeDriver: {e}")
            self.driver = None
            
    def log_browser_console(self):
        """Log pesan console dari browser (jika ada)."""
        try:
            logs = self.driver.get_log('browser')
            for entry in logs:
                # entry = {'level': 'INFO', 'message': '...', 'timestamp': 123456789}
                logging.info(f"BROWSER LOG [{entry['level']}]: {entry['message']}")
        except Exception as e:
            logging.error(f"Gagal mengambil browser console logs: {e}")
            
    def debug_dump(self, prefix):
        """Simpan screenshot dan page_source untuk keperluan debugging."""
        timestamp = int(time.time())
        screenshot_name = f"{prefix}_{timestamp}.png"
        html_name = f"{prefix}_{timestamp}.html"

        try:
            self.driver.save_screenshot(screenshot_name)
            logging.info(f"Screenshot disimpan: {screenshot_name}")
        except Exception as e:
            logging.error(f"Gagal mengambil screenshot: {e}")

        try:
            page_source = self.driver.page_source
            with open(html_name, "w", encoding="utf-8") as f:
                f.write(page_source)
            logging.info(f"HTML page source disimpan: {html_name}")
        except Exception as e:
            logging.error(f"Gagal menyimpan HTML page source: {e}")

    def get_listing_urls(self, listing_page_url):
        logging.info(f"📄 Mengambil listing dari: {listing_page_url}")

        if not self.driver:
            self.init_driver()

        try:
            self.driver.get(listing_page_url)
            time.sleep(3)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.ellipsize.js-ellipsize-text"))
            )
            elements = self.driver.find_elements(By.CSS_SELECTOR, "a.ellipsize.js-ellipsize-text")
            urls = list(set(elem.get_attribute("href") for elem in elements if elem.get_attribute("href")))
            logging.info(f"✅ Ditemukan {len(urls)} listing URLs.")

            # [OPSIONAL] Cek log console
            self.log_browser_console()

            return urls

        except Exception as e:
            logging.error(f"❌ Error mengambil listing URLs: {e}")

            # Tangkap screenshot & HTML dump
            self.debug_dump("get_listing_urls_error")

    def scrape_detail(self, detail_url):
        if self.stop_flag:
            logging.info("⚠️ Scraping dihentikan sebelum mengambil detail.")
            return None

        if not self.driver:
            self.init_driver()

        logging.info(f"🔍 Mengambil detail dari: {detail_url}")
        try:
            self.driver.get(detail_url)
            time.sleep(3)
        except Exception as e:
            logging.error(f"Error saat memuat halaman detail {detail_url}: {e}")

            # Tangkap screenshot & HTML dump
            self.debug_dump("scrape_detail_error")

            return None

        # [OPSIONAL] Cek log console
        self.log_browser_console()

        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        def extract(selector):
            element = soup.select_one(selector)
            return element.text.strip() if element else None

        brand = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--breadcrumb.u-margin-top-xs.u-hide\\@mobile.js-part-breadcrumb > div > ul > li:nth-child(3) > a > span")
        model = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--breadcrumb.u-margin-top-xs.u-hide\\@mobile.js-part-breadcrumb > div > ul > li:nth-child(4) > a > span")
        variant = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--breadcrumb.u-margin-top-xs.u-hide\\@mobile.js-part-breadcrumb > div > ul > li:nth-child(5) > a > span")

        informasi_iklan = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--masthead.u-margin-ends-lg.u-margin-ends-sm\\@mobile.u-order-2\\@mobile > div > div > div:nth-child(1) > span.u-color-muted.u-text-7.u-hide\@mobile")
        
        lokasi_part1 = extract("#listing-detail > section:nth-child(2) > div > div > div.c-sidebar.c-sidebar--top.u-width-2\\/6.u-width-1\\@mobile.u-padding-right-sm.u-padding-left-md.u-padding-top-md.u-padding-top-none\\@mobile.u-flex.u-flex--column.u-flex--column\\@mobile.u-order-first\\@mobile > div.c-card.c-card--ctr.u-margin-ends-sm.u-order-last\\@mobile > div.c-card__body > div.u-flex.u-align-items-center > div > div > span:nth-child(2)")
        lokasi_part2 = extract("#listing-detail > section:nth-child(2) > div > div > div.c-sidebar.c-sidebar--top.u-width-2\\/6.u-width-1\\@mobile.u-padding-right-sm.u-padding-left-md.u-padding-top-md.u-padding-top-none\\@mobile.u-flex.u-flex--column.u-flex--column\\@mobile.u-order-first\\@mobile > div.c-card.c-card--ctr.u-margin-ends-sm.u-order-last\\@mobile > div.c-card__body > div.u-flex.u-align-items-center > div > div > span:nth-child(3)")
        lokasi = " ".join(filter(None, [lokasi_part1, lokasi_part2]))

        gambar_container = soup.select_one("#details-gallery > div > div")
        gambar = []
        if gambar_container:
            img_tags = gambar_container.find_all("img")
            for img in img_tags:
                src = img.get("src")
                if src:
                    gambar.append(src)

        price = extract("#details-gallery > div > div > div.c-gallery--hero-img.u-relative > div.c-gallery__item > div.c-gallery__item-details.u-padding-lg.u-padding-md\\@mobile.u-absolute.u-bottom-right.u-bottom-left.u-zindex-1 > div > div.listing__item-price > h3")

        year = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--key-details.u-margin-ends-lg.u-margin-ends-sm\\@mobile.u-order-3\\@mobile > div > div > div > div > div.owl-stage-outer > div > div:nth-child(2) > div > div > div > span.u-text-bold.u-block")
        millage = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--key-details.u-margin-ends-lg.u-margin-ends-sm\\@mobile.u-order-3\\@mobile > div > div > div > div > div.owl-stage-outer > div > div:nth-child(3) > div > div > div > span.u-text-bold.u-block")
        transmission = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--key-details.u-margin-ends-lg.u-margin-ends-sm\\@mobile.u-order-3\\@mobile > div > div > div > div > div.owl-stage-outer > div > div:nth-child(6) > div > div > div > span.u-text-bold.u-block")
        seat_capacity = extract("#listing-detail > section.c-section--content.u-bg-white.u-padding-top-md.u-padding-bottom-xs.u-flex\\@mobile.u-flex--column\\@mobile > section.c-section.c-section--key-details.u-margin-ends-lg.u-margin-ends-sm\\@mobile.u-order-3\\@mobile > div > div > div > div > div.owl-stage-outer > div > div:nth-child(7) > div > div > div > span.u-text-bold.u-block")

        detail = {
            "listing_url": detail_url,
            "brand": brand,
            "model": model,
            "variant": variant,
            "informasi_iklan": informasi_iklan,
            "lokasi": lokasi,
            "price": price,
            "year": year,
            "millage": millage,
            "transmission": transmission,
            "seat_capacity": seat_capacity,
            "gambar": gambar
        }
        return detail

    def scrape_all_brands(self, start_brand=None, start_page=1):
        """Scrape semua brand berdasarkan file CSV dengan opsi batch untuk meminimalkan penggunaan memori."""
        try:
            self.reset_scraping()
            df = pd.read_csv(INPUT_FILE)
            start_scraping = False if start_brand else True
            
            for _, row in df.iterrows():
                brand = row["brand"]
                base_brand_url = row["url"]
                
                if not start_scraping:
                    if brand == start_brand:
                        start_scraping = True
                    else:
                        continue  
                
                logging.info(f"🚀 Mulai scraping brand: {brand}")
                page_number = start_page if brand == start_brand else 1
                
                while not self.stop_flag:
                    # lalu kita ganti dengan page_number sekarang
                    paginated_url = re.sub(r"(page_number=)\d+", lambda m: m.group(1) + str(page_number), base_brand_url)
                    logging.info(f"📄 Scraping halaman {page_number}: {paginated_url}")
                    
                    listing_urls = self.get_listing_urls(paginated_url)
                    if not listing_urls:
                        logging.info(f"✅ Tidak ditemukan listing URLs pada halaman {page_number}. Menghentikan scraping brand: {brand}")
                        break
                    
                    for listing_url in listing_urls:
                        if self.stop_flag:
                            break

                        detail = self.scrape_detail(listing_url)
                        if detail:
                            self.save_to_db(detail)
                            self.listing_count += 1

                            # Jika sudah mencapai batch_size, reinit driver
                            if self.listing_count >= self.batch_size:
                                logging.info(f"Batch {self.batch_size} listing tercapai, reinit driver...")
                                self.quit_driver()
                                time.sleep(2)  # Jeda agar resource benar-benar bebas
                                self.init_driver()
                                self.listing_count = 0

                    page_number += 1
            
            logging.info("✅ Proses scraping semua brand selesai.")
        except Exception as e:
            logging.error(f"❌ Error saat scraping semua brand: {e}")
        finally:
            # Pastikan driver ditutup pada akhirnya
            self.quit_driver()

    def stop_scraping(self):
        logging.info("⚠️ Permintaan untuk menghentikan scraping diterima.")
        self.stop_flag = True

    def reset_scraping(self):
        self.stop_flag = False
        self.listing_count = 0
        logging.info("🔄 Scraping direset dan siap dimulai kembali.")

    def save_to_db(self, car_data):
        """Menyimpan atau memperbarui data mobil ke database PostgreSQL."""
        try:
            select_query = "SELECT id FROM cars WHERE listing_url = %s"
            self.cursor.execute(select_query, (car_data['listing_url'],))
            result = self.cursor.fetchone()

            if result:  # Data sudah ada, update
                update_query = """
                    UPDATE cars
                    SET price = %s, informasi_iklan = %s, lokasi = %s, year = %s, millage = %s,
                         transmission = %s, seat_capacity = %s, gambar = %s,
                        last_scraped_at = CURRENT_TIMESTAMP, version = version + 1
                    WHERE listing_url = %s
                """
                self.cursor.execute(update_query, (
                    car_data['price'], car_data['informasi_iklan'], car_data['lokasi'],
                    car_data['year'], car_data['millage'],
                    car_data['transmission'], car_data['seat_capacity'], car_data['gambar'],
                    car_data['listing_url']
                ))
            else:  # Data belum ada, insert
                insert_query = """
                    INSERT INTO cars (listing_url, brand, model, variant, informasi_iklan, lokasi, price,
                                    year, millage, transmission, seat_capacity, gambar)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                self.cursor.execute(insert_query, (
                    car_data['listing_url'], car_data['brand'], car_data['model'], car_data['variant'],
                    car_data['informasi_iklan'], car_data['lokasi'], car_data['price'], car_data['year'],
                    car_data['millage'], car_data['transmission'],
                    car_data['seat_capacity'], car_data['gambar']
                ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logging.error(f"❌ Error menyimpan atau memperbarui data ke database: {e}")

    def close(self):
        """Menutup driver dan koneksi database."""
        self.quit_driver()
        self.cursor.close()
        self.conn.close()
        logging.info("Koneksi database ditutup, driver Selenium ditutup.")

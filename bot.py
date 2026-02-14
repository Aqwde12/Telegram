import time
import random
import requests
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import json

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8")
ADMIN_ID = os.environ.get("ADMIN_ID", "380924486")
AVITO_URL = "https://www.avito.ru/all/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?cd=1&s=104"
MIN_PRICE = 0
MAX_PRICE = 2300
CHECK_DELAY = 60
SEEN_FILE = "seen_ads.txt"
# ================================

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": ADMIN_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.get(url, params=params, timeout=10)
    except:
        pass

def create_driver():
    """Создает драйвер в headless-режиме с оптимизациями"""
    chrome_options = Options()
    
    # Headless режим (без окна)
    chrome_options.add_argument("--headless=new")
    
    # Оптимизации для экономии памяти
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # Ограничение памяти
    chrome_options.add_argument("--max_old_space_size=256")
    
    return webdriver.Chrome(options=chrome_options)

def load_seen_ads():
    try:
        with open(SEEN_FILE, "r") as f:
            return set(line.strip() for line in f)
    except:
        return set()

def save_seen_ad(ad_id):
    with open(SEEN_FILE, "a") as f:
        f.write(ad_id + "\n")

def get_ads(driver):
    try:
        driver.get(AVITO_URL)
        time.sleep(5)
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        items = soup.find_all("div", attrs={"data-marker": "item"})
        
        ads = []
        for item in items:
            try:
                title = item.find("a", attrs={"data-marker": "item-title"})
                price = item.find("meta", itemprop="price")
                ad_id = item.get("data-item-id")
                
                if not title or not price or not ad_id:
                    continue
                
                price_val = int(price.get("content", 0))
                if MIN_PRICE <= price_val <= MAX_PRICE:
                    ads.append({
                        "id": ad_id,
                        "title": title.get_text(strip=True),
                        "price": price_val,
                        "link": "https://www.avito.ru" + title["href"]
                    })
            except:
                continue
        return ads
    except:
        return []

def format_ad(ad):
    if ad['price'] < 1000:
        emoji = "💚"
    elif ad['price'] < 1500:
        emoji = "💛"
    else:
        emoji = "❤️"
    
    return f"""
🔔 НОВОЕ ОБЪЯВЛЕНИЕ!

📱 {ad['title']}
{emoji} Цена: {ad['price']} ₽
🔗 {ad['link']}
🕐 {time.strftime('%H:%M')}
"""

def main():
    send_telegram_message("🚀 Бот запущен на Bothost!")
    
    driver = create_driver()
    seen_ads = load_seen_ads()
    
    while True:
        try:
            ads = get_ads(driver)
            
            for ad in ads:
                if ad["id"] not in seen_ads:
                    msg = format_ad(ad)
                    send_telegram_message(msg)
                    seen_ads.add(ad["id"])
                    save_seen_ad(ad["id"])
                    time.sleep(2)
            
            time.sleep(CHECK_DELAY)
            
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
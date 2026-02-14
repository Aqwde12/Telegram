import time
import requests
import os
from bs4 import BeautifulSoup
from datetime import datetime

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8")
ADMIN_ID = os.environ.get("ADMIN_ID", "380924486")

AVITO_URL = os.environ.get("AVITO_URL", "https://www.avito.ru/all/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?cd=1&s=104")

MIN_PRICE = int(os.environ.get("MIN_PRICE", "0"))
MAX_PRICE = int(os.environ.get("MAX_PRICE", "2300"))
CHECK_DELAY = int(os.environ.get("CHECK_DELAY", "60"))

SEEN_FILE = "seen_ads.txt"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}
# ================================

def send_telegram_message(text):
    """Отправляет сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": ADMIN_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        requests.get(url, params=params, timeout=10)
    except:
        pass

def load_seen_ads():
    """Загружает ID просмотренных объявлений"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_seen_ad(ad_id):
    """Сохраняет ID нового объявления"""
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(ad_id + "\n")

def fetch_ad_details(ad_url):
    """Загружает страницу объявления и извлекает описание"""
    try:
        response = requests.get(ad_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Поиск описания - разные варианты селекторов
        description = ""
        
        # Вариант 1: data-marker
        desc_block = soup.find('div', {'data-marker': 'item-view/item-description'})
        if desc_block:
            description = desc_block.get_text(strip=True)
        
        # Вариант 2: класс description
        if not description:
            desc_block = soup.find('div', class_='style-item-description')
            if desc_block:
                description = desc_block.get_text(strip=True)
        
        # Вариант 3: любой блок с большим текстом
        if not description:
            for div in soup.find_all('div'):
                text = div.get_text(strip=True)
                if len(text) > 100 and 'описание' in text.lower():
                    description = text
                    break
        
        # Ограничиваем длину
        if description and len(description) > 800:
            description = description[:800] + "..."
            
        return description if description else "Описание не найдено"
        
    except Exception as e:
        return f"Ошибка загрузки описания"

def parse_avito_ads(html):
    """Парсит объявления из HTML"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', attrs={'data-marker': 'item'})
    
    if not items:
        items = soup.find_all('div', class_='iva-item-root')
    
    ads = []
    for item in items:
        try:
            # ID
            ad_id = (item.get('data-item-id') or 
                    item.get('id') or 
                    str(hash(str(item))))
            
            # Заголовок и ссылка
            title_tag = None
            for selector in [
                ('a', {'data-marker': 'item-title'}),
                ('a', {'itemprop': 'url'}),
                ('a', {'class': 'iva-item-title'})
            ]:
                title_tag = item.find(selector[0], attrs=selector[1])
                if title_tag:
                    break
            
            if not title_tag:
                continue
            
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href', '')
            if link and link.startswith('/'):
                link = 'https://www.avito.ru' + link
            
            # Цена
            price = 0
            meta_price = item.find('meta', {'itemprop': 'price'})
            if meta_price and meta_price.get('content'):
                try:
                    price = int(float(meta_price['content']))
                except:
                    pass
            
            if price == 0:
                price_text = item.get_text()
                digits = ''.join(c for c in price_text if c.isdigit())
                if digits:
                    price = int(digits[:6])
            
            if MIN_PRICE <= price <= MAX_PRICE and price > 0:
                ads.append({
                    'id': ad_id,
                    'title': title,
                    'price': price,
                    'link': link
                })
        except:
            continue
    
    return ads

def format_ad_message(ad, description):
    """Форматирует полное сообщение с объявлением"""
    # Эмодзи цены
    if ad['price'] < 1000:
        price_emoji = "💚"
    elif ad['price'] < 1500:
        price_emoji = "💛"
    else:
        price_emoji = "❤️"
    
    current_time = datetime.now().strftime('%H:%M %d.%m')
    
    # Собираем сообщение
    message = f"""
🔔 <b>НОВОЕ ОБЪЯВЛЕНИЕ НА AVITO!</b>

📱 <b>{ad['title']}</b>
{price_emoji} <b>Цена: {ad['price']} ₽</b>
🔗 <a href="{ad['link']}">Открыть объявление</a>

📝 <b>Описание:</b>
{description}

🕐 {current_time}
"""
    return message

def main():
    """Главная функция"""
    # Просто отправляем одно сообщение о запуске
    send_telegram_message(f"🚀 Бот запущен\n💰 {MIN_PRICE}-{MAX_PRICE}₽\n⏱ {CHECK_DELAY}с")
    
    seen_ads = load_seen_ads()
    
    while True:
        try:
            # Загружаем страницу поиска
            response = requests.get(AVITO_URL, headers=HEADERS, timeout=30)
            response.raise_for_status()
            
            # Парсим объявления
            ads = parse_avito_ads(response.text)
            
            # Проверяем новые
            for ad in ads:
                if ad['id'] not in seen_ads:
                    # Загружаем описание
                    description = fetch_ad_details(ad['link'])
                    
                    # Отправляем полное сообщение
                    message = format_ad_message(ad, description)
                    send_telegram_message(message)
                    
                    # Сохраняем ID
                    seen_ads.add(ad['id'])
                    save_seen_ad(ad['id'])
                    
                    # Пауза между объявлениями
                    time.sleep(3)
            
            # Ждем до следующей проверки
            time.sleep(CHECK_DELAY)
            
        except Exception as e:
            # При ошибке просто ждем и продолжаем
            time.sleep(60)

if __name__ == "__main__":
    main()

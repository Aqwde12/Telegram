import time
import random
import requests
import os
from bs4 import BeautifulSoup
import json
from datetime import datetime

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8")
ADMIN_ID = os.environ.get("ADMIN_ID", "380924486")

# URL для поиска (можно менять через переменные окружения)
AVITO_URL = os.environ.get("AVITO_URL", "https://www.avito.ru/all/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?cd=1&s=104")

# Диапазон цен
MIN_PRICE = int(os.environ.get("MIN_PRICE", "0"))
MAX_PRICE = int(os.environ.get("MAX_PRICE", "2300"))

# Интервал проверки (в секундах)
CHECK_DELAY = int(os.environ.get("CHECK_DELAY", "60"))

# Файл для хранения просмотренных объявлений
SEEN_FILE = "seen_ads.txt"

# Заголовки для имитации браузера
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0'
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
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            print(f"✅ Сообщение отправлено в Telegram")
        else:
            print(f"❌ Ошибка Telegram: {response.status_code}")
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")

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

def fetch_page(url):
    """Загружает страницу и возвращает HTML"""
    try:
        print(f"🌐 Загружаю страницу: {url}")
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        print(f"✅ Страница загружена, размер: {len(response.text)} байт")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка загрузки страницы: {e}")
        return None

def parse_avito_ads(html):
    """Парсит объявления из HTML страницы Avito"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Поиск всех объявлений
    # На Avito объявления обычно находятся в div с data-marker="item"
    items = soup.find_all('div', attrs={'data-marker': 'item'})
    
    print(f"📄 Найдено {len(items)} элементов с data-marker='item'")
    
    # Если не нашли через data-marker, пробуем другие селекторы
    if not items:
        # Пробуем найти по классам
        items = soup.find_all('div', class_='iva-item-root')
        print(f"📄 Найдено {len(items)} элементов с class='iva-item-root'")
    
    ads = []
    
    for item in items:
        try:
            # Поиск ID объявления
            ad_id = None
            if item.get('data-item-id'):
                ad_id = item.get('data-item-id')
            elif item.get('id'):
                ad_id = item.get('id')
            
            # Поиск заголовка и ссылки
            title_tag = None
            # Пробуем разные селекторы для заголовка
            selectors = [
                ('a', {'data-marker': 'item-title'}),
                ('a', {'itemprop': 'url'}),
                ('a', {'class': 'iva-item-title'}),
                ('h3', {'class': 'title'})
            ]
            
            for tag, attrs in selectors:
                title_tag = item.find(tag, attrs=attrs)
                if title_tag:
                    break
            
            if not title_tag:
                continue
            
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href')
            if link:
                if link.startswith('/'):
                    link = 'https://www.avito.ru' + link
                elif not link.startswith('http'):
                    link = 'https://www.avito.ru' + link
            
            # Поиск цены
            price_tag = None
            price_selectors = [
                ('meta', {'itemprop': 'price'}),
                ('span', {'class': 'price'}),
                ('span', {'data-marker': 'item-price'}),
                ('div', {'class': 'iva-item-price'})
            ]
            
            for tag, attrs in price_selectors:
                price_tag = item.find(tag, attrs=attrs)
                if price_tag:
                    break
            
            if not price_tag:
                continue
            
            # Получаем цену
            if price_tag.name == 'meta':
                price_content = price_tag.get('content')
            else:
                price_content = price_tag.get_text(strip=True)
            
            # Очищаем цену от лишних символов
            price_str = ''.join(c for c in price_content if c.isdigit() or c == ' ')
            price_parts = price_str.split()
            if price_parts:
                price = int(price_parts[0])
            else:
                continue
            
            # Проверяем диапазон цен
            if MIN_PRICE <= price <= MAX_PRICE:
                ads.append({
                    'id': ad_id or str(hash(title + link)),
                    'title': title,
                    'price': price,
                    'link': link
                })
                print(f"  ✅ Найдено: {title[:50]}... - {price}₽")
            
        except Exception as e:
            print(f"  ⚠ Ошибка при парсинге элемента: {e}")
            continue
    
    print(f"📊 После фильтрации по цене: {len(ads)} объявлений")
    return ads

def format_ad_message(ad):
    """Форматирует объявление для отправки в Telegram"""
    # Эмодзи для разных цен
    if ad['price'] < 1000:
        price_emoji = "💚"
    elif ad['price'] < 1500:
        price_emoji = "💛"
    else:
        price_emoji = "❤️"
    
    current_time = datetime.now().strftime('%H:%M %d.%m')
    
    return f"""
🔔 <b>НОВОЕ ОБЪЯВЛЕНИЕ!</b>

📱 <b>{ad['title']}</b>
{price_emoji} Цена: <b>{ad['price']} ₽</b>
🔗 <a href="{ad['link']}">Открыть объявление</a>

🕐 {current_time}
"""

def main():
    """Главная функция"""
    print("🚀 Avito Monitor Bot (requests version) запущен")
    print(f"📊 Параметры:")
    print(f"  • Цена: {MIN_PRICE} - {MAX_PRICE} ₽")
    print(f"  • Интервал: {CHECK_DELAY} сек")
    print(f"  • URL: {AVITO_URL[:100]}...")
    
    # Отправляем сообщение о запуске
    start_msg = f"🚀 Бот запущен!\n💰 Цена: {MIN_PRICE}-{MAX_PRICE}₽\n⏱ Интервал: {CHECK_DELAY}с"
    send_telegram_message(start_msg)
    
    seen_ads = load_seen_ads()
    print(f"📂 Загружено {len(seen_ads)} ранее просмотренных объявлений")
    
    # Счетчик для статистики
    check_count = 0
    total_new = 0
    
    while True:
        try:
            check_count += 1
            print(f"\n🔄 Проверка #{check_count} - {datetime.now().strftime('%H:%M:%S')}")
            
            # Загружаем страницу
            html = fetch_page(AVITO_URL)
            if not html:
                print("⏳ Жду 30 секунд перед повторной попыткой...")
                time.sleep(30)
                continue
            
            # Парсим объявления
            ads = parse_avito_ads(html)
            
            # Проверяем новые объявления
            new_ads = []
            for ad in ads:
                if ad['id'] not in seen_ads:
                    new_ads.append(ad)
            
            if new_ads:
                print(f"🎉 Найдено {len(new_ads)} новых объявлений!")
                total_new += len(new_ads)
                
                for ad in new_ads:
                    # Отправляем в Telegram
                    msg = format_ad_message(ad)
                    send_telegram_message(msg)
                    
                    # Сохраняем в файл
                    seen_ads.add(ad['id'])
                    save_seen_ad(ad['id'])
                    
                    # Небольшая задержка между сообщениями
                    time.sleep(2)
            else:
                print(f"✅ Новых объявлений нет")
            
            # Статистика
            print(f"📊 Статистика: всего найдено {total_new}, в файле {len(seen_ads)}")
            
            # Ждем до следующей проверки
            print(f"⏳ Следующая проверка через {CHECK_DELAY} секунд")
            time.sleep(CHECK_DELAY)
            
        except KeyboardInterrupt:
            print("\n👋 Бот остановлен пользователем")
            send_telegram_message("⏹ Бот остановлен")
            break
            
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            send_telegram_message(f"❌ Ошибка: {str(e)[:100]}")
            print("⏳ Перезапуск через 60 секунд...")
            time.sleep(60)

if __name__ == "__main__":
    main()
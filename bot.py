import time
import random
import requests
import os
from bs4 import BeautifulSoup
import json
from datetime import datetime
import traceback

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8")
ADMIN_ID = os.environ.get("ADMIN_ID", "380924486")

# URL для поиска
AVITO_URL = os.environ.get("AVITO_URL", "https://www.avito.ru/all/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?cd=1&s=104")

# Диапазон цен
MIN_PRICE = int(os.environ.get("MIN_PRICE", "0"))
MAX_PRICE = int(os.environ.get("MAX_PRICE", "2300"))

# Интервал проверки (в секундах)
CHECK_DELAY = int(os.environ.get("CHECK_DELAY", "60"))

# Файл для хранения просмотренных объявлений
SEEN_FILE = "seen_ads.txt"

# Включить/выключить подробные логи
DETAILED_LOGS = os.environ.get("DETAILED_LOGS", "True").lower() == "true"

# Заголовки для имитации браузера
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
}
# ================================

# Для отслеживания последних отправленных логов (чтобы не спамить)
_last_log_time = {}
_last_error_hash = None

def send_telegram_message(text, silent=False):
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
            if not silent:
                print(f"✅ Сообщение отправлено в Telegram")
            return True
        else:
            print(f"❌ Ошибка Telegram: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ошибка при отправке в Telegram: {e}")
        return False

def send_log(message, level="INFO"):
    """Отправляет лог в Telegram с эмодзи"""
    emoji = {
        "INFO": "ℹ️",
        "SUCCESS": "✅",
        "WARNING": "⚠️",
        "ERROR": "❌",
        "DEBUG": "🔍",
        "START": "🚀",
        "STOP": "⏹",
        "FOUND": "🎉"
    }.get(level, "📌")
    
    current_time = datetime.now().strftime('%H:%M:%S')
    log_message = f"{emoji} <b>[{current_time}]</b> {message}"
    
    # Для ошибок отправляем всегда, для INFO/Debug - с ограничением частоты
    if level in ["ERROR", "START", "STOP", "FOUND"]:
        send_telegram_message(log_message)
    elif DETAILED_LOGS:
        # Ограничиваем частоту отправки логов (не чаще раза в минуту)
        global _last_log_time
        now = time.time()
        last = _last_log_time.get(level, 0)
        if now - last > 60:  # 60 секунд
            _last_log_time[level] = now
            send_telegram_message(log_message, silent=True)
    
    # В консоль выводим всегда
    print(f"[{current_time}] {level}: {message}")

def send_error(error, context=""):
    """Отправляет детальную информацию об ошибке"""
    global _last_error_hash
    
    error_text = str(error)
    error_hash = hash(error_text + context)
    
    # Не отправляем одну и ту же ошибку слишком часто
    if error_hash == _last_error_hash:
        return
    
    _last_error_hash = error_hash
    
    tb = traceback.format_exc()
    current_time = datetime.now().strftime('%H:%M:%S')
    
    message = f"❌ <b>ОШИБКА</b>\n"
    message += f"🕐 {current_time}\n"
    message += f"📌 {context}\n" if context else ""
    message += f"⚠️ {error_text[:200]}\n"
    message += f"🔍 Подробности в логах"
    
    send_telegram_message(message)
    print(f"❌ Ошибка: {error_text}\n{tb}")

def load_seen_ads():
    """Загружает ID просмотренных объявлений"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            ads = set(line.strip() for line in f)
        send_log(f"Загружено {len(ads)} просмотренных объявлений", "INFO")
        return ads
    except FileNotFoundError:
        send_log("Файл с объявлениями не найден. Будет создан новый.", "INFO")
        return set()
    except Exception as e:
        send_error(e, "Ошибка загрузки файла с объявлениями")
        return set()

def save_seen_ad(ad_id):
    """Сохраняет ID нового объявления"""
    try:
        with open(SEEN_FILE, "a", encoding="utf-8") as f:
            f.write(ad_id + "\n")
    except Exception as e:
        send_error(e, f"Ошибка сохранения объявления {ad_id}")

def fetch_page(url):
    """Загружает страницу и возвращает HTML"""
    try:
        send_log(f"Загрузка страницы: {url[:100]}...", "DEBUG")
        
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        size_kb = len(response.text) / 1024
        send_log(f"Страница загружена ({size_kb:.1f} KB)", "SUCCESS")
        
        return response.text
    except requests.exceptions.Timeout:
        send_log("Таймаут при загрузке страницы", "WARNING")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            send_log("Слишком много запросов. Avito временно заблокировал", "WARNING")
        else:
            send_error(e, f"HTTP ошибка {e.response.status_code}")
        return None
    except Exception as e:
        send_error(e, "Ошибка загрузки страницы")
        return None

def parse_avito_ads(html):
    """Парсит объявления из HTML страницы Avito"""
    if not html:
        return []
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Поиск всех объявлений
        items = soup.find_all('div', attrs={'data-marker': 'item'})
        
        if not items:
            items = soup.find_all('div', class_='iva-item-root')
        
        send_log(f"Найдено элементов на странице: {len(items)}", "DEBUG")
        
        if len(items) == 0:
            send_log("Не удалось найти объявления на странице. Возможно, изменилась структура Avito", "WARNING")
            return []
        
        ads = []
        for i, item in enumerate(items[:30]):  # Ограничим первые 30 для скорости
            try:
                # Поиск ID
                ad_id = (item.get('data-item-id') or 
                        item.get('id') or 
                        f"ad_{i}_{int(time.time())}")
                
                # Поиск заголовка и ссылки
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
                if not title or len(title) < 3:
                    continue
                
                # Формируем ссылку
                link = title_tag.get('href', '')
                if link and link.startswith('/'):
                    link = 'https://www.avito.ru' + link
                elif link and not link.startswith('http'):
                    link = 'https://www.avito.ru/' + link.lstrip('/')
                
                # Поиск цены
                price = 0
                price_tag = None
                
                # Сначала ищем meta-тег
                meta_price = item.find('meta', {'itemprop': 'price'})
                if meta_price and meta_price.get('content'):
                    try:
                        price = int(float(meta_price['content']))
                    except:
                        pass
                
                # Если не нашли, ищем в тексте
                if price == 0:
                    price_selectors = [
                        ('span', {'data-marker': 'item-price'}),
                        ('span', {'class': 'price'}),
                        ('div', {'class': 'iva-item-price'})
                    ]
                    
                    for tag, attrs in price_selectors:
                        price_tag = item.find(tag, attrs=attrs)
                        if price_tag:
                            price_text = price_tag.get_text(strip=True)
                            # Извлекаем цифры
                            digits = ''.join(c for c in price_text if c.isdigit())
                            if digits:
                                price = int(digits)
                                break
                
                # Проверяем диапазон цен
                if MIN_PRICE <= price <= MAX_PRICE and price > 0:
                    ads.append({
                        'id': ad_id,
                        'title': title[:100],  # Ограничим длину
                        'price': price,
                        'link': link
                    })
                    
            except Exception as e:
                send_log(f"Ошибка парсинга элемента {i}: {str(e)[:50]}", "DEBUG")
                continue
        
        send_log(f"После фильтрации: {len(ads)} объявлений в диапазоне {MIN_PRICE}-{MAX_PRICE}₽", "INFO")
        
        if len(ads) == 0 and len(items) > 0:
            # Проверим, есть ли вообще объявления с ценами
            sample_prices = []
            for item in items[:5]:
                price_text = item.get_text()
                digits = ''.join(c for c in price_text if c.isdigit())
                if digits:
                    sample_prices.append(digits[:6])
            if sample_prices:
                send_log(f"Примеры цен на странице: {', '.join(sample_prices)}", "DEBUG")
        
        return ads
        
    except Exception as e:
        send_error(e, "Ошибка парсинга HTML")
        return []

def format_ad_message(ad):
    """Форматирует объявление для отправки в Telegram"""
    # Эмодзи для разных цен
    if ad['price'] < 1000:
        price_emoji = "💚"
    elif ad['price'] < 1500:
        price_emoji = "💛"
    else:
        price_emoji = "❤️"
    
    current_time = datetime.now().strftime('%H:%M')
    
    return f"""
🔔 <b>НОВОЕ ОБЪЯВЛЕНИЕ!</b>

📱 <b>{ad['title']}</b>
{price_emoji} Цена: <b>{ad['price']} ₽</b>
🔗 <a href="{ad['link']}">Открыть объявление</a>

🕐 {current_time}
"""

def send_status_report(seen_ads, total_checked, total_found, uptime):
    """Отправляет отчет о состоянии бота"""
    current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
    
    message = f"""
📊 <b>ОТЧЕТ О РАБОТЕ БОТА</b>
🕐 {current_time}

📈 Статистика:
• Проверок: {total_checked}
• Найдено всего: {total_found}
• В базе: {len(seen_ads)} объявлений
• Uptime: {uptime:.1f} часов

⚙️ Параметры:
• Цена: {MIN_PRICE}-{MAX_PRICE}₽
• Интервал: {CHECK_DELAY} сек
• Детальные логи: {"✅" if DETAILED_LOGS else "❌"}

🔗 <a href="{AVITO_URL}">Ссылка на поиск</a>
"""
    send_telegram_message(message)

def main():
    """Главная функция"""
    start_time = time.time()
    total_checked = 0
    total_found = 0
    
    send_log("🚀 Avito Monitor Bot (requests version) ЗАПУЩЕН", "START")
    send_log(f"Параметры: {MIN_PRICE}-{MAX_PRICE}₽, интервал {CHECK_DELAY}с", "INFO")
    
    seen_ads = load_seen_ads()
    total_found = len(seen_ads)
    
    # Отправляем первый отчет через 5 минут
    last_report_time = time.time()
    
    while True:
        try:
            total_checked += 1
            check_start = time.time()
            
            send_log(f"Проверка #{total_checked} начата", "DEBUG")
            
            # Загружаем страницу
            html = fetch_page(AVITO_URL)
            if not html:
                send_log("Жду 30 секунд перед повторной попыткой...", "WARNING")
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
                send_log(f"НАЙДЕНО {len(new_ads)} НОВЫХ ОБЪЯВЛЕНИЙ!", "FOUND")
                total_found += len(new_ads)
                
                for ad in new_ads:
                    # Отправляем в Telegram
                    msg = format_ad_message(ad)
                    send_telegram_message(msg)
                    
                    # Сохраняем
                    seen_ads.add(ad['id'])
                    save_seen_ad(ad['id'])
                    
                    time.sleep(2)  # Пауза между сообщениями
            else:
                send_log("Новых объявлений нет", "DEBUG")
            
            # Время проверки
            check_time = time.time() - check_start
            send_log(f"Проверка завершена за {check_time:.1f}с", "DEBUG")
            
            # Отправляем отчет каждый час
            if time.time() - last_report_time > 3600:  # 1 час
                uptime = (time.time() - start_time) / 3600
                send_status_report(seen_ads, total_checked, total_found, uptime)
                last_report_time = time.time()
            
            # Ждем до следующей проверки
            next_check = CHECK_DELAY
            send_log(f"Следующая проверка через {next_check}с", "INFO")
            
            # Считаем до следующей проверки с возможностью прерывания
            for i in range(next_check):
                if i % 10 == 0 and i > 0:  # Каждые 10 секунд напоминание
                    send_log(f"До проверки: {next_check - i}с", "DEBUG")
                time.sleep(1)
            
        except KeyboardInterrupt:
            send_log("Бот остановлен пользователем", "STOP")
            uptime = (time.time() - start_time) / 3600
            send_status_report(seen_ads, total_checked, total_found, uptime)
            break
            
        except Exception as e:
            send_error(e, "Критическая ошибка в основном цикле")
            send_log("Перезапуск через 60 секунд...", "WARNING")
            time.sleep(60)

if __name__ == "__main__":
    main()

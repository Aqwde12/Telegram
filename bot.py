import time
import requests
import os
from bs4 import BeautifulSoup
from datetime import datetime
import json
import threading
import logging
from logging.handlers import RotatingFileHandler
import shutil
import re

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8")
ADMIN_ID = os.environ.get("ADMIN_ID", "380924486")

# Файлы для хранения данных
CONFIG_FILE = "bot_config.json"
SEEN_FILE = "seen_ads.txt"
LOG_FILE = "bot_log.txt"

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log_handler = RotatingFileHandler(LOG_FILE, maxBytes=1024*1024, backupCount=5)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger('AvitoBot')
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)

# Конфигурация по умолчанию
DEFAULT_CONFIG = {
    "avito_url": "https://www.avito.ru/all/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?cd=1&s=104",
    "min_price": 0,
    "max_price": 2300,
    "check_delay": 60,
    "is_active": True
}

# Заголовки для запросов
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}

# Глобальные переменные
monitoring_active = False
monitoring_thread = None
# ================================

def log_info(message):
    """Запись информационного сообщения в лог"""
    logger.info(message)
    print(f"ℹ️ {message}")

def log_error(message):
    """Запись ошибки в лог"""
    logger.error(message)
    print(f"❌ {message}")

def log_debug(message):
    """Запись отладочного сообщения в лог"""
    logger.debug(message)
    print(f"🔍 {message}")

def log_warning(message):
    """Запись предупреждения в лог"""
    logger.warning(message)
    print(f"⚠️ {message}")

def log_success(message):
    """Запись успешного действия в лог"""
    logger.info(f"SUCCESS: {message}")
    print(f"✅ {message}")

def load_config():
    """Загружает конфигурацию"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            log_info(f"Конфигурация загружена: цена {config['min_price']}-{config['max_price']}₽")
            return config
    except Exception as e:
        log_error(f"Ошибка загрузки конфига: {e}")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Сохраняет конфигурацию"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        log_info("Конфигурация сохранена")
    except Exception as e:
        log_error(f"Ошибка сохранения конфига: {e}")

def load_seen_ads():
    """Загружает просмотренные объявления"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            ads = set(line.strip() for line in f)
        log_info(f"Загружено {len(ads)} просмотренных объявлений")
        return ads
    except FileNotFoundError:
        log_info("Файл с объявлениями не найден, будет создан новый")
        return set()
    except Exception as e:
        log_error(f"Ошибка загрузки объявлений: {e}")
        return set()

def save_seen_ad(ad_id):
    """Сохраняет ID объявления"""
    try:
        with open(SEEN_FILE, "a", encoding="utf-8") as f:
            f.write(ad_id + "\n")
    except Exception as e:
        log_error(f"Ошибка сохранения ID {ad_id}: {e}")

def send_telegram_message(text, keyboard=None):
    """Отправляет сообщение с клавиатурой"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": ADMIN_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    if keyboard:
        params["reply_markup"] = json.dumps(keyboard)
    
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            log_debug(f"Сообщение отправлено в Telegram")
        else:
            log_error(f"Ошибка Telegram: {response.status_code}")
    except Exception as e:
        log_error(f"Ошибка отправки в Telegram: {e}")

def get_main_keyboard():
    """Главная клавиатура с кнопкой Логи"""
    keyboard = {
        "keyboard": [
            ["▶️ Запустить", "⏹ Остановить"],
            ["⚙️ Настройки", "📊 Статистика"],
            ["📋 Логи", "🆘 Помощь"],
            ["🔄 Очистить логи"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }
    return keyboard

def get_settings_keyboard():
    """Клавиатура настроек"""
    keyboard = {
        "keyboard": [
            ["💰 Цена", "🔗 URL"],
            ["⏱ Интервал", "◀️ Назад"],
            ["💾 Текущие настройки", "📋 Показать логи"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }
    return keyboard

def send_logs_to_telegram(lines=20):
    """Отправляет последние строки из лог-файла в Telegram"""
    try:
        if not os.path.exists(LOG_FILE):
            send_telegram_message("📝 Лог-файл еще не создан", get_main_keyboard())
            return
            
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            
        if not all_lines:
            send_telegram_message("📝 Лог-файл пуст", get_main_keyboard())
            return
            
        # Берем последние строки
        last_lines = all_lines[-lines:]
        
        # Формируем сообщение
        log_text = "".join(last_lines)
        
        # Если лог слишком длинный, обрезаем
        if len(log_text) > 3500:
            log_text = log_text[-3500:]
            
        message = f"📋 <b>Последние {len(last_lines)} строк лога:</b>\n\n<code>{log_text}</code>"
        send_telegram_message(message, get_main_keyboard())
        
    except Exception as e:
        log_error(f"Ошибка чтения лога: {e}")
        send_telegram_message(f"❌ Ошибка чтения лога: {e}", get_main_keyboard())

def clear_log_file():
    """Очищает лог-файл"""
    try:
        # Создаем резервную копию
        if os.path.exists(LOG_FILE):
            backup_name = f"{LOG_FILE}.backup"
            shutil.copy2(LOG_FILE, backup_name)
            log_info(f"Создана резервная копия лога: {backup_name}")
        
        # Очищаем файл
        open(LOG_FILE, 'w').close()
        log_info("Лог-файл очищен")
        send_telegram_message("✅ Лог-файл очищен. Резервная копия сохранена.", get_main_keyboard())
        
    except Exception as e:
        log_error(f"Ошибка очистки лога: {e}")
        send_telegram_message(f"❌ Ошибка очистки лога: {e}", get_main_keyboard())

def show_main_menu():
    """Показывает главное меню"""
    config = load_config()
    status = "АКТИВЕН 🟢" if monitoring_active else "ОСТАНОВЛЕН 🔴"
    
    text = f"""
🤖 <b>AVITO МОНИТОРИНГ БОТ</b>

📊 <b>Статус:</b> {status}
💰 <b>Цена:</b> {config['min_price']} - {config['max_price']} ₽
⏱ <b>Интервал:</b> {config['check_delay']} сек

Выберите действие:
"""
    send_telegram_message(text, get_main_keyboard())

def show_settings():
    """Показывает меню настроек"""
    text = "⚙️ <b>НАСТРОЙКИ</b>\n\nВыберите что изменить:"
    send_telegram_message(text, get_settings_keyboard())

def show_current_settings():
    """Показывает текущие настройки"""
    config = load_config()
    status = "АКТИВЕН 🟢" if monitoring_active else "ОСТАНОВЛЕН 🔴"
    
    text = f"""
📋 <b>ТЕКУЩИЕ НАСТРОЙКИ</b>

📊 <b>Статус:</b> {status}
💰 <b>Цена:</b> {config['min_price']} - {config['max_price']} ₽
⏱ <b>Интервал:</b> {config['check_delay']} сек
🔗 <b>URL:</b> 
{config['avito_url']}
"""
    send_telegram_message(text, get_settings_keyboard())

def show_statistics():
    """Показывает статистику"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            ads_count = len(f.readlines())
        
        text = f"""
📊 <b>СТАТИСТИКА</b>

📦 <b>Найдено объявлений:</b> {ads_count}
🕐 <b>Время работы:</b> {time.strftime('%H:%M %d.%m.%Y')}
"""
        send_telegram_message(text, get_main_keyboard())
    except Exception as e:
        log_error(f"Ошибка статистики: {e}")
        send_telegram_message("❌ Ошибка получения статистики", get_main_keyboard())

def show_help():
    """Показывает помощь"""
    text = """
🆘 <b>ПОМОЩЬ</b>

<b>Кнопки управления:</b>
▶️ Запустить - начать мониторинг
⏹ Остановить - остановить мониторинг
⚙️ Настройки - открыть меню настроек
📊 Статистика - показать статистику
📋 Логи - показать последние 20 строк лога
🔄 Очистить логи - очистить файл логов
🆘 Помощь - показать это сообщение

<b>Ввод значений:</b>
• Цена: "мин макс" (например: 0 3000)
• URL: ссылка на Avito
• Интервал: число секунд (10-3600)
"""
    send_telegram_message(text, get_main_keyboard())

def fetch_ad_details(ad_url):
    """Загружает описание объявления"""
    try:
        log_debug(f"Загрузка описания: {ad_url}")
        response = requests.get(ad_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        description = None
        
        # Поиск описания
        desc_block = soup.find('div', {'data-marker': 'item-view/item-description'})
        if desc_block:
            text_parts = []
            for elem in desc_block.find_all(['p', 'div', 'span']):
                text = elem.get_text(strip=True)
                if text and len(text) > 20:
                    text_parts.append(text)
            if text_parts:
                description = '\n'.join(text_parts)
                log_success("Описание найдено по data-marker")
        
        if not description:
            for class_name in ['style-item-description', 'item-description']:
                desc_block = soup.find('div', class_=class_name)
                if desc_block:
                    description = desc_block.get_text(strip=True)
                    log_success(f"Описание найдено по классу {class_name}")
                    break
        
        if description:
            description = ' '.join(description.split())
            if len(description) > 1000:
                description = description[:1000] + "..."
            return description
        else:
            log_warning("Описание не найдено")
            return "📝 Описание отсутствует"
        
    except Exception as e:
        log_error(f"Ошибка загрузки описания: {e}")
        return "❌ Ошибка загрузки описания"

def parse_avito_ads(html, config):
    """Парсит объявления с логированием"""
    if not html:
        log_error("HTML пустой")
        return []
    
    log_info(f"Начинаю парсинг HTML размером {len(html)} байт")
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Поиск объявлений
    items = soup.find_all('div', attrs={'data-marker': 'item'})
    log_info(f"Найдено элементов с data-marker='item': {len(items)}")
    
    if not items:
        items = soup.find_all('div', class_='iva-item-root')
        log_info(f"Найдено элементов с class='iva-item-root': {len(items)}")
    
    if not items:
        log_warning("Объявления не найдены на странице")
        return []
    
    ads = []
    for i, item in enumerate(items):
        try:
            log_debug(f"Парсинг элемента {i+1}/{len(items)}")
            
            # ID
            ad_id = (item.get('data-item-id') or 
                    item.get('id') or 
                    f"ad_{i}_{int(time.time())}")
            
            # Заголовок и ссылка
            title_tag = None
            for selector in [
                ('a', {'data-marker': 'item-title'}),
                ('a', {'itemprop': 'url'})
            ]:
                title_tag = item.find(selector[0], attrs=selector[1])
                if title_tag:
                    break
            
            if not title_tag:
                log_debug(f"Элемент {i}: не найден заголовок")
                continue
            
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href', '')
            if link.startswith('/'):
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
                numbers = re.findall(r'\b\d{4,6}\b', price_text)
                if numbers:
                    price = int(numbers[0])
            
            if config['min_price'] <= price <= config['max_price'] and price > 0:
                ads.append({
                    'id': ad_id,
                    'title': title,
                    'price': price,
                    'link': link
                })
                log_debug(f"✅ Добавлено: {title[:30]}... {price}₽")
                
        except Exception as e:
            log_error(f"Ошибка парсинга элемента {i}: {e}")
            continue
    
    log_info(f"Парсинг завершен. Найдено {len(ads)} объявлений в диапазоне цен")
    return ads

def monitoring_loop():
    """Основной цикл мониторинга"""
    global monitoring_active
    
    log_info("🔄 Запуск цикла мониторинга")
    seen_ads = load_seen_ads()
    check_count = 0
    
    while monitoring_active:
        try:
            check_count += 1
            log_info(f"Проверка #{check_count} начата")
            
            config = load_config()
            
            # Загружаем страницу
            log_debug(f"Загрузка URL: {config['avito_url']}")
            response = requests.get(config['avito_url'], headers=HEADERS, timeout=30)
            log_debug(f"Статус ответа: {response.status_code}")
            
            if response.status_code != 200:
                log_error(f"Ошибка HTTP: {response.status_code}")
                time.sleep(60)
                continue
            
            # Парсим объявления
            ads = parse_avito_ads(response.text, config)
            
            # Проверяем новые
            new_count = 0
            for ad in ads:
                if not monitoring_active:
                    break
                    
                if ad['id'] not in seen_ads:
                    new_count += 1
                    log_info(f"НОВОЕ ОБЪЯВЛЕНИЕ #{new_count}: {ad['title'][:50]}... {ad['price']}₽")
                    
                    # Загружаем описание
                    description = fetch_ad_details(ad['link'])
                    
                    # Эмодзи цены
                    if ad['price'] < 1000:
                        price_emoji = "💚"
                    elif ad['price'] < 1500:
                        price_emoji = "💛"
                    else:
                        price_emoji = "❤️"
                    
                    # Формируем сообщение
                    current_time = datetime.now().strftime('%H:%M %d.%m')
                    message = f"""
🔔 <b>НОВОЕ ОБЪЯВЛЕНИЕ!</b>

📱 <b>{ad['title']}</b>
{price_emoji} <b>Цена: {ad['price']} ₽</b>
🔗 <a href="{ad['link']}">Открыть объявление</a>

📝 <b>Описание:</b>
{description}

🕐 {current_time}
"""
                    send_telegram_message(message, get_main_keyboard())
                    
                    seen_ads.add(ad['id'])
                    save_seen_ad(ad['id'])
                    time.sleep(3)
            
            if new_count > 0:
                log_success(f"Найдено {new_count} новых объявлений")
            
            # Ждем следующую проверку
            delay = config['check_delay']
            log_info(f"Следующая проверка через {delay} секунд")
            
            for i in range(delay):
                if not monitoring_active:
                    break
                time.sleep(1)
                
        except Exception as e:
            log_error(f"Ошибка в цикле мониторинга: {e}")
            time.sleep(60)
    
    log_info("⏹ Цикл мониторинга остановлен")

def start_monitoring():
    """Запускает мониторинг"""
    global monitoring_active, monitoring_thread
    
    if monitoring_active:
        send_telegram_message("⚠️ Мониторинг уже запущен!", get_main_keyboard())
        return
    
    monitoring_active = True
    monitoring_thread = threading.Thread(target=monitoring_loop)
    monitoring_thread.daemon = True
    monitoring_thread.start()
    
    log_success("Мониторинг запущен")
    send_telegram_message("✅ Мониторинг запущен!", get_main_keyboard())

def stop_monitoring():
    """Останавливает мониторинг"""
    global monitoring_active
    
    monitoring_active = False
    log_info("Мониторинг остановлен")
    send_telegram_message("⏹ Мониторинг остановлен!", get_main_keyboard())

def handle_message(text):
    """Обрабатывает сообщения от пользователя"""
    log_debug(f"Получено сообщение: {text}")
    config = load_config()
    
    # Команды меню
    if text == "/start":
        show_main_menu()
    
    elif text == "▶️ Запустить":
        start_monitoring()
    
    elif text == "⏹ Остановить":
        stop_monitoring()
    
    elif text == "⚙️ Настройки":
        show_settings()
    
    elif text == "📊 Статистика":
        show_statistics()
    
    elif text == "📋 Логи":
        send_logs_to_telegram(20)
    
    elif text == "🔄 Очистить логи":
        clear_log_file()
    
    elif text == "🆘 Помощь":
        show_help()
    
    elif text == "💰 Цена":
        send_telegram_message(
            "💰 Введите диапазон цен в формате:\n"
            "<code>мин макс</code>\n\n"
            "Пример: <code>0 3000</code>",
            get_settings_keyboard()
        )
    
    elif text == "🔗 URL":
        send_telegram_message(
            "🔗 Отправьте новую ссылку для поиска\n\n"
            "Пример:\n"
            "<code>https://www.avito.ru/all/telefony</code>",
            get_settings_keyboard()
        )
    
    elif text == "⏱ Интервал":
        send_telegram_message(
            "⏱ Введите интервал проверки в секундах\n\n"
            "Пример: <code>120</code> (2 минуты)",
            get_settings_keyboard()
        )
    
    elif text == "💾 Текущие настройки":
        show_current_settings()
    
    elif text == "📋 Показать логи":
        send_logs_to_telegram(15)
    
    elif text == "◀️ Назад":
        show_main_menu()
    
    # Обработка ввода значений
    elif ' ' in text and all(p.strip().isdigit() for p in text.split()):
        parts = text.split()
        min_p, max_p = int(parts[0]), int(parts[1])
        
        if min_p < max_p:
            config['min_price'] = min_p
            config['max_price'] = max_p
            save_config(config)
            log_info(f"Цена изменена: {min_p}-{max_p}₽")
            send_telegram_message(f"✅ Цена установлена: {min_p} - {max_p} ₽", get_settings_keyboard())
        else:
            send_telegram_message("❌ Минимальная цена должна быть меньше максимальной", get_settings_keyboard())
    
    elif text.isdigit():
        delay = int(text)
        if 10 <= delay <= 3600:
            config['check_delay'] = delay
            save_config(config)
            log_info(f"Интервал изменен: {delay} сек")
            send_telegram_message(f"✅ Интервал установлен: {delay} сек", get_settings_keyboard())
        else:
            send_telegram_message("❌ Интервал должен быть от 10 до 3600 секунд", get_settings_keyboard())
    
    elif 'avito.ru' in text:
        if not text.startswith('http'):
            text = 'https://' + text
        config['avito_url'] = text
        save_config(config)
        log_info(f"URL изменен: {text[:100]}...")
        send_telegram_message("✅ URL для поиска обновлен!", get_settings_keyboard())
    
    else:
        send_telegram_message("❓ Неизвестная команда. Используйте кнопки меню.", get_main_keyboard())

def get_updates(offset=0):
    """Получает обновления от Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {
        "offset": offset,
        "timeout": 30,
        "allowed_updates": ["message"]
    }
    
    try:
        response = requests.get(url, params=params, timeout=35)
        return response.json()
    except Exception as e:
        log_error(f"Ошибка getUpdates: {e}")
        return {"ok": False, "result": []}

def main():
    """Главная функция"""
    log_info("🚀 Бот запускается...")
    
    # Создаем лог-файл при запуске
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*50}\n")
        f.write(f"Бот запущен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'='*50}\n")
    
    # Загружаем конфиг
    load_config()
    
    # Показываем меню при запуске
    show_main_menu()
    log_success("Бот готов к работе")
    
    # Основной цикл получения сообщений
    last_update_id = 0
    
    while True:
        try:
            updates = get_updates(last_update_id)
            
            if updates.get("ok"):
                for update in updates.get("result", []):
                    last_update_id = update["update_id"] + 1
                    
                    if "message" in update and "text" in update["message"]:
                        text = update["message"]["text"]
                        handle_message(text)
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            log_info("👋 Бот остановлен пользователем")
            break
        except Exception as e:
            log_error(f"Ошибка в главном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()

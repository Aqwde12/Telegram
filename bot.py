import time
import random
import requests
import threading
import json
import os
import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import urllib3
from datetime import datetime
from flask import Flask, request, jsonify

# Отключаем предупреждения о SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================= НАСТРОЙКИ ЛОГИРОВАНИЯ =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= НАСТРОЙКИ =================

# 🔥 ВАЖНО: На Bothost настройте переменные окружения!
# В панели Bothost -> Настройки проекта -> Переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN', '7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8')
ADMIN_ID = os.environ.get('ADMIN_ID', '380924486')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', '')  # URL вашего бота на Bothost
WEBHOOK_PORT = int(os.environ.get('PORT', 8080))  # Bothost автоматически назначает порт

DEFAULT_CONFIG = {
    "avito_url": "https://www.avito.ru/all/telefony/mobilnye_telefony/apple-ASgBAgICAkS0wA3OqzmwwQ2I_Dc?cd=1&s=104",
    "min_price": 0,
    "max_price": 2300,
    "check_delay": 60,
    "is_active": True,
    "show_details": True
}

# На Bothost используем /app/data/ для постоянного хранения
# Эти папки не очищаются при перезапуске
DATA_DIR = '/app/data' if os.path.exists('/app/data') else '.'
CONFIG_FILE = os.path.join(DATA_DIR, "bot_config.json")
SEEN_FILE = os.path.join(DATA_DIR, "seen_ads.txt")

# =============================================

# Flask приложение для Webhook
app = Flask(__name__)

# Глобальные переменные
bot_thread = None
is_bot_running = False
monitoring_active = False
stop_monitoring = False
bot_chat_id = None

# Сессия с улучшенными настройками
session = requests.Session()
session.verify = False
session.trust_env = False

# Заголовки для имитации браузера
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}

# ================= ФУНКЦИИ РАБОТЫ С ФАЙЛАМИ =================

def ensure_data_dir():
    """Создает директорию для данных, если её нет"""
    if DATA_DIR != '.' and not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info(f"✅ Создана директория для данных: {DATA_DIR}")

def load_config():
    """Загружает конфигурацию из файла с обновлением до актуальной версии"""
    ensure_data_dir()
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Проверяем и добавляем недостающие ключи из DEFAULT_CONFIG
        updated = False
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = value
                updated = True
                logger.info(f"🔄 Добавлен недостающий ключ в конфиг: {key}")
        
        # Конвертируем старый формат интервала (min/max) в новый (одно значение)
        if "check_delay_min" in config and "check_delay_max" in config:
            # Берем среднее значение
            avg_delay = (config["check_delay_min"] + config["check_delay_max"]) // 2
            config["check_delay"] = avg_delay
            # Удаляем старые ключи
            del config["check_delay_min"]
            del config["check_delay_max"]
            updated = True
            logger.info(f"🔄 Конвертирован старый формат интервала в новое значение: {avg_delay} сек")
        
        if updated:
            save_config(config)
            logger.info("✅ Конфигурация обновлена")
        
        return config
        
    except FileNotFoundError:
        logger.info("📝 Создан новый файл конфигурации")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    except json.JSONDecodeError:
        logger.error("⚠ Ошибка чтения конфига, создаем новый")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Сохраняет конфигурацию в файл"""
    ensure_data_dir()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_seen_ads():
    """Загружает ID просмотренных объявлений"""
    ensure_data_dir()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_seen_ad(ad_id):
    """Сохраняет ID нового объявления"""
    ensure_data_dir()
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(ad_id + "\n")

# ================= TELEGRAM ФУНКЦИИ =================

def send_telegram_request(method, params=None, json_data=None):
    """Универсальная функция для отправки запросов к Telegram API"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            if json_data:
                response = session.post(url, json=json_data, headers=headers, timeout=60)
            else:
                response = session.get(url, params=params, headers=headers, timeout=60)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Ошибка HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            logger.warning(f"⚠ Таймаут (попытка {attempt + 1}/{max_retries})")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"⚠ Ошибка (попытка {attempt + 1}/{max_retries}): {e}")
            time.sleep(5)
    
    return None

def set_webhook():
    """Устанавливает вебхук для бота"""
    if not WEBHOOK_URL:
        logger.warning("⚠ WEBHOOK_URL не задан, используется polling режим")
        return False
    
    webhook_url = f"{WEBHOOK_URL}/webhook"
    
    # Удаляем старый вебхук
    send_telegram_request("deleteWebhook")
    
    # Устанавливаем новый
    result = send_telegram_request("setWebhook", params={
        "url": webhook_url,
        "allowed_updates": ["message"]
    })
    
    if result and result.get("ok"):
        logger.info(f"✅ Webhook установлен: {webhook_url}")
        return True
    else:
        logger.error(f"❌ Ошибка установки webhook: {result}")
        return False

def send_telegram_message(chat_id, text, keyboard=None, parse_mode="HTML"):
    """Отправляет сообщение в Telegram"""
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    
    if keyboard:
        params["reply_markup"] = json.dumps(keyboard)
    
    result = send_telegram_request("sendMessage", params=params)
    return result is not None

# ================= КЛАВИАТУРЫ =================

def get_main_keyboard():
    """Возвращает основную клавиатуру"""
    config = load_config()
    details_status = "Вкл" if config.get("show_details", True) else "Выкл"
    
    return {
        "keyboard": [
            ["🔍 Запустить", "⏹ Остановить"],
            ["⚙️ Настройки", "📊 Статистика"],
            [f"👁 Детали: {details_status}", "🔄 Перезапустить"],
            ["🆘 Помощь"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def get_settings_keyboard():
    """Возвращает клавиатуру для настроек"""
    config = load_config()
    details_status = "✅ Вкл" if config.get("show_details", True) else "❌ Выкл"
    
    return {
        "keyboard": [
            ["💰 Цена", "🔗 URL"],
            ["⏱ Интервал", f"📋 Детали: {details_status}"],
            ["◀️ Назад"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

# ================= ПАРСИНГ AVITO =================

def parse_avito_details(ad_url):
    """Парсит только описание с детальной страницы объявления"""
    try:
        logger.info(f"🔍 Загружаю описание объявления: {ad_url}")
        
        # Задержка перед запросом деталей
        time.sleep(random.uniform(3, 5))
        
        response = session.get(ad_url, headers=HEADERS, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"❌ Ошибка загрузки страницы: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ищем описание
        description = ""
        desc_selectors = [
            'div[data-marker="item-view/item-description"]',
            'div.item-description',
            'div[class*="description"]',
            'div[class*="Description"]'
        ]
        
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                description = desc_elem.get_text(strip=True)
                break
        
        if not description:
            # Пробуем найти описание по тексту
            text_blocks = soup.find_all(['div', 'p'], text=True)
            for block in text_blocks:
                if block and len(block.get_text(strip=True)) > 100:
                    description = block.get_text(strip=True)
                    break
        
        if description:
            return description[:1000] + "..." if len(description) > 1000 else description
        else:
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка при парсинге описания: {e}")
        return None

def get_latest_ads(config):
    """Парсит объявления со страницы через requests"""
    try:
        logger.info(f"🌐 Загружаю страницу: {config['avito_url']}")
        
        # Небольшая задержка перед запросом
        time.sleep(random.uniform(2, 4))
        
        # Обновляем заголовки для каждого запроса
        headers = HEADERS.copy()
        headers['Referer'] = 'https://www.avito.ru/'
        
        response = session.get(config['avito_url'], headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"❌ Ошибка загрузки: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ищем объявления
        items = soup.find_all("div", attrs={"data-marker": "item"})
        
        if not items:
            # Альтернативный поиск
            items = soup.find_all("div", class_=re.compile("iva-item"))
        
        logger.info(f"📦 Найдено {len(items)} объявлений на странице")
        
        ads = []
        for item in items:
            try:
                # Пробуем разные способы найти ID
                ad_id = None
                
                # По data-item-id
                ad_id = item.get("data-item-id")
                
                # По data-id
                if not ad_id:
                    ad_id = item.get("data-id")
                
                # По ссылке
                if not ad_id:
                    link_tag = item.find("a", href=re.compile(r"\/\d+"))
                    if link_tag:
                        href = link_tag.get("href", "")
                        match = re.search(r"/(\d+)$", href)
                        if match:
                            ad_id = match.group(1)
                
                # Поиск заголовка и цены
                title_tag = None
                price_tag = None
                
                # Ищем заголовок
                title_selectors = [
                    'a[data-marker="item-title"]',
                    'h3[itemprop="name"] a',
                    'a[class*="title"]',
                    'a[href*="/"]'
                ]
                
                for selector in title_selectors:
                    title_tag = item.select_one(selector)
                    if title_tag and title_tag.get_text(strip=True):
                        break
                
                # Ищем цену
                price_selectors = [
                    'meta[itemprop="price"]',
                    'span[data-marker*="price"]',
                    'strong[class*="price"]',
                    'span[class*="price"]'
                ]
                
                price = 0
                for selector in price_selectors:
                    if selector.startswith('meta'):
                        price_tag = item.select_one(selector)
                        if price_tag:
                            price_content = price_tag.get("content")
                            if price_content and price_content.isdigit():
                                price = int(price_content)
                                break
                    else:
                        price_tag = item.select_one(selector)
                        if price_tag:
                            price_text = price_tag.get_text(strip=True)
                            # Извлекаем цифры из текста цены
                            price_digits = re.findall(r'\d+', price_text.replace(' ', ''))
                            if price_digits:
                                price = int(price_digits[0])
                                break
                
                if not all([ad_id, title_tag, price]):
                    continue
                
                # Проверяем цену по фильтру
                if config['min_price'] <= price <= config['max_price']:
                    title = title_tag.get_text(strip=True)
                    
                    # Формируем ссылку
                    link = title_tag.get("href", "")
                    if link.startswith("/"):
                        link = "https://www.avito.ru" + link
                    
                    ads.append({
                        "id": str(ad_id),
                        "title": title,
                        "price": price,
                        "link": link
                    })
                    
            except Exception as e:
                continue
        
        # Сортируем по цене
        ads.sort(key=lambda x: x['price'])
        
        logger.info(f"💰 Найдено {len(ads)} объявлений в заданном диапазоне цен")
        return ads
        
    except Exception as e:
        logger.error(f"❌ Ошибка при парсинге: {e}")
        return []

def format_ad_message_with_details(ad, description=None):
    """Форматирует объявление с описанием под спойлером"""
    if ad['price'] < 1000:
        price_emoji = "💚"
    elif ad['price'] < 1500:
        price_emoji = "💛"
    else:
        price_emoji = "❤️"
    
    message = f"""
🔔 <b>НОВОЕ ОБЪЯВЛЕНИЕ!</b>

📱 <b>{ad['title']}</b>
{price_emoji} Цена: <b>{ad['price']} ₽</b>
🔗 <a href="{ad['link']}">Открыть объявление</a>
"""
    
    if description:
        message += f"\n\n||📝 <b>Описание:</b>\n{description}||"
    
    message += f"\n🕐 {time.strftime('%H:%M')}"
    
    return message

def send_ad_notification(chat_id, ad):
    """Отправляет уведомление о новом объявлении"""
    config = load_config()
    
    description = None
    if config.get("show_details", True):
        logger.info(f"📋 Загружаю описание для объявления {ad['id']}...")
        description = parse_avito_details(ad['link'])
    
    message = format_ad_message_with_details(ad, description)
    send_telegram_message(chat_id, message, get_main_keyboard())

# ================= ОБРАБОТКА КОМАНД =================

def get_settings_text():
    """Возвращает текст с текущими настройками"""
    config = load_config()
    status = "✅ Активен" if config.get("is_active", False) else "❌ Остановлен"
    details = "✅ Вкл" if config.get("show_details", True) else "❌ Выкл"
    
    return f"""
📱 Статус: {status}
💰 Цена: {config['min_price']} - {config['max_price']} ₽
⏱ Интервал между проверками: {config['check_delay']} сек
📋 Детали (описание): {details}
🔗 <a href="{config['avito_url']}">Ссылка на поиск</a>
"""

def send_start_message(chat_id):
    """Отправляет стартовое сообщение"""
    config = load_config()
    details_status = "✅ Включены" if config.get("show_details", True) else "❌ Отключены"
    
    text = f"""
🤖 <b>Avito Мониторинг Бот</b>

Добро пожаловать! Я помогу отслеживать новые объявления на Avito.
📋 Детали объявлений (описание): {details_status}

<b>Текущие настройки:</b>
"""
    text += get_settings_text()
    
    send_telegram_message(chat_id, text, get_main_keyboard())

def send_settings_menu(chat_id):
    """Отправляет меню настроек"""
    text = "⚙️ <b>Настройки</b>\n\n"
    text += get_settings_text()
    text += "\n\nВыберите что изменить:"
    
    send_telegram_message(chat_id, text, get_settings_keyboard())

def show_statistics(chat_id):
    """Показывает статистику работы"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            ads_count = len(f.readlines())
    except FileNotFoundError:
        ads_count = 0
    
    config = load_config()
    
    text = f"""
📊 <b>Статистика</b>

📦 Найдено объявлений: {ads_count}
💰 Текущий диапазон: {config['min_price']} - {config['max_price']} ₽
⏱ Интервал между проверками: {config['check_delay']} сек
📋 Детали (описание): {"✅ Вкл" if config.get("show_details", True) else "❌ Выкл"}
🕐 Время работы: {time.strftime('%H:%M %d.%m.%Y')}
"""
    
    send_telegram_message(chat_id, text, get_main_keyboard())

def show_help(chat_id):
    """Показывает справку"""
    text = """
🆘 <b>Помощь по боту</b>

<b>Кнопки управления:</b>
🔍 Запустить - начать мониторинг
⏹ Остановить - остановить мониторинг
⚙️ Настройки - изменить параметры
📊 Статистика - показать статистику
👁 Детали: Вкл/Выкл - вкл/выкл подробное описание
🔄 Перезапустить - перезапуск
🆘 Помощь - показать справку

<b>📋 Скрытый текст:</b>
• Описание объявления под спойлером
• Нажмите на скрытый текст, чтобы развернуть

<b>Форматы ввода:</b>
• Цена: <code>0 3000</code> (мин макс)
• Интервал: <code>60</code> (одно число в секундах)
• URL: просто вставьте ссылку
"""
    send_telegram_message(chat_id, text, get_main_keyboard())

def toggle_details(chat_id):
    """Включает/выключает показ описания объявлений"""
    config = load_config()
    config["show_details"] = not config.get("show_details", True)
    save_config(config)
    
    status = "включен" if config["show_details"] else "отключен"
    send_telegram_message(chat_id, f"✅ Показ описания объявлений {status}", get_settings_keyboard())

def handle_input(text, chat_id):
    """Обрабатывает пользовательский ввод"""
    config = load_config()
    
    # Проверяем ввод диапазона цен (два числа)
    if text.count(' ') == 1 and all(part.strip().isdigit() for part in text.split()):
        parts = text.split()
        min_val, max_val = int(parts[0]), int(parts[1])
        
        if min_val < max_val:
            config["min_price"] = min_val
            config["max_price"] = max_val
            save_config(config)
            send_telegram_message(chat_id, "✅ Диапазон цен обновлен!", get_settings_keyboard())
        else:
            send_telegram_message(chat_id, "❌ Минимальная цена должна быть меньше максимальной", get_settings_keyboard())
    
    # Проверяем ввод интервала (одно число)
    elif text.isdigit():
        delay = int(text)
        if delay >= 10:  # Минимальный интервал 10 секунд
            config["check_delay"] = delay
            save_config(config)
            send_telegram_message(chat_id, f"✅ Интервал между проверками установлен: {delay} сек", get_settings_keyboard())
        else:
            send_telegram_message(chat_id, "❌ Интервал должен быть не менее 10 секунд", get_settings_keyboard())
            
    elif "avito.ru" in text:
        if not text.startswith(("http://", "https://")):
            text = "https://" + text
        config["avito_url"] = text
        save_config(config)
        send_telegram_message(chat_id, "✅ URL для поиска обновлен!", get_settings_keyboard())
    
    else:
        send_telegram_message(chat_id, "❌ Не понял команду. Используйте кнопки ниже.", get_main_keyboard())

def process_text_message(text, chat_id):
    """Обрабатывает текстовые сообщения от кнопок"""
    global monitoring_active, stop_monitoring, bot_chat_id
    
    # Сохраняем chat_id для мониторинга
    bot_chat_id = chat_id
    
    if text == "🔍 Запустить":
        if not monitoring_active:
            monitoring_active = True
            stop_monitoring = False
            config = load_config()
            config["is_active"] = True
            save_config(config)
            
            send_telegram_message(chat_id, "✅ Мониторинг запущен!", get_main_keyboard())
            start_monitoring_thread(chat_id)
        else:
            send_telegram_message(chat_id, "⚠ Мониторинг уже запущен!", get_main_keyboard())
        
    elif text == "⏹ Остановить":
        if monitoring_active:
            monitoring_active = False
            stop_monitoring = True
            config = load_config()
            config["is_active"] = False
            save_config(config)
            
            send_telegram_message(chat_id, "⏹ Мониторинг остановлен!", get_main_keyboard())
            logger.info("⏹ Мониторинг остановлен по команде")
        else:
            send_telegram_message(chat_id, "⚠ Мониторинг не запущен!", get_main_keyboard())
                
    elif text == "🔄 Перезапустить":
        if monitoring_active:
            monitoring_active = False
            stop_monitoring = True
            time.sleep(2)
            monitoring_active = True
            stop_monitoring = False
            start_monitoring_thread(chat_id)
            send_telegram_message(chat_id, "🔄 Мониторинг перезапущен!", get_main_keyboard())
        else:
            send_telegram_message(chat_id, "⚠ Мониторинг не запущен!", get_main_keyboard())
        
    elif text.startswith("👁 Детали:") or text.startswith("📋 Детали:"):
        toggle_details(chat_id)
        
    elif text == "⚙️ Настройки":
        send_settings_menu(chat_id)
        
    elif text == "📊 Статистика":
        show_statistics(chat_id)
        
    elif text == "🆘 Помощь":
        show_help(chat_id)
        
    elif text == "◀️ Назад":
        send_start_message(chat_id)
        
    elif text == "💰 Цена":
        send_telegram_message(chat_id, "💰 Введите новый диапазон цен в формате: <b>мин макс</b>\nНапример: <code>0 3000</code>", get_settings_keyboard())
        
    elif text == "🔗 URL":
        send_telegram_message(chat_id, "🔗 Отправьте новую ссылку для поиска на Avito", get_settings_keyboard())
        
    elif text == "⏱ Интервал":
        send_telegram_message(chat_id, "⏱ Введите интервал между проверками в секундах\nНапример: <code>60</code>", get_settings_keyboard())

# ================= МОНИТОРИНГ =================

def monitoring_loop(chat_id):
    """Основной цикл мониторинга"""
    global monitoring_active, stop_monitoring
    
    logger.info("🔄 Запуск мониторинга...")
    config = load_config()
    seen_ads = load_seen_ads()
    
    # Бесконечный цикл мониторинга
    while monitoring_active and not stop_monitoring:
        try:
            logger.info("\n" + "="*50)
            logger.info("🔍 Проверка новых объявлений...")
            
            # Получаем текущие объявления
            ads = get_latest_ads(config)
            
            # Фильтруем только новые объявления
            new_ads = [ad for ad in ads if ad["id"] not in seen_ads]
            
            if new_ads:
                logger.info(f"📬 Найдено {len(new_ads)} новых объявлений")
                
                # Отправляем каждое новое объявление с интервалом
                for i, ad in enumerate(new_ads, 1):
                    # Проверяем флаг остановки
                    if stop_monitoring or not monitoring_active:
                        logger.info("⏹ Мониторинг остановлен")
                        monitoring_active = False
                        return
                    
                    logger.info(f"  {i}. Отправка: {ad['title']} - {ad['price']}₽")
                    
                    # Отправляем уведомление
                    send_ad_notification(chat_id, ad)
                    
                    # Добавляем в просмотренные
                    seen_ads.add(ad["id"])
                    save_seen_ad(ad["id"])
                    
                    # Если это не последнее объявление, ждем указанный интервал
                    if i < len(new_ads):
                        delay = config['check_delay']
                        logger.info(f"⏳ Ожидание {delay} сек перед следующим объявлением...")
                        
                        # Ожидание с проверкой флага остановки
                        for _ in range(delay):
                            if stop_monitoring or not monitoring_active:
                                logger.info("⏹ Мониторинг остановлен во время ожидания")
                                monitoring_active = False
                                return
                            time.sleep(1)
            else:
                logger.info(f"ℹ️ Новых объявлений не найдено")
            
            # Ждем перед следующей проверкой
            delay = config['check_delay']
            logger.info(f"⏳ Следующая проверка через {delay} сек...")
            
            # Ожидание с проверкой флага остановки
            for _ in range(delay):
                if stop_monitoring or not monitoring_active:
                    logger.info("⏹ Мониторинг остановлен во время ожидания")
                    monitoring_active = False
                    return
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Ошибка в мониторинге: {e}")
            
            if monitoring_active and not stop_monitoring:
                logger.info("⏳ Повторная попытка через 30 секунд...")
                for _ in range(30):
                    if stop_monitoring or not monitoring_active:
                        logger.info("⏹ Мониторинг остановлен во время ожидания после ошибки")
                        monitoring_active = False
                        return
                    time.sleep(1)

def start_monitoring_thread(chat_id):
    """Запускает мониторинг в отдельном потоке"""
    global bot_thread, monitoring_active, stop_monitoring
    
    # Если есть старый поток, ждем его завершения
    if bot_thread and bot_thread.is_alive():
        stop_monitoring = True
        monitoring_active = False
        time.sleep(2)
    
    monitoring_active = True
    stop_monitoring = False
    bot_thread = threading.Thread(target=monitoring_loop, args=(chat_id,))
    bot_thread.daemon = True
    bot_thread.start()
    logger.info("✅ Поток мониторинга запущен")

# ================= FLASK WEBHOOK =================

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обрабатывает входящие обновления от Telegram"""
    try:
        update = request.get_json()
        
        if update and "message" in update and "text" in update["message"]:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"]["text"]
            
            logger.info(f"📨 Получено сообщение от {chat_id}: {text}")
            
            if text == "/start":
                send_start_message(chat_id)
            elif text == "/help":
                show_help(chat_id)
            elif text in ["🔍 Запустить", "⏹ Остановить", "⚙️ Настройки", "📊 Статистика", 
                        "🆘 Помощь", "◀️ Назад", "💰 Цена", "🔗 URL", 
                        "⏱ Интервал", "🔄 Перезапустить"] or text.startswith("👁 Детали:") or text.startswith("📋 Детали:"):
                process_text_message(text, chat_id)
            else:
                handle_input(text, chat_id)
        
        return jsonify({"ok": True})
    
    except Exception as e:
        logger.error(f"❌ Ошибка в webhook: {e}")
        return jsonify({"ok": False}), 500

@app.route('/health', methods=['GET'])
def health():
    """Endpoint для проверки здоровья (Bothost мониторинг)"""
    return jsonify({"status": "ok", "monitoring": monitoring_active})

@app.route('/', methods=['GET'])
def index():
    """Главная страница"""
    return jsonify({
        "name": "Avito Monitoring Bot",
        "status": "running",
        "monitoring": monitoring_active
    })

# ================= ЗАПУСК =================

def start_polling():
    """Запускает polling режим (если webhook не настроен)"""
    logger.info("🤖 Запуск в polling режиме...")
    
    offset = 0
    error_count = 0
    
    while True:
        try:
            params = {
                "offset": offset,
                "timeout": 60,
                "allowed_updates": ["message"]
            }
            
            result = send_telegram_request("getUpdates", params=params)
            
            if result and result.get("ok"):
                error_count = 0
                
                if "result" in result and result["result"]:
                    for update in result["result"]:
                        update_id = update["update_id"]
                        offset = update_id + 1
                        
                        if "message" in update and "text" in update["message"]:
                            chat_id = update["message"]["chat"]["id"]
                            text = update["message"]["text"]
                            
                            logger.info(f"📨 Получено сообщение от {chat_id}: {text}")
                            
                            if text == "/start":
                                send_start_message(chat_id)
                            elif text == "/help":
                                show_help(chat_id)
                            elif text in ["🔍 Запустить", "⏹ Остановить", "⚙️ Настройки", "📊 Статистика", 
                                        "🆘 Помощь", "◀️ Назад", "💰 Цена", "🔗 URL", 
                                        "⏱ Интервал", "🔄 Перезапустить"] or text.startswith("👁 Детали:") or text.startswith("📋 Детали:"):
                                process_text_message(text, chat_id)
                            else:
                                handle_input(text, chat_id)
            
            time.sleep(1)
            
        except Exception as e:
            error_count += 1
            logger.error(f"⚠ Ошибка в Telegram polling ({error_count}): {e}")
            time.sleep(5)

def main():
    """Главная функция"""
    logger.info("="*60)
    logger.info("🚀 Avito мониторинг бот (адаптирован для Bothost)")
    logger.info("="*60)
    
    # Создаем директорию для данных
    ensure_data_dir()
    
    # Проверяем токен
    if BOT_TOKEN:
        logger.info("✅ Токен бота загружен")
    
    # Проверяем ID администратора
    if ADMIN_ID:
        logger.info("✅ ID администратора загружен")
    
    # Загружаем конфигурацию
    config = load_config()
    
    logger.info(f"\n📋 Текущие настройки:")
    logger.info(f"  • Диапазон цен: {config['min_price']} - {config['max_price']} ₽")
    logger.info(f"  • Интервал: {config['check_delay']} сек")
    logger.info(f"  • Детали: {'Вкл' if config.get('show_details', True) else 'Выкл'}")
    logger.info(f"  • Данные хранятся в: {DATA_DIR}")
    
    # Пытаемся установить webhook
    webhook_set = set_webhook()
    
    if webhook_set:
        # Запускаем Flask сервер для webhook
        logger.info(f"🌐 Запуск webhook сервера на порту {WEBHOOK_PORT}")
        app.run(host='0.0.0.0', port=WEBHOOK_PORT)
    else:
        # Запускаем polling режим
        logger.info("📱 Запуск в polling режиме...")
        try:
            start_polling()
        except KeyboardInterrupt:
            logger.info("\n👋 Бот остановлен")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()

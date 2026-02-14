import time
import requests
import os
from bs4 import BeautifulSoup
from datetime import datetime
import json
import threading

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7952549707:AAGiYWBj8pfkrd-KB4XYbfko9jvGYlcaqs8")
ADMIN_ID = os.environ.get("ADMIN_ID", "380924486")

# Файлы для хранения данных
CONFIG_FILE = "bot_config.json"
SEEN_FILE = "seen_ads.txt"

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

def load_config():
    """Загружает конфигурацию"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Сохраняет конфигурацию"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_seen_ads():
    """Загружает просмотренные объявления"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    except:
        return set()

def save_seen_ad(ad_id):
    """Сохраняет ID объявления"""
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        f.write(ad_id + "\n")

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
        requests.get(url, params=params, timeout=10)
    except:
        pass

def get_main_keyboard():
    """Главная клавиатура"""
    config = load_config()
    status = "🔴 Остановлен" if not monitoring_active else "🟢 Активен"
    
    keyboard = {
        "keyboard": [
            [f"▶️ Запустить", f"⏹ Остановить"],
            [f"⚙️ Настройки", f"📊 Статистика"],
            [f"🔄 Обновить", f"🆘 Помощь"]
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
            ["💾 Текущие настройки"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }
    return keyboard

def show_main_menu():
    """Показывает главное меню"""
    config = load_config()
    status = "АКТИВЕН 🟢" if monitoring_active else "ОСТАНОВЛЕН 🔴"
    
    text = f"""
🤖 <b>AVITO МОНИТОРИНГ БОТ</b>

📊 <b>Статус:</b> {status}
💰 <b>Цена:</b> {config['min_price']} - {config['max_price']} ₽
⏱ <b>Интервал:</b> {config['check_delay']} сек
🔗 <a href="{config['avito_url']}">Ссылка на поиск</a>

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

Используйте кнопки для изменения.
"""
    send_telegram_message(text, get_settings_keyboard())

def show_statistics():
    """Показывает статистику"""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            ads_count = len(f.readlines())
    except:
        ads_count = 0
    
    config = load_config()
    uptime = "Бот работает" if monitoring_active else "Бот остановлен"
    
    text = f"""
📊 <b>СТАТИСТИКА</b>

📦 <b>Найдено объявлений:</b> {ads_count}
💰 <b>Диапазон цен:</b> {config['min_price']} - {config['max_price']} ₽
⏱ <b>Интервал:</b> {config['check_delay']} сек
🕐 <b>Статус:</b> {uptime}
"""
    send_telegram_message(text, get_main_keyboard())

def show_help():
    """Показывает помощь"""
    text = """
🆘 <b>ПОМОЩЬ</b>

<b>Кнопки управления:</b>
▶️ Запустить - начать мониторинг
⏹ Остановить - остановить мониторинг
⚙️ Настройки - открыть меню настроек
📊 Статистика - показать статистику
🔄 Обновить - обновить страницу

<b>Ввод значений:</b>
• Цена: отправьте "мин макс" (0 3000)
• URL: отправьте ссылку на Avito
• Интервал: отправьте число (секунды)

<b>Примеры:</b>
<code>0 2500</code> - установить цену
<code>https://www.avito.ru/...</code> - установить URL
<code>120</code> - установить интервал
"""
    send_telegram_message(text, get_main_keyboard())

def fetch_ad_details(ad_url):
    """Загружает описание объявления"""
    try:
        response = requests.get(ad_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем описание
        desc_block = soup.find('div', {'data-marker': 'item-view/item-description'})
        if desc_block:
            description = desc_block.get_text(strip=True)
        else:
            description = "Описание не найдено"
        
        if len(description) > 800:
            description = description[:800] + "..."
        
        return description
    except:
        return "Не удалось загрузить описание"

def parse_avito_ads(html, config):
    """Парсит объявления"""
    soup = BeautifulSoup(html, 'html.parser')
    items = soup.find_all('div', attrs={'data-marker': 'item'})
    
    if not items:
        items = soup.find_all('div', class_='iva-item-root')
    
    ads = []
    for item in items:
        try:
            ad_id = item.get('data-item-id') or str(hash(str(item)))
            
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
                digits = ''.join(c for c in price_text if c.isdigit())
                if digits:
                    price = int(digits[:6])
            
            if config['min_price'] <= price <= config['max_price'] and price > 0:
                ads.append({
                    'id': ad_id,
                    'title': title,
                    'price': price,
                    'link': link
                })
        except:
            continue
    
    return ads

def monitoring_loop():
    """Основной цикл мониторинга"""
    global monitoring_active
    
    seen_ads = load_seen_ads()
    
    while monitoring_active:
        try:
            config = load_config()
            
            # Загружаем страницу
            response = requests.get(config['avito_url'], headers=HEADERS, timeout=30)
            
            # Парсим объявления
            ads = parse_avito_ads(response.text, config)
            
            # Проверяем новые
            for ad in ads:
                if not monitoring_active:
                    break
                    
                if ad['id'] not in seen_ads:
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
            
            # Ждем следующую проверку
            for _ in range(config['check_delay']):
                if not monitoring_active:
                    break
                time.sleep(1)
                
        except Exception as e:
            time.sleep(60)

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
    
    send_telegram_message("✅ Мониторинг запущен!", get_main_keyboard())

def stop_monitoring():
    """Останавливает мониторинг"""
    global monitoring_active
    
    monitoring_active = False
    send_telegram_message("⏹ Мониторинг остановлен!", get_main_keyboard())

def handle_message(text):
    """Обрабатывает сообщения от пользователя"""
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
    
    elif text == "🔄 Обновить":
        show_main_menu()
    
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
    
    elif text == "◀️ Назад":
        show_main_menu()
    
    # Обработка ввода значений
    elif ' ' in text and all(p.strip().isdigit() for p in text.split()):
        # Установка цены
        parts = text.split()
        min_p, max_p = int(parts[0]), int(parts[1])
        
        if min_p < max_p:
            config['min_price'] = min_p
            config['max_price'] = max_p
            save_config(config)
            send_telegram_message(f"✅ Цена установлена: {min_p} - {max_p} ₽", get_settings_keyboard())
        else:
            send_telegram_message("❌ Минимальная цена должна быть меньше максимальной", get_settings_keyboard())
    
    elif text.isdigit():
        # Установка интервала
        delay = int(text)
        if 10 <= delay <= 3600:
            config['check_delay'] = delay
            save_config(config)
            send_telegram_message(f"✅ Интервал установлен: {delay} сек", get_settings_keyboard())
        else:
            send_telegram_message("❌ Интервал должен быть от 10 до 3600 секунд", get_settings_keyboard())
    
    elif 'avito.ru' in text:
        # Установка URL
        if not text.startswith('http'):
            text = 'https://' + text
        config['avito_url'] = text
        save_config(config)
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
    except:
        return {"ok": False, "result": []}

def main():
    """Главная функция"""
    # Загружаем конфиг
    load_config()
    
    # Показываем меню при запуске
    show_main_menu()
    
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
            
        except Exception as e:
            time.sleep(5)

if __name__ == "__main__":
    main()

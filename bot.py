# bot.py
import logging
import sqlite3
import random
import asyncio
import time
import uuid
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from yoomoney import Client, Quickpay

# ==================== НАСТРОЙКИ ====================
TOKEN = "8697901011:AAGHFxmnV4qXE7io99ONR7R-xdjjBlNQPR8"  # ТВОЙ ТОКЕН

# Список ID администраторов
ADMIN_IDS = [123456789]  # ВСТАВЬ СВОЙ ID

# Настройки для платежей
COINS_PER_RUBLE = 20  # 20 монет за 1 рубль

# ========== ЮMONEY НАСТРОЙКИ ==========
YOOMONEY_CLIENT_ID = "FC76BEE7B7B22A6EE92BB50FE8013CC65057337980D43ECB6FEE2B23F34F2D25"
YOOMONEY_CLIENT_SECRET = "0740EB08029A5B336C45564755181E83BF3E7001174521B65A4366C3F4FEB7A3495B6DBC21D3A452554B53B8D3362209BF716E0CFEDCCEB0311EDE4C4DA35DC9"
YOOMONEY_TOKEN = "4100119038966136.B4BBCC6C90C99EA4146E4AE2BBFA1A05F8B74E30F57BFB71E64AF13716EE1B008B4A9B29001B4DC62D38C344D437AC8D5464B6A1E5B57354854535DA8E6D3BC5C8A479038663381652F8B2DB913F644342D7AC7B5BB8E22C97E0C40D26DBC4205A8F5B124B83A776A11A36E55B6C7A0349BC7543A72B0ED33EB7A0A5C2A876FE"
YOOMONEY_RECEIVER = "4100119038966136"  # НОМЕР КОШЕЛЬКА

# Клиент для проверки платежей
yoomoney_client = Client(YOOMONEY_TOKEN)

# Словарь для хранения ожидаемых платежей
pending_payments = {}

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Кейсы и их шансы (ОБНОВЛЕНЫ)
CASES = {
    'обычный': {
        'price': 30, 
        'chances': {'обычная': 0.7, 'редкая': 0.2, 'эпическая': 0.09, 'легендарная': 0.01},
        'description': '📦 Самый доступный кейс'
    },
    'редкий': {
        'price': 150, 
        'chances': {'обычная': 0.4, 'редкая': 0.4, 'эпическая': 0.17, 'легендарная': 0.03},
        'description': '📦 Повышенный шанс на редкие карты'
    },
    'эпический': {
        'price': 1000, 
        'chances': {'обычная': 0.3, 'редкая': 0.35, 'эпическая': 0.3, 'легендарная': 0.05},
        'description': '📦 Отличные шансы на эпические карты'
    },
    'легендарный': {
        'price': 10000, 
        'chances': {'обычная': 0.15, 'редкая': 0.3, 'эпическая': 0.45, 'легендарная': 0.09, 'золотой': 0.01},
        'description': '📦 Шанс на ЗОЛОТОЙ СУНДУК!'
    }
}

# Цены продажи карт (ОБНОВЛЕНЫ)
SELL_PRICES = {
    'обычная': (1, 100),
    'редкая': (50, 1000),
    'эпическая': (500, 2500),
    'легендарная': (5000, 60000),  # Максимум 60000
    'божественная': (10000000, 10000000)
}

# Состояния
user_games = {}
user_casino = {}
user_auction_view = {}
user_lottery_data = {}
user_input_data = {}
user_top_page = {}
user_top_category = {}

# Глобальные переменные
bitcoin_price = 5000
sale_active = False
sale_check_date = None

# ==================== ФУНКЦИЯ СОЗДАНИЯ ПЛАТЕЖА ====================
async def create_yoomoney_payment(amount, user_id):
    label = str(uuid.uuid4())[:8]
    
    quickpay = Quickpay(
        receiver=YOOMONEY_RECEIVER,
        quickpay_form="shop",
        targets=f"Пополнение баланса",
        paymentType="AC",
        sum=amount,
        label=label
    )
    
    pending_payments[label] = {
        'user_id': user_id,
        'amount': amount,
        'status': 'pending'
    }
    
    return quickpay.redirected_url, label

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  coins INTEGER DEFAULT 1000,
                  season_coins INTEGER DEFAULT 0,
                  max_coins INTEGER DEFAULT 0,
                  best_place INTEGER DEFAULT 0,
                  best_place_count INTEGER DEFAULT 0,
                  total_balloons INTEGER DEFAULT 0,
                  max_score INTEGER DEFAULT 0,
                  first_season INTEGER DEFAULT 0,
                  is_admin INTEGER DEFAULT 0,
                  last_daily TEXT,
                  bitcoin REAL DEFAULT 0,
                  total_donated INTEGER DEFAULT 0,
                  season_donated INTEGER DEFAULT 0,
                  total_cards INTEGER DEFAULT 0,
                  season_cards INTEGER DEFAULT 0,
                  created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS cards
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  card_type TEXT,
                  rarity TEXT,
                  is_in_safe INTEGER DEFAULT 0,
                  is_on_auction INTEGER DEFAULT 0,
                  received_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS golden_chests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  owner_id INTEGER,
                  is_on_auction INTEGER DEFAULT 0,
                  received_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS auctions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  item_id INTEGER,
                  item_type TEXT,
                  seller_id INTEGER,
                  start_price INTEGER DEFAULT 0,
                  current_bid INTEGER DEFAULT 0,
                  current_bidder_id INTEGER,
                  end_time TEXT,
                  is_active INTEGER DEFAULT 1,
                  is_completed INTEGER DEFAULT 0,
                  created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ultra_secret_card
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  owner_id INTEGER,
                  last_auction_at TEXT,
                  season INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS seasons
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  season_number INTEGER,
                  user_id INTEGER,
                  coins INTEGER,
                  place INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  from_user INTEGER,
                  to_user INTEGER,
                  amount INTEGER,
                  type TEXT,
                  timestamp TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS used_codes
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  code TEXT,
                  used_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount INTEGER,
                  coins INTEGER,
                  status TEXT,
                  payment_id TEXT,
                  created_at TEXT,
                  completed_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS first_places
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  season_number INTEGER,
                  achieved_at TEXT)''')
    
    for admin_id in ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO users (user_id, username, is_admin, created_at) VALUES (?, ?, ?, ?)",
                 (admin_id, f"admin_{admin_id}", 1, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

def register_user(user_id, username):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    if not c.fetchone():
        is_admin = 1 if user_id in ADMIN_IDS else 0
        c.execute("SELECT MAX(season_number) FROM seasons")
        result = c.fetchone()
        current_season = result[0] if result and result[0] else 0
        c.execute("INSERT INTO users (user_id, username, is_admin, first_season, coins, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (user_id, username, is_admin, current_season + 1, 1000, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user_coins(user_id):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 1000

def update_user_coins(user_id, amount):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ? WHERE user_id = ?", 
              (amount, amount, user_id))
    conn.commit()
    conn.close()

def update_user_balloons(user_id):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET total_balloons = total_balloons + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def update_max_score(user_id, score):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET max_score = MAX(max_score, ?) WHERE user_id = ?", (score, user_id))
    conn.commit()
    conn.close()

def update_user_donated(user_id, amount):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET total_donated = total_donated + ?, season_donated = season_donated + ? WHERE user_id = ?", 
              (amount, amount, user_id))
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1

def get_user_bitcoin(user_id):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT bitcoin FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def update_user_bitcoin(user_id, amount):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET bitcoin = bitcoin + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_user_cards_count(user_id):
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET total_cards = total_cards + 1, season_cards = season_cards + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ==================== ПРОВЕРКА СКИДОК ====================
async def check_sale():
    global sale_active, sale_check_date
    while True:
        now = datetime.now()
        if sale_check_date != now.day:
            sale_check_date = now.day
            sale_active = (now.day == 1 or now.day == 15)
        await asyncio.sleep(3600)

def get_price_with_sale(price):
    return price // 2 if sale_active else price

# ==================== ЕЖЕДНЕВНЫЙ БОНУС ====================
async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    c.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    last_daily_str = result[0] if result else None
    
    now = datetime.now()
    
    if last_daily_str:
        last_daily = datetime.fromisoformat(last_daily_str)
        if now.date() == last_daily.date():
            await update.message.reply_text("❌ Вы уже получали бонус сегодня!")
            conn.close()
            return
    
    amount = 1000
    c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ?, last_daily = ? WHERE user_id = ?", 
              (amount, amount, now.isoformat(), user_id))
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Ежедневный бонус! Получено {amount} монет!")

# ==================== МЕНЮ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user.id, user.username)
    
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("daily", "Ежедневный бонус"),
    ]
    await context.bot.set_my_commands(commands)
    
    sale_text = "🔥 СКИДКА 50%! 🔥" if sale_active else ""
    
    keyboard = [
        [InlineKeyboardButton("🎈 Играть", callback_data='play')],
        [InlineKeyboardButton("🏪 Магазин", callback_data='shop')],
        [InlineKeyboardButton("📦 Инвентарь", callback_data='inventory')],
        [InlineKeyboardButton("🏆 Топ лидеров", callback_data='top_menu')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("💰 Аукцион", callback_data='auction')],
        [InlineKeyboardButton("₿ Биткойн", callback_data='bitcoin')],
        [InlineKeyboardButton("🎰 Казино", callback_data='casino_menu')],
        [InlineKeyboardButton("💎 Купить монеты", callback_data='donate_menu')],
        [InlineKeyboardButton("💸 Передать монеты", callback_data='transfer_menu')],
        [InlineKeyboardButton("📅 Бонус", callback_data='daily_button')],
        [InlineKeyboardButton("ℹ️ Информация", callback_data='info')],
    ]
    
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("👑 Админ панель", callback_data='admin_panel')])
    
    await update.message.reply_text(
        f"🎮 Добро пожаловать, {user.first_name}!\n\n{sale_text}💰 Твои монеты: {get_user_coins(user.id)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== ТОП ЛИДЕРОВ ====================
async def top_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    user_top_page[user_id] = 0
    user_top_category[user_id] = 'season_coins'
    
    await show_top(query, user_id)

async def show_top(query, user_id, edit=True):
    page = user_top_page.get(user_id, 0)
    category = user_top_category.get(user_id, 'season_coins')
    
    categories = {
        'season_coins': '💰 Монеты в сезоне',
        'coins': '💎 Всего монет',
        'total_donated': '💸 Задоначено всего',
        'season_donated': '💸 Задоначено в сезоне',
        'total_cards': '🃏 Карточек всего',
        'season_cards': '🃏 Карточек в сезоне',
        'total_balloons': '🎈 Лопнуто шариков',
        'max_score': '🎯 Рекордный счет',
        'bitcoin': '₿ Биткойн'
    }
    
    category_name = categories.get(category, '💰 Монеты в сезоне')
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    c.execute(f"SELECT COUNT(*) FROM users WHERE {category} > 0")
    total = c.fetchone()[0]
    
    offset = page * 10
    c.execute(f"SELECT username, {category} FROM users WHERE {category} > 0 ORDER BY {category} DESC LIMIT 10 OFFSET ?", (offset,))
    top_list = c.fetchall()
    conn.close()
    
    text = f"🏆 ТОП ЛИДЕРОВ\n📊 {category_name}\n\n"
    
    if not top_list:
        text += "Пока нет участников"
    else:
        for i, (username, value) in enumerate(top_list, start=offset+1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            if category == 'bitcoin':
                display = f"{value:.8f} BTC"
            elif 'donated' in category:
                display = f"{value} руб."
            else:
                display = f"{value}"
            
            text += f"{medal} @{username or 'Unknown'} - {display}\n"
    
    text += f"\n📄 Страница {page + 1}/{(total-1)//10 + 1 if total > 0 else 1}"
    
    keyboard = []
    
    cat_buttons = []
    cat_buttons.append(InlineKeyboardButton("💰 Сезон", callback_data='top_cat_season_coins'))
    cat_buttons.append(InlineKeyboardButton("💎 Всего", callback_data='top_cat_coins'))
    cat_buttons.append(InlineKeyboardButton("💸 Донат", callback_data='top_cat_total_donated'))
    keyboard.append(cat_buttons)
    
    cat_buttons2 = []
    cat_buttons2.append(InlineKeyboardButton("🃏 Всего", callback_data='top_cat_total_cards'))
    cat_buttons2.append(InlineKeyboardButton("🃏 Сезон", callback_data='top_cat_season_cards'))
    cat_buttons2.append(InlineKeyboardButton("🎈 Шарики", callback_data='top_cat_total_balloons'))
    keyboard.append(cat_buttons2)
    
    cat_buttons3 = []
    cat_buttons3.append(InlineKeyboardButton("🎯 Рекорд", callback_data='top_cat_max_score'))
    cat_buttons3.append(InlineKeyboardButton("₿ Биткойн", callback_data='top_cat_bitcoin'))
    keyboard.append(cat_buttons3)
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data='top_prev'))
    if offset + 10 < total:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data='top_next'))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    if edit:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def top_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if query.data == 'top_next':
        user_top_page[user_id] = user_top_page.get(user_id, 0) + 1
    elif query.data == 'top_prev':
        user_top_page[user_id] = max(0, user_top_page.get(user_id, 0) - 1)
    elif query.data.startswith('top_cat_'):
        category = query.data.replace('top_cat_', '')
        user_top_category[user_id] = category
        user_top_page[user_id] = 0
    
    await show_top(query, user_id)

# ==================== ИГРА ====================
async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    keyboard = [
        [
            InlineKeyboardButton("⬆️", callback_data='game_up'),
            InlineKeyboardButton("⬇️", callback_data='game_down'),
            InlineKeyboardButton("⬅️", callback_data='game_left'),
            InlineKeyboardButton("➡️", callback_data='game_right')
        ],
        [InlineKeyboardButton("❌ Закончить", callback_data='end_game')]
    ]
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    
    msg = await query.edit_message_text(
        "🎮 НОВАЯ ИГРА!\n\nСчет: 0\nМонет за шарик: 1",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    user_games[user_id] = {
        'score': 0, 'coins': 0, 'active': True,
        'message_id': msg.message_id, 'chat_id': msg.chat_id,
        'current_combo': [], 'current_index': 0, 'last_press': None
    }
    
    asyncio.create_task(game_loop(user_id, context))

def get_combo_length(score):
    if score < 5: return 1
    elif score < 10: return 2
    elif score < 15: return 3
    else: return 4

def get_time_limit(combo_length):
    if combo_length <= 2: return 3.0
    elif combo_length == 3: return 4.5
    else: return 6.0

def get_coins_per_balloon(score):
    return (score // 3) + 1

async def generate_combo(length):
    return [random.choice(['up', 'down', 'left', 'right']) for _ in range(length)]

def direction_to_emoji(d):
    return {'up': '⬆️', 'down': '⬇️', 'left': '⬅️', 'right': '➡️'}[d]

async def game_loop(user_id, context):
    game = user_games.get(user_id)
    if not game: return
    
    while user_id in user_games and user_games[user_id]['active']:
        combo_length = get_combo_length(game['score'])
        combo = await generate_combo(combo_length)
        time_limit = get_time_limit(combo_length)
        
        game['current_combo'] = combo
        game['current_index'] = 0
        game['last_press'] = None
        
        coins_per = get_coins_per_balloon(game['score'])
        
        keyboard = [
            [
                InlineKeyboardButton("⬆️", callback_data='game_up'),
                InlineKeyboardButton("⬇️", callback_data='game_down'),
                InlineKeyboardButton("⬅️", callback_data='game_left'),
                InlineKeyboardButton("➡️", callback_data='game_right')
            ],
            [InlineKeyboardButton("❌ Закончить", callback_data='end_game')]
        ]
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
        
        start = datetime.now()
        
        try:
            await context.bot.edit_message_text(
                chat_id=game['chat_id'], message_id=game['message_id'],
                text=f"🎮 ИГРА\n\nСчет: {game['score']}\nМонет за шарик: {coins_per}\nВремя: {time_limit}с\n\n🎯 Повтори: {' '.join([direction_to_emoji(d) for d in combo])}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except: pass
        
        while game['current_index'] < len(combo):
            elapsed = (datetime.now() - start).total_seconds()
            if elapsed > time_limit:
                await game_over(user_id, context, "⏰ Время вышло!")
                return
            
            await asyncio.sleep(0.1)
            if user_id not in user_games: return
            
            if game['last_press'] == combo[game['current_index']]:
                game['current_index'] += 1
                game['last_press'] = None
            elif game['last_press'] is not None:
                await game_over(user_id, context, "❌ Неправильно!")
                return
        
        coins = get_coins_per_balloon(game['score'])
        game['score'] += 1
        game['coins'] += coins
        update_user_coins(user_id, coins)
        update_user_balloons(user_id)
        
        try:
            await context.bot.edit_message_text(
                chat_id=game['chat_id'], message_id=game['message_id'],
                text=f"🎮 ИГРА\n\n✅ +{coins} монет!\nСчет: {game['score']}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except: pass
        
        await asyncio.sleep(1)

async def handle_game_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id in user_games:
        user_games[q.from_user.id]['last_press'] = q.data.replace('game_', '')
        await q.answer()

async def game_over(user_id, context, reason):
    if user_id in user_games:
        g = user_games[user_id]
        update_max_score(user_id, g['score'])
        try:
            await context.bot.edit_message_text(
                chat_id=g['chat_id'], message_id=g['message_id'],
                text=f"{reason}\n\nСчет: {g['score']}\nМонет: {g['coins']}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎮 Снова", callback_data='play'),
                    InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
                ]])
            )
        except: pass
        del user_games[user_id]

# ==================== МАГАЗИН ====================
async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    coins = get_user_coins(user_id)
    sale = "🔥 СКИДКА 50%! 🔥\n" if sale_active else ""
    
    text = f"🏪 МАГАЗИН\n\n{sale}💰 Монет: {coins}\n\n"
    for name, data in CASES.items():
        price = get_price_with_sale(data['price'])
        text += f"{data['description']}\n💎 {name.upper()} - {price}💰\n"
    
    text += "\n🎲 ЛОТЕРЕИ:\n"
    text += "• 1500💰: выигрыш 1500-10000\n"
    text += "• 5000💰: выигрыш 5000-25000\n"
    text += "• 10000💰: выигрыш 10000-75000\n"
    
    keyboard = []
    for name in CASES:
        price = get_price_with_sale(CASES[name]['price'])
        keyboard.append([InlineKeyboardButton(f"📦 {name.upper()} ({price}💰)", callback_data=f'buy_{name}')])
    
    for p in [1500, 5000, 10000]:
        price = get_price_with_sale(p)
        keyboard.append([InlineKeyboardButton(f"🎲 Лотерея {p}💰 ({price}💰)", callback_data=f'lottery_{p}')])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== ПОКУПКА КЕЙСА ====================
async def buy_case(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    case = query.data.replace('buy_', '')
    
    logger.info(f"Покупка кейса: user_id={user_id}, case={case}")
    
    if case not in CASES:
        logger.error(f"Неизвестный тип кейса: {case}")
        await query.answer("❌ Ошибка: неизвестный кейс!")
        return
    
    price = get_price_with_sale(CASES[case]['price'])
    
    conn = None
    try:
        conn = sqlite3.connect('game_bot.db', timeout=10)
        c = conn.cursor()
        
        c.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        if not result or result[0] < price:
            await query.answer("❌ Недостаточно монет!")
            return
        
        c.execute("UPDATE users SET coins = coins - ?, season_coins = season_coins - ? WHERE user_id = ?", (price, price, user_id))
        c.execute("UPDATE users SET total_cards = total_cards + 1, season_cards = season_cards + 1 WHERE user_id = ?", (user_id,))
        
        rand = random.random()
        cum = 0
        prize = None
        for rarity, chance in CASES[case]['chances'].items():
            cum += chance
            if rand <= cum:
                prize = rarity
                break
        
        if prize == 'золотой':
            c.execute("INSERT INTO golden_chests (owner_id, received_at) VALUES (?, ?)", 
                     (user_id, datetime.now().isoformat()))
            text = f"✨ ЗОЛОТОЙ СУНДУК!\nМожно открыть сразу в инвентаре!"
        elif prize == 'божественная':
            c.execute("INSERT INTO cards (user_id, card_type, rarity, received_at) VALUES (?, ?, ?, ?)",
                     (user_id, case, prize, datetime.now().isoformat()))
            text = f"✨✨✨ БОЖЕСТВЕННАЯ КАРТА! ✨✨✨"
        else:
            c.execute("INSERT INTO cards (user_id, card_type, rarity, received_at) VALUES (?, ?, ?, ?)",
                     (user_id, case, prize, datetime.now().isoformat()))
            text = f"🎉 {prize.upper()} КАРТОЧКА!"
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Ошибка при покупке кейса: {e}")
        if conn:
            conn.rollback()
        await query.answer("❌ Ошибка при покупке!")
        return
    finally:
        if conn:
            conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📦 Ещё", callback_data=f'buy_{case}'),
         InlineKeyboardButton("🏪 Магазин", callback_data='shop')],
        [InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== ИНВЕНТАРЬ ====================
async def inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    c.execute("SELECT id, rarity FROM cards WHERE user_id = ? AND is_in_safe = 0 AND is_on_auction = 0", (user_id,))
    cards = c.fetchall()
    
    c.execute("SELECT id FROM golden_chests WHERE owner_id = ? AND is_on_auction = 0", (user_id,))
    chests = c.fetchall()
    conn.close()
    
    if not cards and not chests:
        await q.edit_message_text("📦 Инвентарь пуст!", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]]))
        return
    
    text = "📦 ИНВЕНТАРЬ\n\n"
    keyboard = []
    
    if chests:
        text += "✨ ЗОЛОТЫЕ СУНДУКИ:\n"
        for cid, in chests:
            text += f"  🟡 Сундук #{cid} - ГОТОВ К ОТКРЫТИЮ!\n"
            keyboard.append([
                InlineKeyboardButton(f"✨ Открыть #{cid}", callback_data=f'open_chest_{cid}'),
                InlineKeyboardButton(f"📢 Аукцион #{cid}", callback_data=f'auction_start_chest_{cid}')
            ])
    
    if cards:
        text += "\n🃏 КАРТОЧКИ:\n"
        total = 0
        for cid, rar in cards:
            if rar == 'божественная':
                price = 10000000
            else:
                price = (SELL_PRICES[rar][0] + SELL_PRICES[rar][1]) // 2
            total += price
            text += f"  #{cid}: {rar.upper()} - ~{price}💰\n"
            keyboard.append([
                InlineKeyboardButton(f"💰 Продать #{cid}", callback_data=f'sell_{cid}'),
                InlineKeyboardButton(f"📢 Аукцион #{cid}", callback_data=f'auction_start_card_{cid}')
            ])
        
        if len(cards) > 1:
            keyboard.append([InlineKeyboardButton(f"💰 Продать всё (~{total}💰)", callback_data='sell_all')])
    
    keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data='main_menu')])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== ПРОДАЖА КАРТ ====================
async def sell_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    card_id = int(q.data.split('_')[1])
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT rarity FROM cards WHERE id = ? AND user_id = ?", (card_id, user_id))
    res = c.fetchone()
    
    if not res:
        await q.answer("❌ Карточка не найдена!")
        conn.close()
        return
    
    if res[0] == 'божественная':
        price = 10000000
    else:
        price = random.randint(SELL_PRICES[res[0]][0], SELL_PRICES[res[0]][1])
    
    c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ? WHERE user_id = ?", 
              (price, price, user_id))
    c.execute("DELETE FROM cards WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()
    
    await q.edit_message_text(f"✅ Продано за {price}💰", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("📦 Инвентарь", callback_data='inventory'),
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

async def sell_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT id, rarity FROM cards WHERE user_id = ? AND is_in_safe = 0", (user_id,))
    cards = c.fetchall()
    
    if not cards:
        await q.answer("❌ Нет карточек!")
        conn.close()
        return
    
    total = 0
    for cid, rar in cards:
        if rar == 'божественная':
            price = 10000000
        else:
            price = random.randint(SELL_PRICES[rar][0], SELL_PRICES[rar][1])
        total += price
        c.execute("DELETE FROM cards WHERE id = ?", (cid,))
    
    c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ? WHERE user_id = ?", 
              (total, total, user_id))
    conn.commit()
    conn.close()
    
    await q.edit_message_text(f"✅ Продано {len(cards)} карт за {total}💰", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

# ==================== ОТКРЫТИЕ СУНДУКА ====================
async def open_golden_chest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    chest_id = int(q.data.split('_')[2])
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("SELECT id FROM golden_chests WHERE id = ? AND owner_id = ?", (chest_id, user_id))
    res = c.fetchone()
    
    if not res:
        await q.answer("❌ Сундук не найден!", show_alert=True)
        conn.close()
        return
    
    if random.random() < 0.01:
        c.execute("INSERT INTO cards (user_id, card_type, rarity, received_at) VALUES (?, ?, ?, ?)",
                 (user_id, 'golden_chest', 'божественная', datetime.now().isoformat()))
        update_user_cards_count(user_id)
        text = "✨✨✨ БОЖЕСТВЕННАЯ КАРТА! ✨✨✨"
    else:
        coins = random.randint(-100000, 500000)  # Изменено с 1000000 на 500000
        c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ? WHERE user_id = ?", 
                  (coins, coins, user_id))
        text = f"💰 {coins} монет" if coins >= 0 else f"💸 {coins} монет"
    
    c.execute("DELETE FROM golden_chests WHERE id = ?", (chest_id,))
    conn.commit()
    conn.close()
    
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

# ==================== ИНФОРМАЦИЯ ====================
async def info_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    
    text = "ℹ️ ИНФОРМАЦИЯ\n\n"
    text += "💰 **ЦЕНЫ КАРТ:**\n"
    text += "• Обычная: 1-100💰\n"
    text += "• Редкая: 50-1000💰\n"
    text += "• Эпическая: 500-2500💰\n"
    text += "• Легендарная: 5000-60000💰\n"  # Изменено с 100000 на 60000
    text += "• Божественная: 1.000.000💰\n\n"
    
    text += "📊 **ШАНСЫ ИЗ КЕЙСОВ:**\n"
    for name, data in CASES.items():
        text += f"\n**{name.upper()}:**\n"
        for rarity, chance in data['chances'].items():
            percent = int(chance * 100) if (chance * 100).is_integer() else round(chance * 100, 1)
            text += f"  • {rarity}: {percent}%\n"
    
    text += "\n✨ **ЗОЛОТОЙ СУНДУК:**\n"
    text += "• Можно получить из легендарного кейса (шанс 1%)\n"
    text += "• Открывается сразу (без ожидания)\n"
    text += "• **Шанс 1%** на **БОЖЕСТВЕННУЮ КАРТУ** ✨\n"
    text += "• В остальных случаях: от **-100.000** до **+500.000** монет 💰\n"  # Изменено
    text += "• Можно выставить на аукцион или открыть\n"
    
    await q.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

# ==================== ЛОТЕРЕЯ ====================
async def lottery_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    price = int(q.data.split('_')[1])
    sale_price = get_price_with_sale(price)
    
    if get_user_coins(user_id) < sale_price:
        await q.answer(f"❌ Нужно {sale_price}💰")
        return
    
    if price == 1500: win_range = (1500, 10000)
    elif price == 5000: win_range = (5000, 25000)
    else: win_range = (10000, 75000)
    
    win = random.randint(win_range[0], win_range[1])
    win_ticket = random.randint(1, 3)
    
    user_lottery_data[user_id] = {
        'price': price, 'sale_price': sale_price,
        'win': win, 'win_ticket': win_ticket
    }
    
    keyboard = [
        [
            InlineKeyboardButton("🎫1", callback_data=f'lottery_{price}_1'),
            InlineKeyboardButton("🎫2", callback_data=f'lottery_{price}_2'),
            InlineKeyboardButton("🎫3", callback_data=f'lottery_{price}_3')
        ],
        [InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]
    ]
    await q.edit_message_text(
        f"🎲 ЛОТЕРЕЯ\n\nЦена: {sale_price}💰\nВыигрыш: {win}💰",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def lottery_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    parts = q.data.split('_')
    price = int(parts[1])
    ticket = int(parts[2])
    
    if user_id not in user_lottery_data:
        await q.answer("❌ Лотерея не найдена!")
        return
    
    data = user_lottery_data[user_id]
    if data['price'] != price:
        await q.answer("❌ Ошибка!")
        return
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins - ?, season_coins = season_coins - ? WHERE user_id = ?", 
              (data['sale_price'], data['sale_price'], user_id))
    
    if ticket == data['win_ticket']:
        c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ? WHERE user_id = ?", 
                 (data['win'], data['win'], user_id))
        text = f"🎉 ПОБЕДА! +{data['win']}💰"
    else:
        text = f"😢 Проигрыш! Выигрышный билет был №{data['win_ticket']}"
    
    conn.commit()
    conn.close()
    del user_lottery_data[user_id]
    
    keyboard = [[InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== СТАТИСТИКА ====================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    c.execute("""SELECT coins, season_coins, max_coins, best_place, best_place_count,
                        total_balloons, max_score, first_season, bitcoin,
                        total_donated, season_donated, total_cards, season_cards
                 FROM users WHERE user_id = ?""", (user_id,))
    res = c.fetchone()
    
    if not res:
        await q.edit_message_text("❌ Ошибка")
        conn.close()
        return
    
    (coins, season_coins, max_coins, best_place, best_place_count,
     total_balloons, max_score, first_season, bitcoin,
     total_donated, season_donated, total_cards, season_cards) = res
    
    c.execute("SELECT COUNT(*) FROM cards WHERE user_id = ?", (user_id,))
    current_cards = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM first_places WHERE user_id = ?", (user_id,))
    first_places = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM seasons WHERE user_id = ?", (user_id,))
    seasons_count = c.fetchone()[0]
    
    conn.close()
    
    text = f"📊 ТВОЯ СТАТИСТИКА\n\n"
    text += f"💰 Всего монет: {coins}\n"
    text += f"💎 В сезоне: {season_coins}\n"
    text += f"🏆 Рекорд монет: {max_coins}\n"
    text += f"🥇 Лучшее место: {best_place if best_place else 'нет'}\n"
    text += f"👑 Побед в сезонах: {first_places}\n"
    text += f"📅 Первый сезон: #{first_season}\n"
    text += f"📊 Участий в сезонах: {seasons_count}\n"
    text += f"🎈 Лопнуто шариков: {total_balloons}\n"
    text += f"🎯 Рекордный счет: {max_score}\n"
    text += f"🃏 Карточек сейчас: {current_cards}\n"
    text += f"📦 Получено карточек всего: {total_cards}\n"
    text += f"📦 Получено в этом сезоне: {season_cards}\n"
    text += f"💸 Задоначено всего: {total_donated} руб.\n"
    text += f"💸 Задоначено в сезоне: {season_donated} руб.\n"
    text += f"₿ Биткойн: {bitcoin:.8f} BTC"
    
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

# ==================== ПЕРЕДАЧА МОНЕТ ====================
async def transfer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    await q.edit_message_text(
        f"💸 ПЕРЕДАЧА МОНЕТ\n\n💰 Твой баланс: {get_user_coins(user_id)}\n\nФормат: /transfer @username сумма\nПример: /transfer @durov 100",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

async def transfer_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("❌ Используй: /transfer @username сумма")
            return
        
        from_id = update.effective_user.id
        to_name = args[0].replace('@', '')
        amount = int(args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть больше 0")
            return
        
        conn = sqlite3.connect('game_bot.db', timeout=10)
        c = conn.cursor()
        
        c.execute("SELECT coins FROM users WHERE user_id = ?", (from_id,))
        from_coins = c.fetchone()
        if not from_coins or from_coins[0] < amount:
            await update.message.reply_text("❌ Недостаточно монет!")
            conn.close()
            return
        
        c.execute("SELECT user_id FROM users WHERE username = ?", (to_name,))
        to_user = c.fetchone()
        if not to_user:
            await update.message.reply_text("❌ Пользователь не найден!")
            conn.close()
            return
        
        to_id = to_user[0]
        if to_id == from_id:
            await update.message.reply_text("❌ Нельзя передавать самому себе!")
            conn.close()
            return
        
        c.execute("UPDATE users SET coins = coins - ?, season_coins = season_coins - ? WHERE user_id = ?", 
                 (amount, amount, from_id))
        c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ? WHERE user_id = ?", 
                 (amount, amount, to_id))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Переведено {amount}💰 @{to_name}")
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ==================== БИТКОЙН ====================
async def update_bitcoin():
    global bitcoin_price
    while True:
        await asyncio.sleep(3600)
        change = random.randint(-1000, 1000)
        bitcoin_price = max(100, bitcoin_price + change)
        logger.info(f"Новая цена биткойна: {bitcoin_price}")

async def bitcoin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    btc = get_user_bitcoin(user_id)
    
    text = f"₿ БИТКОЙН\n\n"
    text += f"💰 Текущая цена: {bitcoin_price} монет за 1 BTC\n"
    text += f"🪙 Твой баланс: {btc:.8f} BTC\n"
    text += f"💎 Твои монеты: {get_user_coins(user_id)}\n\n"
    text += f"📊 Стоимость твоего BTC: {int(btc * bitcoin_price)} монет\n"
    text += f"⏰ Цена обновляется каждый час\n"
    
    keyboard = [
        [
            InlineKeyboardButton("📈 Купить BTC", callback_data='bitcoin_buy'),
            InlineKeyboardButton("📉 Продать BTC", callback_data='bitcoin_sell')
        ],
        [InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def bitcoin_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_input_data[q.from_user.id] = {'action': 'bitcoin_buy'}
    await q.edit_message_text("📈 Введите количество BTC:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

async def bitcoin_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_input_data[q.from_user.id] = {'action': 'bitcoin_sell'}
    await q.edit_message_text("📉 Введите количество BTC:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

# ==================== КАЗИНО ====================
async def casino_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.edit_message_text(
        "🎰 КАЗИНО\n\nПравила:\n• Делаешь ставку\n• 2 кнопки - одна проигрыш, другая ×1.5\n• Можешь играть бесконечно\n• В любой момент забрать выигрыш",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🎰 Начать", callback_data='casino_start'),
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

async def casino_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    user_input_data[user_id] = {'action': 'casino_bet'}
    current_coins = get_user_coins(user_id)
    
    await q.edit_message_text(
        f"🎰 Введите ставку (минимум 10 монет)\n💰 Твой баланс: {current_coins}💰",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

async def casino_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    choice = q.data.replace('casino_', '')
    
    if user_id not in user_casino:
        await q.answer("❌ Игра не найдена!", show_alert=True)
        return
    
    game = user_casino[user_id]
    
    if choice == 'take':
        update_user_coins(user_id, game['current'])
        new_balance = get_user_coins(user_id)
        
        await q.edit_message_text(
            f"✅ Ты забрал {game['current']}💰\n💰 Текущий баланс: {new_balance}💰",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎰 Снова", callback_data='casino_menu'),
                InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
            ]])
        )
        del user_casino[user_id]
        return
    
    win = random.choice(['left', 'right'])
    if choice == win:
        game['current'] = int(game['current'] * 1.5)
        text = f"✅ +{int(game['current']*0.5)}💰\n💰 Текущий выигрыш: {game['current']}💰"
    else:
        update_user_coins(user_id, -game['bet'])
        new_balance = get_user_coins(user_id)
        
        await q.edit_message_text(
            f"❌ Проигрыш! -{game['bet']}💰\n💰 Текущий баланс: {new_balance}💰",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🎰 Снова", callback_data='casino_menu'),
                InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
            ]])
        )
        del user_casino[user_id]
        return
    
    keyboard = [
        [InlineKeyboardButton("⬅️ Левая", callback_data='casino_left'),
         InlineKeyboardButton("➡️ Правая", callback_data='casino_right')],
        [InlineKeyboardButton("💰 Забрать", callback_data='casino_take')],
        [InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== ДОНАТ ====================
async def donate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    sale_text = "🔥 СКИДКА 50%! ×2 монет 🔥" if sale_active else ""
    
    await q.edit_message_text(
        f"💎 ПОКУПКА МОНЕТ\n\n{sale_text}\n💰 Курс: 20 монет = 1 рубль\n💳 Минимальная сумма: 50 рублей (1000 монет)\n\nДля покупки нажмите кнопку ниже",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💳 Купить монеты", callback_data='donate_buy'),
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

async def donate_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    user_input_data[user_id] = {'action': 'donate_yoomoney'}
    await q.edit_message_text(
        "💎 Введите сумму в рублях (минимум 50):",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

# ==================== АУКЦИОН (ИСПРАВЛЕННЫЙ) ====================
async def check_expired_auctions(app):
    while True:
        try:
            await asyncio.sleep(60)
            
            conn = sqlite3.connect('game_bot.db', timeout=10)
            c = conn.cursor()
            
            now = datetime.now()
            
            c.execute("""SELECT id, item_id, item_type, seller_id, current_bidder_id, current_bid, end_time 
                         FROM auctions WHERE is_active = 1""")
            auctions = c.fetchall()
            
            for auction_id, item_id, item_type, seller_id, winner_id, final_bid, end_time_str in auctions:
                end_time = datetime.fromisoformat(end_time_str)
                if now > end_time:
                    if winner_id:
                        if item_type == 'card':
                            c.execute("UPDATE cards SET user_id = ?, is_on_auction = 0 WHERE id = ?", (winner_id, item_id))
                        else:
                            c.execute("UPDATE golden_chests SET owner_id = ?, is_on_auction = 0 WHERE id = ?", (winner_id, item_id))
                        c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (final_bid, seller_id))
                        logger.info(f"Аукцион #{auction_id} завершен")
                    else:
                        if item_type == 'card':
                            c.execute("UPDATE cards SET is_on_auction = 0 WHERE id = ?", (item_id,))
                        else:
                            c.execute("UPDATE golden_chests SET is_on_auction = 0 WHERE id = ?", (item_id,))
                    
                    c.execute("UPDATE auctions SET is_active = 0 WHERE id = ?", (auction_id,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Ошибка при проверке аукционов: {e}")
            await asyncio.sleep(60)

async def auction_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    c.execute("""SELECT a.id, 
                        CASE WHEN a.item_type = 'card' THEN c.rarity ELSE 'золотой сундук' END as rarity,
                        a.current_bid, u.username, a.seller_id, a.start_price, a.item_id, a.end_time, a.item_type
                 FROM auctions a 
                 LEFT JOIN cards c ON a.item_id = c.id AND a.item_type = 'card'
                 LEFT JOIN users u ON a.seller_id = u.user_id 
                 WHERE a.is_active = 1 
                 ORDER BY a.end_time ASC""")
    auctions = c.fetchall()
    conn.close()
    
    if not auctions:
        await q.edit_message_text(
            "💰 АУКЦИОН\n\nНет активных лотов\n\nЧтобы выставить карту, зайди в Инвентарь и нажми '📢 Аукцион'",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
            ]])
        )
        return
    
    if user_id not in user_auction_view:
        user_auction_view[user_id] = 0
    
    current = user_auction_view[user_id]
    if current >= len(auctions):
        current = len(auctions) - 1
        user_auction_view[user_id] = current
    
    auction = auctions[current]
    aid, rarity, bid, seller, sid, start, iid, end_str, item_type = auction
    
    end_time = datetime.fromisoformat(end_str)
    time_left = end_time - datetime.now()
    hours = time_left.seconds // 3600
    minutes = (time_left.seconds % 3600) // 60
    
    text = f"💰 АУКЦИОН (Лот {current+1}/{len(auctions)})\n\n"
    text += f"🎴 Предмет: {rarity.upper()}\n"
    text += f"👤 Продавец: @{seller}\n"
    text += f"💰 Старт: {start}💰\n"
    text += f"💎 Текущая ставка: {bid}💰\n"
    text += f"⏰ Осталось: {hours}ч {minutes}м\n"
    
    keyboard = []
    nav = []
    if current > 0:
        nav.append(InlineKeyboardButton("◀️ Предыдущий", callback_data='auction_prev'))
    if current < len(auctions)-1:
        nav.append(InlineKeyboardButton("Следующий ▶️", callback_data='auction_next'))
    if nav:
        keyboard.append(nav)
    
    if user_id != sid:
        keyboard.append([InlineKeyboardButton("💰 Сделать ставку", callback_data=f'auction_bid_{aid}')])
    
    keyboard.append([InlineKeyboardButton("🏠 Меню", callback_data='main_menu')])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def auction_navigate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    if q.data == 'auction_next':
        user_auction_view[user_id] = user_auction_view.get(user_id, 0) + 1
    else:
        user_auction_view[user_id] = user_auction_view.get(user_id, 0) - 1
    
    await auction_menu(update, context)

async def auction_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    data_parts = q.data.split('_')
    item_type = data_parts[2]  # card или chest
    item_id = int(data_parts[3])
    
    logger.info(f"Аукцион: пользователь {user_id} выставляет {item_type} #{item_id}")
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    # Проверяем, не на аукционе ли уже
    if item_type == 'card':
        c.execute("SELECT is_on_auction FROM cards WHERE id = ? AND user_id = ?", (item_id, user_id))
    else:
        c.execute("SELECT is_on_auction FROM golden_chests WHERE id = ? AND owner_id = ?", (item_id, user_id))
    
    res = c.fetchone()
    
    if not res:
        await q.answer("❌ Предмет не найден!", show_alert=True)
        conn.close()
        return
    
    if res[0] == 1:
        await q.answer("❌ Предмет уже на аукционе!", show_alert=True)
        conn.close()
        return
    
    conn.close()
    user_input_data[user_id] = {'action': 'auction_create', 'item_id': item_id, 'item_type': item_type, 'step': 'price'}
    await q.edit_message_text(
        "📢 СОЗДАНИЕ АУКЦИОНА - ШАГ 1/2\n\nВведите стартовую цену:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

async def auction_bid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    auction_id = int(q.data.split('_')[2])
    
    user_input_data[user_id] = {'action': 'auction_bid', 'auction_id': auction_id}
    await q.edit_message_text(
        f"💰 СТАВКА НА АУКЦИОН #{auction_id}\n\nВведите сумму ставки:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
        ]])
    )

# ==================== АДМИН ПАНЕЛЬ ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        await q.answer("❌ Нет прав!")
        return
    
    keyboard = [
        [InlineKeyboardButton("💰 Выдать монеты", callback_data='admin_give')],
        [InlineKeyboardButton("💎 Выдать себе", callback_data='admin_self')],
        [InlineKeyboardButton("📊 Статистика пользователя", callback_data='admin_stats')],
        [InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]
    ]
    await q.edit_message_text("👑 АДМИН ПАНЕЛЬ", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_give(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_input_data[q.from_user.id] = {'action': 'admin_give'}
    await q.edit_message_text("💰 Введите ID и сумму:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

async def admin_self(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_input_data[q.from_user.id] = {'action': 'admin_self'}
    await q.edit_message_text("💰 Введите сумму:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_input_data[q.from_user.id] = {'action': 'admin_stats'}
    await q.edit_message_text("📊 Введите ID пользователя:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
    ]]))

# ==================== ЕЖЕДНЕВНЫЙ БОНУС (КНОПКА) ====================
async def daily_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    
    conn = sqlite3.connect('game_bot.db', timeout=10)
    c = conn.cursor()
    
    c.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    last_daily_str = result[0] if result else None
    
    now = datetime.now()
    
    if last_daily_str:
        last_daily = datetime.fromisoformat(last_daily_str)
        if now.date() == last_daily.date():
            await q.answer("❌ Бонус уже получен сегодня!")
            conn.close()
            return
    
    amount = 1000
    c.execute("UPDATE users SET coins = coins + ?, season_coins = season_coins + ?, last_daily = ? WHERE user_id = ?", 
              (amount, amount, now.isoformat(), user_id))
    
    conn.commit()
    conn.close()
    
    await q.edit_message_text(f"✅ Ежедневный бонус!\nПолучено {amount} монет!", 
                              reply_markup=InlineKeyboardMarkup([[
                                  InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
                              ]]))

# ==================== ГЛАВНОЕ МЕНЮ ====================
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    sale = "🔥 СКИДКА 50%! 🔥" if sale_active else ""
    
    keyboard = [
        [InlineKeyboardButton("🎈 Играть", callback_data='play'),
         InlineKeyboardButton("🏪 Магазин", callback_data='shop')],
        [InlineKeyboardButton("📦 Инвентарь", callback_data='inventory'),
         InlineKeyboardButton("🏆 Топ", callback_data='top_menu')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats'),
         InlineKeyboardButton("💰 Аукцион", callback_data='auction')],
        [InlineKeyboardButton("₿ Биткойн", callback_data='bitcoin'),
         InlineKeyboardButton("🎰 Казино", callback_data='casino_menu')],
        [InlineKeyboardButton("💎 Донат", callback_data='donate_menu'),
         InlineKeyboardButton("💸 Передать", callback_data='transfer_menu')],
        [InlineKeyboardButton("📅 Бонус", callback_data='daily_button')],
        [InlineKeyboardButton("ℹ️ Инфо", callback_data='info')],
    ]
    
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Админ", callback_data='admin_panel')])
    
    await q.edit_message_text(
        f"🏠 ГЛАВНОЕ МЕНЮ\n\n{sale}\n💰 Монет: {get_user_coins(user_id)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== ОБРАБОТЧИК ВВОДА ====================
async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_input_data:
        return
    
    data = user_input_data[user_id]
    action = data.get('action')
    text = update.message.text
    
    try:
        # КАЗИНО
        if action == 'casino_bet':
            try:
                bet = int(text)
            except ValueError:
                await update.message.reply_text("❌ Введите число!")
                return
                
            if bet < 10:
                await update.message.reply_text("❌ Минимум 10 монет")
                return
            
            current_coins = get_user_coins(user_id)
            
            if current_coins < bet:
                await update.message.reply_text(f"❌ Недостаточно монет! Твой баланс: {current_coins}💰")
                return
            
            update_user_coins(user_id, -bet)
            new_balance = get_user_coins(user_id)
            
            user_casino[user_id] = {'bet': bet, 'current': bet}
            
            keyboard = [
                [InlineKeyboardButton("⬅️ Левая", callback_data='casino_left'),
                 InlineKeyboardButton("➡️ Правая", callback_data='casino_right')],
                [InlineKeyboardButton("💰 Забрать", callback_data='casino_take')],
                [InlineKeyboardButton("🏠 Меню", callback_data='main_menu')]
            ]
            await update.message.reply_text(
                f"🎰 ИГРА!\n💰 Твоя ставка: {bet}💰\n💰 Текущий баланс: {new_balance}💰\n\nВыбери кнопку:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif action == 'bitcoin_buy':
            am = float(text.replace(',', '.'))
            if am <= 0:
                await update.message.reply_text("❌ Количество должно быть больше 0")
                return
            cost = int(am * bitcoin_price)
            if get_user_coins(user_id) < cost:
                await update.message.reply_text(f"❌ Недостаточно монет! Нужно {cost}💰")
                return
            update_user_coins(user_id, -cost)
            update_user_bitcoin(user_id, am)
            await update.message.reply_text(f"✅ Куплено {am:.8f} BTC")
        
        elif action == 'bitcoin_sell':
            am = float(text.replace(',', '.'))
            if am <= 0:
                await update.message.reply_text("❌ Количество должно быть больше 0")
                return
            if get_user_bitcoin(user_id) < am:
                await update.message.reply_text(f"❌ Недостаточно BTC! У вас {get_user_bitcoin(user_id):.8f} BTC")
                return
            profit = int(am * bitcoin_price)
            update_user_bitcoin(user_id, -am)
            update_user_coins(user_id, profit)
            await update.message.reply_text(f"✅ Продано за {profit}💰")
        
        elif action == 'donate_yoomoney':
            rub = int(text)
            if rub < 50:
                await update.message.reply_text("❌ Минимальная сумма 50 рублей")
                return
            
            payment_url, label = await create_yoomoney_payment(rub, user_id)
            
            await update.message.reply_text(
                f"💳 **ОПЛАТА ЧЕРЕЗ ЮMONEY**\n\n"
                f"Сумма: {rub}₽\n"
                f"К оплате: {rub}₽\n\n"
                f"1. Перейдите по ссылке:\n{payment_url}\n\n"
                f"2. Оплатите\n"
                f"3. Нажмите кнопку ниже ПОСЛЕ оплаты\n\n"
                f"⏳ Платеж действителен 1 час",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Я ОПЛАТИЛ", callback_data=f'check_payment_{label}')
                ], [
                    InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
                ]])
            )
        
        elif action == 'auction_create':
            if data.get('step') == 'price':
                price = int(text)
                if price < 1:
                    await update.message.reply_text("❌ Цена должна быть больше 0")
                    return
                user_input_data[user_id] = {
                    'action': 'auction_create',
                    'item_id': data['item_id'],
                    'item_type': data['item_type'],
                    'price': price,
                    'step': 'time'
                }
                await update.message.reply_text("📢 ШАГ 2/2\n\nВведите время в минутах (5-1440):")
                return
            
            elif data.get('step') == 'time':
                minutes = int(text)
                if minutes < 5 or minutes > 1440:
                    await update.message.reply_text("❌ Время должно быть от 5 до 1440 минут")
                    return
                
                conn = sqlite3.connect('game_bot.db', timeout=10)
                c = conn.cursor()
                
                if data['item_type'] == 'card':
                    c.execute("UPDATE cards SET is_on_auction = 1 WHERE id = ?", (data['item_id'],))
                else:
                    c.execute("UPDATE golden_chests SET is_on_auction = 1 WHERE id = ?", (data['item_id'],))
                
                end = (datetime.now() + timedelta(minutes=minutes)).isoformat()
                c.execute("""INSERT INTO auctions 
                            (item_id, item_type, seller_id, start_price, current_bid, end_time, created_at) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)""",
                         (data['item_id'], data['item_type'], user_id, data['price'], data['price'], end, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                
                await update.message.reply_text(f"✅ Аукцион создан!\nЦена: {data['price']}💰\nВремя: {minutes} мин")
        
        elif action == 'auction_bid':
            auction_id = data['auction_id']
            amount = int(text)
            
            conn = sqlite3.connect('game_bot.db', timeout=10)
            c = conn.cursor()
            c.execute("SELECT current_bid, seller_id, end_time FROM auctions WHERE id = ? AND is_active = 1", (auction_id,))
            res = c.fetchone()
            
            if not res:
                await update.message.reply_text("❌ Аукцион не найден")
                conn.close()
                return
            
            bid, seller, end_str = res
            end_time = datetime.fromisoformat(end_str)
            if datetime.now() > end_time:
                await update.message.reply_text("❌ Аукцион уже завершен")
                conn.close()
                return
            if amount <= bid:
                await update.message.reply_text(f"❌ Ставка должна быть больше {bid}")
                conn.close()
                return
            if user_id == seller:
                await update.message.reply_text("❌ Нельзя ставить на свой лот")
                conn.close()
                return
            
            c.execute("SELECT coins FROM users WHERE user_id = ?", (user_id,))
            coins = c.fetchone()[0]
            if coins < amount:
                await update.message.reply_text("❌ Недостаточно монет")
                conn.close()
                return
            
            c.execute("SELECT current_bidder_id, current_bid FROM auctions WHERE id = ?", (auction_id,))
            prev = c.fetchone()
            if prev and prev[0]:
                c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (prev[1], prev[0]))
            
            c.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (amount, user_id))
            c.execute("UPDATE auctions SET current_bid = ?, current_bidder_id = ? WHERE id = ?",
                     (amount, user_id, auction_id))
            conn.commit()
            conn.close()
            
            await update.message.reply_text(f"✅ Ставка {amount}💰 принята")
        
        elif action == 'admin_give':
            parts = text.split()
            if len(parts) != 2:
                await update.message.reply_text("❌ Формат: ID сумма")
                return
            target = int(parts[0])
            amount = int(parts[1])
            update_user_coins(target, amount)
            await update.message.reply_text(f"✅ Выдано {amount}💰 пользователю {target}")
        
        elif action == 'admin_self':
            amount = int(text)
            update_user_coins(user_id, amount)
            await update.message.reply_text(f"✅ Выдано {amount}💰 себе")
        
        elif action == 'admin_stats':
            target = int(text)
            conn = sqlite3.connect('game_bot.db', timeout=10)
            c = conn.cursor()
            c.execute("SELECT username, coins, season_coins, total_donated, total_cards FROM users WHERE user_id = ?", (target,))
            user = c.fetchone()
            conn.close()
            
            if user:
                await update.message.reply_text(
                    f"📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ {target}\n\n"
                    f"👤 Username: @{user[0]}\n"
                    f"💰 Монет: {user[1]}\n"
                    f"💎 В сезоне: {user[2]}\n"
                    f"💸 Задоначено: {user[3]} руб.\n"
                    f"🃏 Карточек: {user[4]}"
                )
            else:
                await update.message.reply_text("❌ Пользователь не найден")
        
        del user_input_data[user_id]
        
    except ValueError:
        await update.message.reply_text("❌ Введите число!")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")
        if user_id in user_input_data:
            del user_input_data[user_id]

# ==================== ПРОВЕРКА ПЛАТЕЖА ====================
async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    label = q.data.replace('check_payment_', '')
    
    if label not in pending_payments:
        await q.answer("❌ Платеж не найден", show_alert=True)
        return
    
    payment = pending_payments[label]
    
    try:
        history = yoomoney_client.operation_history(label=label)
        
        for operation in history.operations:
            if operation.status == 'success':
                coins = int(payment['amount'] * COINS_PER_RUBLE)
                if sale_active:
                    coins *= 2
                
                update_user_coins(payment['user_id'], coins)
                update_user_donated(payment['user_id'], payment['amount'])
                
                await q.message.edit_text(
                    f"✅ ОПЛАЧЕНО!\n\n"
                    f"Зачислено: {coins}💰",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🏠 Меню", callback_data='main_menu')
                    ]])
                )
                
                del pending_payments[label]
                return
        
        await q.answer("❌ Платеж не найден. Убедитесь что вы оплатили", show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка проверки платежа: {e}")
        await q.answer("❌ Ошибка проверки, попробуйте позже", show_alert=True)

# ==================== СЕЗОНЫ ====================
class SeasonManager:
    def __init__(self, app):
        self.app = app
        self.season = 0
    
    async def run(self):
        while True:
            now = datetime.now()
            days = (7 - now.weekday()) % 7
            if days == 0: days = 7
            next_monday = now.replace(hour=0, minute=0, second=0) + timedelta(days=days)
            await asyncio.sleep((next_monday - now).total_seconds())
            await self.reset()
    
    async def reset(self):
        logger.info(f"Сброс сезона {self.season}")
        conn = sqlite3.connect('game_bot.db', timeout=10)
        c = conn.cursor()
        
        c.execute("SELECT user_id, season_coins FROM users WHERE season_coins > 0")
        for uid, coins in c.fetchall():
            c.execute("UPDATE users SET max_coins = MAX(max_coins, ?) WHERE user_id = ?", (coins, uid))
            c.execute("INSERT INTO seasons (season_number, user_id, coins) VALUES (?, ?, ?)",
                     (self.season, uid, coins))
        
        c.execute("SELECT user_id, season_coins FROM users ORDER BY season_coins DESC")
        for place, (uid, coins) in enumerate(c.fetchall(), 1):
            if place == 1:
                c.execute("UPDATE users SET best_place = MIN(best_place, ?) WHERE user_id = ?", (place, uid))
                c.execute("UPDATE users SET best_place_count = best_place_count + 1 WHERE user_id = ?", (uid,))
                c.execute("INSERT INTO first_places (user_id, season_number) VALUES (?, ?)", (uid, self.season))
        
        c.execute("UPDATE users SET season_coins = 0, season_donated = 0, season_cards = 0")
        c.execute("UPDATE cards SET is_in_safe = 1")
        
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
        if users:
            owner = random.choice(users)[0]
            c.execute("DELETE FROM ultra_secret_card")
            c.execute("INSERT INTO ultra_secret_card (owner_id, season) VALUES (?, ?)", (owner, self.season))
            logger.info(f"Ультра секретная карта ушла пользователю {owner}")
        
        conn.commit()
        conn.close()
        self.season += 1

# ==================== ЗАПУСК ====================
def main():
    init_db()
    
    app = Application.builder().token(TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("daily", daily_bonus))
    app.add_handler(CommandHandler("transfer", transfer_coins))
    
    # Игра
    app.add_handler(CallbackQueryHandler(play_game, pattern='^play$'))
    app.add_handler(CallbackQueryHandler(handle_game_direction, pattern='^game_'))
    app.add_handler(CallbackQueryHandler(lambda u,c: game_over(u.callback_query.from_user.id, c, "❌ Игра завершена"), pattern='^end_game$'))
    
    # Магазин
    app.add_handler(CallbackQueryHandler(shop_menu, pattern='^shop$'))
    app.add_handler(CallbackQueryHandler(buy_case, pattern='^buy_'))
    
    # Лотерея
    app.add_handler(CallbackQueryHandler(lottery_menu, pattern='^lottery_\\d+$'))
    app.add_handler(CallbackQueryHandler(lottery_choose, pattern='^lottery_\\d+_\\d+$'))
    
    # Инвентарь
    app.add_handler(CallbackQueryHandler(inventory, pattern='^inventory$'))
    app.add_handler(CallbackQueryHandler(sell_card, pattern='^sell_\\d+$'))
    app.add_handler(CallbackQueryHandler(sell_all, pattern='^sell_all$'))
    app.add_handler(CallbackQueryHandler(open_golden_chest, pattern='^open_chest_\\d+$'))
    
    # Топ лидеров
    app.add_handler(CallbackQueryHandler(top_menu, pattern='^top_menu$'))
    app.add_handler(CallbackQueryHandler(top_navigate, pattern='^top_'))
    
    # Статистика и инфо
    app.add_handler(CallbackQueryHandler(stats, pattern='^stats$'))
    app.add_handler(CallbackQueryHandler(info_menu, pattern='^info$'))
    
    # Биткойн
    app.add_handler(CallbackQueryHandler(bitcoin_menu, pattern='^bitcoin$'))
    app.add_handler(CallbackQueryHandler(bitcoin_buy, pattern='^bitcoin_buy$'))
    app.add_handler(CallbackQueryHandler(bitcoin_sell, pattern='^bitcoin_sell$'))
    
    # Казино
    app.add_handler(CallbackQueryHandler(casino_menu, pattern='^casino_menu$'))
    app.add_handler(CallbackQueryHandler(casino_start, pattern='^casino_start$'))
    app.add_handler(CallbackQueryHandler(casino_game, pattern='^casino_'))
    
    # Донат
    app.add_handler(CallbackQueryHandler(donate_menu, pattern='^donate_menu$'))
    app.add_handler(CallbackQueryHandler(donate_buy, pattern='^donate_buy$'))
    
    # Перевод и бонус
    app.add_handler(CallbackQueryHandler(transfer_menu, pattern='^transfer_menu$'))
    app.add_handler(CallbackQueryHandler(daily_button, pattern='^daily_button$'))
    
    # Аукцион
    app.add_handler(CallbackQueryHandler(auction_menu, pattern='^auction$'))
    app.add_handler(CallbackQueryHandler(auction_navigate, pattern='^auction_next$|^auction_prev$'))
    app.add_handler(CallbackQueryHandler(auction_start, pattern='^auction_start_'))
    app.add_handler(CallbackQueryHandler(auction_bid, pattern='^auction_bid_'))
    
    # Админ
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin_panel$'))
    app.add_handler(CallbackQueryHandler(admin_give, pattern='^admin_give$'))
    app.add_handler(CallbackQueryHandler(admin_self, pattern='^admin_self$'))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern='^admin_stats$'))
    
    # Навигация
    app.add_handler(CallbackQueryHandler(main_menu, pattern='^main_menu$'))
    
    # Проверка платежа
    app.add_handler(CallbackQueryHandler(check_payment, pattern='^check_payment_'))
    
    # Ввод
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    
    # Фоновые задачи
    season_manager = SeasonManager(app)
    
    async def post_init(app):
        asyncio.create_task(check_sale())
        asyncio.create_task(update_bitcoin())
        asyncio.create_task(check_expired_auctions(app))
        asyncio.create_task(season_manager.run())
        logger.info("Бот запущен!")
    
    app.post_init = post_init
    app.run_polling()

if __name__ == '__main__':
    main()
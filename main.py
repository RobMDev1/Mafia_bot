import asyncio
import random
import re
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "7556597128:AAF94Iu3tJiew4sBwWpJW_9fav2eCWPE9U8"

bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()  # Using aiogram v3 Router

# Game state
game_running = False
players = {}
roles = {}
num_players_required = 0
player_list_message_id = None  # Store message ID for player list

# Function to escape MarkdownV2 special characters
def escape_markdown_v2(text):
    return re.sub(r'([\\_*`[\]()#+\-.!])', r'\\\1', text)

# Start command
@router.message(Command("start"))
async def start(message: Message):
    await message.answer("Welcome to Mafia Bot! Use /startgame to begin.")

# Start game command
@router.message(Command("startgame"))
async def start_game(message: Message):
    global game_running, num_players_required, players, player_list_message_id
    if game_running:
        await message.answer("A game is already running! Use /stopgame to reset.")
        return
    
    game_running = True
    players.clear()
    num_players_required = 0
    await message.answer("Enter the number of players (5-10):")

@router.message(lambda message: message.text.isdigit() and 5 <= int(message.text) <= 10)
async def set_num_players(message: Message):
    global num_players_required, player_list_message_id
    num_players_required = int(message.text)
    join_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Game", callback_data="join_game")],
        [InlineKeyboardButton(text="Fill with Fake Players", callback_data="fill_fake")]
    ])
    sent_message = await message.answer(f"Game set for {num_players_required} players! Click the button to join:", reply_markup=join_button)
    player_list_message_id = sent_message.message_id  # Store message ID
    await update_player_list(message.chat.id)

async def update_player_list(chat_id):
    if player_list_message_id:
        player_list = "\n".join([f"{data['name']} ({data['status']})" for data in players.values()])
        text = f"Current Players:\n{player_list}"
        join_button = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Join Game", callback_data="join_game")],
            [InlineKeyboardButton(text="Fill with Fake Players", callback_data="fill_fake")]
        ])
        await bot.edit_message_text(chat_id=chat_id, message_id=player_list_message_id, text=text, reply_markup=join_button)

@router.callback_query(lambda c: c.data == "join_game")
async def join_game(callback_query: types.CallbackQuery):
    global players
    user_id = callback_query.from_user.id
    if user_id not in players and len(players) < num_players_required:
        players[user_id] = {"name": callback_query.from_user.first_name, "status": "Alive"}
        await update_player_list(callback_query.message.chat.id)
    await callback_query.answer()

@router.callback_query(lambda c: c.data == "fill_fake")
async def fill_fake(callback_query: types.CallbackQuery):
    global players
    filler_names = ["Alice", "Bob", "Charlie", "David", "Eve", "Frank", "Grace", "Hank", "Ivy", "Jack"]
    for name in filler_names:
        if len(players) < num_players_required:
            players[name] = {"name": name, "status": "Alive"}
    await update_player_list(callback_query.message.chat.id)
    await callback_query.answer()

@router.message(Command("startplaying"))
async def assign_roles(message: Message):
    global roles
    num_players = len(players)
    if num_players != num_players_required:
        await message.answer(f"Waiting for {num_players_required - num_players} more players.")
        return
    
    num_mafia = max(1, num_players // 4)  # Adjusted mafia count logic
    available_roles = ["Don"] + ["Mafia"] * (num_mafia - 1) + ["Commissioner"]
    
    if num_players > 7:
        available_roles.append("Doctor")
        available_roles.append("Lawyer")
    
    available_roles += ["Citizen"] * (num_players - len(available_roles))
    random.shuffle(available_roles)
    
    for i, player in enumerate(players.keys()):
        roles[player] = {"role": available_roles[i], "status": "Alive"}
    
    role_list = "\n".join([f"{players[p]['name']}: {roles[p]['role']}" for p in players])
    await message.answer(f"Roles assigned!\n\n{role_list}")

# Mafia kill test command
@router.message(Command("mafiakill"))
async def mafia_kill_test(message: Message):
    if not game_running:
        await message.answer("No game is running.")
        return
    
    living_players = [p for p in roles if roles[p]['status'] == "Alive" and roles[p]['role'] not in ["Mafia", "Don"]]
    if not living_players:
        await message.answer("No valid targets for the mafia.")
        return
    
    victim = random.choice(living_players)
    roles[victim]['status'] = "Dead"
    await update_player_list(message.chat.id)
    await message.answer(f"The mafia has killed {players[victim]['name']}! They are now deceased.")

# Test command
@router.message(Command("testmenu"))
async def test_menu(message: Message):
    test_buttons = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Day Phase", callback_data="day_phase")],
        [InlineKeyboardButton(text="Night Phase", callback_data="night_phase")],
        [InlineKeyboardButton(text="Change Role", callback_data="change_role")],
        [InlineKeyboardButton(text="Mafia Kill", callback_data="mafiakill")]
    ])
    await message.answer("Test Menu:", reply_markup=test_buttons)

# Stop game command
@router.message(Command("stopgame"))
async def stop_game(message: Message):
    global game_running, players, roles
    if not game_running:
        await message.answer("No game is currently running.")
        return
    
    game_running = False
    players.clear()
    roles.clear()
    await message.answer("Game has been stopped. Use /startgame to start a new one.")

# Day/Night commands
@router.message(Command("day"))
async def day_phase(message: Message):
    await message.answer("Day phase started!")

@router.message(Command("night"))
async def night_phase(message: Message):
    await message.answer("Night phase started!")

# Help command
@router.message(Command("help"))
async def help_command(message: Message):
    help_text = (
        "/start - Start the bot\n"
        "/startgame - Start a new game\n"
        "/stopgame - Stop the current game\n"
        "/day - Start the day phase\n"
        "/night - Start the night phase\n"
        "/startplaying - Assign roles to players\n"
        "/mafiakill - Test mafia kill\n"
        "/help - Show this help message"
    )
    escaped_help_text = escape_markdown_v2(help_text)
    await message.answer(escaped_help_text, parse_mode="MarkdownV2")

async def main():
    dp.include_router(router)  # Register the router
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
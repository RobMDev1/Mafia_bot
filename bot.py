import asyncio
import random
import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder
from roles import handle_night_action, game_state, players, player_order, roles
from phases import (
    start_day_cycle, set_phase_timer, register_vote,
    register_mafia_vote, force_day, force_night, force_vote,
    mafia_ids, vote_data, vote_confirm_data, joined_player_ids,
    phase_timers
)
from strings import strings_hy as TXT

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv("token.env")
TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
BOT_USERNAME = "secretcartel_bot"
dp = Dispatcher()
router = Router()
group_id = None
join_message_id = None

async def is_admin(message: Message) -> bool:
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ("administrator", "creator")

@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer(TXT["help"])

@router.message(Command("startgame"))
async def start_game(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return

    players.clear()
    player_order.clear()
    roles.clear()
    game_state["alive"].clear()

    global group_id, join_message_id
    group_id = message.chat.id

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Միանալ խաղին", callback_data="join_game")
    builder.button(text="🤖 Գրել բոթին", url=f"https://t.me/{BOT_USERNAME}?start=join")
    keyboard = builder.as_markup()

    msg = await message.answer(TXT["join_game_prompt"], reply_markup=keyboard)
    join_message_id = msg.message_id

@router.callback_query(lambda c: c.data == "join_game")
async def join_game_callback(callback: CallbackQuery):
    user = callback.from_user

    try:
        await bot.send_message(user.id, TXT["dm_join_confirmation"])
    except Exception as e:
        logging.error(f"Failed to DM user {user.id}: {e}")
        await callback.answer("Խնդրում ենք նախ գրել բոթին։", show_alert=True)
        return

    if user.id not in players:
        players[user.id] = user.full_name
        player_order.append(user.id)
        await callback.answer(TXT["joined_success"])
    else:
        await callback.answer(TXT["already_joined"], show_alert=True)

    if user.id not in joined_player_ids:
        joined_player_ids.append(user.id)

    if group_id and join_message_id:
        try:
            text = TXT["players_joined"] + "\n" + "\n".join(
                f"{i+1}. {players[pid]}" for i, pid in enumerate(player_order)
            )
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text=TXT["join_game_button"], callback_data="join_game")
            keyboard.button(text="🤖 Գրել բոթին", url=f"https://t.me/{BOT_USERNAME}?start=join_game")
            await bot.edit_message_text(
                chat_id=group_id,
                message_id=join_message_id,
                text=text,
                reply_markup=keyboard.as_markup()
            )
        except Exception as e:
            logging.error(f"Failed to update join message: {e}")

@router.message(Command("startplaying"))
async def start_playing(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return

    if len(player_order) < 5:
        await message.reply("❗ Խաղը սկսելու համար անհրաժեշտ է առնվազն 5 խաղացող։")
        return

    global group_id
    group_id = message.chat.id
    game_state["alive"] = set(player_order)

    num_players = len(player_order)
    roles_list = []

    mafia_count = max(1, num_players // 3)

    if num_players >= 8:
        roles_list.append("Don")
        mafia_count -= 1
    if num_players >= 9:
        roles_list.append("Lawyer")
        mafia_count -= 1

    roles_list += ["Mafia"] * mafia_count
    roles_list.append("Commissioner")
    if num_players >= 6:
        roles_list.append("Doctor")

    remaining = num_players - len(roles_list)
    roles_list += ["Citizen"] * remaining
    random.shuffle(roles_list)

    for pid, role in zip(player_order, roles_list):
        roles[pid] = role

    armenian_roles = {
        "Mafia": "Մաֆիա",
        "Don": "Դոն",
        "Lawyer": "Փաստաբան",
        "Commissioner": "Քննչական",
        "Doctor": "Բժիշկ",
        "Citizen": "Քաղաքացի"
    }

    for pid in player_order:
        role = roles[pid]
        try:
            role_arm = armenian_roles.get(role, role)
            msg = f"{TXT['your_role']} {role_arm}"
            if role in ["Mafia", "Don", "Lawyer"]:
                teammates = [
                    (players[uid], armenian_roles[roles[uid]])
                    for uid in player_order
                    if uid != pid and roles[uid] in ["Mafia", "Don", "Lawyer"]
                ]
                if teammates:
                    msg += f"\n{TXT['mafia_teammates']}\n" + "\n".join(f"• {n} ({r})" for n, r in teammates)
            await bot.send_message(pid, msg)
        except Exception as e:
            logging.error(f"❌ Could not DM {players[pid]}: {e}")

    await message.answer(TXT["roles_assigned"])
    await force_night(bot, group_id)

@router.message(Command("fillplayers"))
async def fill_players(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return
    filler_names = ["Ալիսա", "Բոբ", "Չառլի", "Դեյվիդ", "Եվա", "Ֆրենկ", "Գրեյս", "Հենրի", "Իվը", "Ջեք"]
    players.clear()
    player_order.clear()
    roles.clear()
    for i, name in enumerate(filler_names):
        fake_id = 10000 + i
        players[fake_id] = name
        player_order.append(fake_id)
    await message.answer("✅ Լրացվել է կեղծ մասնակիցներով։")

@router.message(Command("settimer"))
async def set_timer(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer(TXT["invalid_timer"])
        return
    phase, time_str = parts[1], parts[2]
    if not time_str.isdigit():
        await message.answer(TXT["invalid_timer"])
        return
    success = set_phase_timer(phase, int(time_str))
    if success:
        await message.answer(TXT["set_timer_success"].format(phase=phase, seconds=time_str))
    else:
        await message.answer(TXT["unknown_phase"])

@router.message(Command("showtimer"))
async def show_timer(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return
    msg = (
        f"⏱️ Այս պահին սահմանված են փուլերի ժամանակները՝\n"
        f"- 🌞 Օր՝ {phase_timers['day']} վայրկյան\n"
        f"- 🌙 Գիշեր՝ {phase_timers['night']} վայրկյան\n"
        f"- 🗳️ Քվեարկություն՝ {phase_timers['vote']} վայրկյան"
    )
    await message.answer(msg)

@router.message(Command("forceday"))
async def admin_force_day(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return
    await force_day(bot, message.chat.id)

@router.message(Command("forcenight"))
async def admin_force_night(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return
    await force_night(bot, message.chat.id)

@router.message(Command("forcevote"))
async def admin_force_vote(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return
    await force_vote(bot, message.chat.id)

@router.message(Command("stopgame"))
async def stop_game(message: Message):
    if not await is_admin(message):
        await message.reply(TXT["only_admin"])
        return

    players.clear()
    player_order.clear()
    roles.clear()
    game_state["alive"].clear()
    game_state["awaiting_last_words"].clear()
    game_state["last_words"].clear()
    game_state["night_actions"] = {
        "mafia_votes": {},
        "doctor": None,
        "lawyer": None,
        "don_check": None,
        "commissioner_check": None
    }

    global mafia_ids, vote_data, vote_confirm_data
    mafia_ids = []
    vote_data.clear()
    vote_confirm_data = {
        "candidate": None,
        "yes": set(),
        "no": set()
    }

    await message.answer("🛑 Խաղը դադարեցվել է։")

@router.callback_query(lambda c: c.data.startswith("vote_"))
async def vote_callback(callback_query: CallbackQuery):
    voter = callback_query.from_user.id
    target = int(callback_query.data.split("_")[1])
    before = len(vote_data)
    register_vote(voter, target)
    after = len(vote_data)

    if after > before:
        voter_name = players.get(voter, "Unknown")
        target_name = players.get(target, "Unknown")
        await bot.send_message(callback_query.message.chat.id, f"🗳 {voter_name} քվեարկեց {target_name}-ի օգտին։")
        logging.info(f"{voter_name} voted for {target_name}")
        await callback_query.answer(TXT["vote_registered"])
    else:
        await callback_query.answer("❌ Դուք չեք կարող քվեարկել։", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("mafkill_"))
async def mafia_vote_callback(callback_query: CallbackQuery):
    voter = callback_query.from_user.id
    target = int(callback_query.data.split("_")[1])
    before = len(game_state["night_actions"]["mafia_votes"])
    register_mafia_vote(voter, target)
    after = len(game_state["night_actions"]["mafia_votes"])

    if after > before:
        voter_name = players.get(voter, "Unknown")
        target_name = players.get(target, "Unknown")
        logging.info(f"{voter_name} (Mafia) voted to kill {target_name}")
        for pid in mafia_ids:
            if pid != voter and roles.get(pid) in ("Mafia", "Don", "Lawyer") and pid in game_state["alive"]:
                try:
                    await bot.send_message(pid, f"🔫 {voter_name} քվեարկեց {target_name}-ի սպանությանը։")
                except Exception as e:
                    logging.error(f"Failed to relay mafia vote to {pid}: {e}")
        await callback_query.answer(TXT["mafia_vote_registered"])
    else:
        await callback_query.answer("❌ Դուք չեք կարող քվեարկել։", show_alert=True)

@router.message()
async def relay_mafia_message(message: Message):
    if (
        message.chat.type == "private"
        and message.from_user.id in mafia_ids
        and message.from_user.id in game_state["alive"]
    ):
        sender_name = players.get(message.from_user.id, "Unknown")
        logging.info(f"[Mafia Chat] {sender_name}: {message.text}")
        for pid in mafia_ids:
            if pid != message.from_user.id and roles.get(pid) in ("Mafia", "Don", "Lawyer") and pid in game_state["alive"]:
                try:
                    await bot.send_message(pid, f"🕵️ {sender_name}: {message.text}")
                except Exception as e:
                    logging.error(f"Failed to relay mafia chat to {pid}: {e}")

@router.callback_query(lambda c: c.data.startswith(("doncheck_", "commcheck_", "lawyerhide_", "docprotect_")))
async def night_action_router(callback_query: CallbackQuery):
    await handle_night_action(callback_query, bot)

@router.message()
async def handle_last_words(message: Message):
    uid = message.from_user.id
    if uid in game_state["awaiting_last_words"]:
        game_state["last_words"][uid] = message.text
        game_state["awaiting_last_words"].discard(uid)
        logging.info(f"Saved last words from {players.get(uid, uid)}: {message.text}")
        try:
            await message.answer(TXT["last_words_saved"])
        except Exception as e:
            logging.error(f"Failed to send last word confirmation to {uid}: {e}")

async def main():
    dp.include_router(router)
    commands = [
        BotCommand(command="startgame", description="Start a new game (admin only)"),
        BotCommand(command="startplaying", description="Assign roles & begin (admin only)"),
        BotCommand(command="stopgame", description="Stop the game (admin only)"),
        BotCommand(command="fillplayers", description="Fill with fake players (admin only)"),
        BotCommand(command="settimer", description="Set timer for a phase"),
        BotCommand(command="forceday", description="Force day phase"),
        BotCommand(command="forcenight", description="Force night phase"),
        BotCommand(command="forcevote", description="Force vote phase"),
        BotCommand(command="showtimer", description="Show timers"),
        BotCommand(command="help", description="Show help message"),
    ]
    await bot.set_my_commands(commands)
    logging.info("Bot is running and polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

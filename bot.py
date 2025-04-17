import asyncio
import random
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder
from roles import handle_night_action, game_state, players, player_order, roles
from phases import (
    start_day_cycle, set_phase_timer, register_vote,
    register_mafia_vote, force_day, force_night, force_vote,
    mafia_ids, vote_data, vote_confirm_data
)
from strings import strings_hy as TXT
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
        print(f"❌ Failed to DM user {user.id}: {e}")
        await callback.answer("Խնդրում ենք նախ գրել բոթին։", show_alert=True)
        return

    if user.id not in players:
        players[user.id] = user.full_name
        player_order.append(user.id)
        await callback.answer(TXT["joined_success"])
    else:
        await callback.answer(TXT["already_joined"], show_alert=True)

    # Update group message
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
            print(f"❌ Failed to update join message: {e}")


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
    num_mafia = max(1, num_players // 4)
    role_pool = ["Don"] + ["Mafia"] * (num_mafia - 1) + ["Commissioner"]

    if num_players > 7:
        role_pool.append("Doctor")
        role_pool.append("Lawyer")

    role_pool += ["Citizen"] * (num_players - len(role_pool))
    random.shuffle(role_pool)

    print("Assigning roles to players:", [(players[pid], role) for pid, role in zip(player_order, role_pool)])

    armenian_roles = {
        "Mafia": "Մաֆիա",
        "Don": "Դոն",
        "Lawyer": "Փաստաբան",
        "Commissioner": "Քննչական",
        "Doctor": "Բժիշկ",
        "Citizen": "Քաղաքացի"
    }

    for pid, role in zip(player_order, role_pool):
        roles[pid] = role

    for pid in player_order:
        role = roles[pid]
        try:
            role_arm = armenian_roles.get(role, role)
            message_text = f"{TXT['your_role']} {role_arm}"
            if role in ["Mafia", "Don", "Lawyer"]:
                teammates = [
                    (players[uid], armenian_roles[roles[uid]])
                    for uid in player_order
                    if uid != pid and roles[uid] in ["Mafia", "Don", "Lawyer"]
                ]
                if teammates:
                    teammate_info = "\n".join(f"• {name} ({r})" for name, r in teammates)
                    message_text += f"\n{TXT['mafia_teammates']}\n{teammate_info}"
            await bot.send_message(pid, message_text)
            print(f"✅ Sent role to {players[pid]} ({pid})")
        except Exception as e:
            print(f"❌ Could not send role to {players[pid]} ({pid}): {e}")

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

    global mafia_ids, current_phase, vote_data, vote_confirm_data
    mafia_ids = []
    current_phase = None
    vote_data.clear()
    vote_confirm_data = {
        "candidate": None,
        "yes": set(),
        "no": set()
    }

    await message.answer("🛑 Խաղը դադարեցվել է։")


@router.message()
async def relay_mafia_message(message: Message):
    if (
        message.chat.type == "private"
        and message.from_user.id in mafia_ids
        and message.from_user.id in game_state["alive"]  # ✅ Alive check
    ):
        sender_name = players.get(message.from_user.id, "Unknown")
        for pid in players:
            if roles.get(pid) in ("Mafia", "Don", "Lawyer") and pid != message.from_user.id:
                try:
                    await bot.send_message(pid, f"🕵️ {sender_name}: {message.text}")
                except Exception as e:
                    print(f"❌ Failed to relay mafia chat to {pid}: {e}")


@router.callback_query(lambda c: c.data.startswith(("doncheck_", "commcheck_", "lawyerhide_", "docprotect_")))
async def night_action_router(callback_query: CallbackQuery):
    await handle_night_action(callback_query, bot)

@router.callback_query(lambda c: c.data.startswith("vote_"))
async def vote_callback(callback_query: CallbackQuery):
    voter = callback_query.from_user.id
    target = int(callback_query.data.split("_")[1])
    register_vote(voter, target)
    await callback_query.answer(TXT["vote_registered"])

@router.callback_query(lambda c: c.data.startswith("mafkill_"))
async def mafia_vote_callback(callback_query: CallbackQuery):
    voter = callback_query.from_user.id
    target = int(callback_query.data.split("_")[1])
    register_mafia_vote(voter, target)
    await callback_query.answer(TXT["mafia_vote_registered"])

@router.message()
async def handle_last_words(message: Message):
    uid = message.from_user.id
    if uid in game_state["awaiting_last_words"]:
        game_state["last_words"][uid] = message.text
        game_state["awaiting_last_words"].discard(uid)
        await message.answer(TXT["last_words_saved"])

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
        BotCommand(command="help", description="Show help message")
    ]
    await bot.set_my_commands(commands)

    print("🤖 Bot is running and polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
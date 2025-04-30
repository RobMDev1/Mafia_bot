import json
import os
import asyncio
import logging
from roles import (
    game_state, players, roles,
    resolve_special_roles, submit_commissioner_check,
    submit_doctor_protect, submit_lawyer_hide
)
from messages import announce_day, announce_night
from strings import strings_hy as TXT
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

CONFIG_FILE = "timer_config.json"
DEFAULT_TIMERS = {"day": 60, "night": 60, "vote": 60}

joined_player_ids = []

def load_timers():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_TIMERS.copy()

def save_timers():
    with open(CONFIG_FILE, "w") as f:
        json.dump(phase_timers, f)

phase_timers = load_timers()

current_phase = None
vote_message_id = None
vote_data = {}
mafia_ids = []
vote_confirm_data = {
    "candidate": None,
    "yes": set(),
    "no": set()
}

async def restrict_group_chat(bot, chat_id, allow_ids):
    for uid in players:
        try:
            perms = {
                "can_send_messages": uid in allow_ids,
                "can_send_media_messages": uid in allow_ids,
                "can_send_other_messages": uid in allow_ids,
                "can_add_web_page_previews": uid in allow_ids
            }
            await bot.restrict_chat_member(chat_id, uid, permissions=perms)
        except Exception:
            continue

async def lift_all_restrictions(bot, chat_id):
    for uid in players:
        try:
            await bot.restrict_chat_member(
                chat_id, uid,
                permissions={
                    "can_send_messages": True,
                    "can_send_media_messages": True,
                    "can_send_other_messages": True,
                    "can_add_web_page_previews": True
                }
            )
        except Exception:
            continue

async def start_day_cycle(bot, chat_id):
    global current_phase
    current_phase = "day"

    if game_state["last_words"]:
        farewell = "\n".join([
            f"💀 {players[uid]} ասաց․ \"{msg}\"" for uid, msg in game_state["last_words"].items()
        ])
        await bot.send_message(chat_id, TXT["final_words_intro"] + "\n" + farewell)
        logging.info("Displayed last words to group")
        game_state["last_words"].clear()

    alive_players = [pid for pid in game_state["alive"]]
    player_list = "\n".join([f"{players[pid]}" for pid in alive_players])
    role_list = ", ".join(sorted(set([roles[pid] for pid in alive_players])))
    await bot.send_message(chat_id, TXT["alive_players"].format(players=player_list, roles=role_list))

    if await check_win_conditions(bot, chat_id):
        return

    await restrict_group_chat(bot, chat_id, allow_ids=game_state["alive"])
    await announce_day(bot, chat_id)
    await asyncio.sleep(phase_timers["day"])
    await start_vote_cycle(bot, chat_id)

async def start_vote_cycle(bot, chat_id):
    global current_phase, vote_data, vote_message_id
    current_phase = "vote"
    vote_data = {}

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{i+1}. {players[pid]}", callback_data=f"vote_{pid}")]
        for i, pid in enumerate(game_state["alive"])
    ])
    msg = await bot.send_message(chat_id, TXT["vote_phase"], reply_markup=keyboard)
    vote_message_id = msg.message_id
    await asyncio.sleep(phase_timers["vote"])
    await conclude_vote(bot, chat_id)

async def conclude_vote(bot, chat_id):
    if not vote_data:
        await bot.send_message(chat_id, TXT["no_votes"])
        return

    tally = {}
    for voter, target in vote_data.items():
        if voter in game_state["alive"] and target in game_state["alive"]:
            tally[target] = tally.get(target, 0) + 1

    if not tally:
        await bot.send_message(chat_id, TXT["invalid_votes"])
        return

    vote_results = "\n".join([
        f"🗳 {players[voter]} → {players[target]}"
        for voter, target in vote_data.items()
        if voter in game_state["alive"] and target in game_state["alive"]
    ])
    await bot.send_message(chat_id, TXT["vote_results"] + "\n" + vote_results)

    max_votes = max(tally.values())
    top_targets = [pid for pid, count in tally.items() if count == max_votes]

    if len(top_targets) > 1:
        await bot.send_message(chat_id, TXT["tied_vote"])
        return

    candidate = top_targets[0]
    vote_confirm_data["candidate"] = candidate
    vote_confirm_data["yes"].clear()
    vote_confirm_data["no"].clear()

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍", callback_data="confirm_yes"),
            InlineKeyboardButton(text="👎", callback_data="confirm_no")
        ]
    ])
    await bot.send_message(chat_id, f"✅ {players[candidate]} առաջադրվել է դուրս մնալու։ Համաձա՞յն եք։", reply_markup=confirm_kb)
    await asyncio.sleep(15)

    yes_votes = len([uid for uid in vote_confirm_data["yes"] if uid in joined_player_ids])
    no_votes = len([uid for uid in vote_confirm_data["no"] if uid in joined_player_ids])

    if yes_votes > no_votes:
        game_state["alive"].discard(candidate)
        await bot.send_message(chat_id, TXT["player_eliminated"].format(player=players[candidate], role=roles[candidate]))
    else:
        await bot.send_message(chat_id, f"❌ {players[candidate]} խաղից դուրս չմնաց։")

    await start_night_cycle(bot, chat_id)

async def start_night_cycle(bot, chat_id):
    global current_phase, mafia_ids
    current_phase = "night"

    if await check_win_conditions(bot, chat_id):
        return

    await restrict_group_chat(bot, chat_id, allow_ids=[])
    await announce_night(bot, chat_id)

    mafia_ids.clear()
    mafia_ids.extend([pid for pid in game_state["alive"] if roles.get(pid) in ("Mafia", "Don", "Lawyer")])

    targets = [pid for pid in game_state["alive"] if roles.get(pid) not in ("Mafia", "Don", "Lawyer")]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=players[pid], callback_data=f"mafkill_{pid}")]
        for pid in targets
    ])

    for maf in mafia_ids:
        try:
            await bot.send_message(maf, "Ո՞ւմ եք ուզում սպանել այս գիշեր:", reply_markup=keyboard)
            await bot.send_message(maf, "💬 Գիշերային մաֆիայի զրույց։ Գրեք ինձ, և ես կփոխանցեմ մյուսներին։")
        except Exception as e:
            print(f"❌ Could not DM mafia {maf}: {e}")

    await send_night_role_buttons(bot)
    await asyncio.sleep(phase_timers["night"])
    await resolve_night(bot, chat_id)
    await start_day_cycle(bot, chat_id)

async def send_night_role_buttons(bot):
    for pid in game_state["alive"]:
        if roles[pid] == "Doctor":
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=players[tid], callback_data=f"docprotect_{tid}")]
                for tid in game_state["alive"]
            ])
            await bot.send_message(pid, "👨‍⚕️ Ո՞ւմ եք ցանկանում պաշտպանել։", reply_markup=kb)

        elif roles[pid] == "Commissioner":
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=players[tid], callback_data=f"commcheck_{tid}")]
                for tid in game_state["alive"] if tid != pid
            ])
            await bot.send_message(pid, "🔍 Ու՞մ եք ուզում հետաքննել։", reply_markup=kb)

        elif roles[pid] == "Lawyer":
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=players[tid], callback_data=f"lawyerhide_{tid}")]
                for tid in game_state["alive"] if tid != pid
            ])
            await bot.send_message(pid, "💼 Ո՞ւմ եք ուզում պաշտպանել։", reply_markup=kb)

async def resolve_night(bot, chat_id):
    await resolve_special_roles(bot)
    mafia_votes = game_state["night_actions"].get("mafia_votes", {})
    protected = game_state["night_actions"].get("doctor")

    if not mafia_votes:
        await bot.send_message(chat_id, TXT["night_passed"])
        return

    mafia_votes = {voter: target for voter, target in mafia_votes.items() if voter in joined_player_ids}

    tally = {}
    for voter, target in mafia_votes.items():
        tally[target] = tally.get(target, 0) + 1

    max_votes = max(tally.values())
    top_targets = [pid for pid, count in tally.items() if count == max_votes]
    don_id = next((pid for pid in mafia_ids if roles.get(pid) == "Don"), None)
    don_vote = mafia_votes.get(don_id) if don_id else None

    if len(top_targets) == 1 and top_targets[0] == don_vote:
        target = top_targets[0]
        if target == protected:
            await bot.send_message(chat_id, TXT["someone_survived"])
            doctor_id = next((pid for pid in game_state["alive"] if roles.get(pid) == "Doctor"), None)
            if doctor_id:
                await bot.send_message(doctor_id, TXT["saved_life"].format(target=players[target]))
        else:
            game_state["alive"].discard(target)
            game_state["awaiting_last_words"].add(target)
            logging.info(f"{players[target]} marked for last words")
            await bot.send_message(target, TXT["you_were_eliminated"])
            await bot.send_message(chat_id, TXT["announced_death"].format(name=players[target], role=roles[target]))
    else:
        await bot.send_message(chat_id, TXT["no_mafia_kill"])

    game_state["night_actions"] = {
        "mafia_votes": {},
        "doctor": None,
        "lawyer": None,
        "commissioner_check": None
    }
    await bot.send_message(chat_id, TXT["new_day"])
    await check_win_conditions(bot, chat_id)


async def force_day(bot, chat_id):
    await start_day_cycle(bot, chat_id)

async def force_vote(bot, chat_id):
    await start_vote_cycle(bot, chat_id)

async def force_night(bot, chat_id):
    await start_night_cycle(bot, chat_id)

def set_phase_timer(phase: str, seconds: int):
    if phase in phase_timers:
        phase_timers[phase] = seconds
        save_timers()
        return True
    return False

def register_vote(voter_id: int, target_id: int):
    if current_phase != "vote":
        return
    if voter_id not in joined_player_ids or voter_id not in game_state["alive"] or target_id not in game_state["alive"]:
        return
    vote_data[voter_id] = target_id


def register_mafia_vote(voter_id: int, target_id: int):
    if current_phase != "night":
        return
    if voter_id not in joined_player_ids or voter_id not in game_state["alive"] or target_id not in game_state["alive"]:
        return
    game_state["night_actions"]["mafia_votes"][voter_id] = target_id


async def check_win_conditions(bot, chat_id):
    mafia_roles = {"Mafia", "Don", "Lawyer"}
    mafia_count = sum(1 for pid in game_state["alive"] if roles.get(pid) in mafia_roles)
    others_count = sum(1 for pid in game_state["alive"] if roles.get(pid) not in mafia_roles)

    if mafia_count == 0:
        await bot.send_message(chat_id, TXT["game_over_citizens"])
        await lift_all_restrictions(bot, chat_id)
        joined_player_ids.clear()
        return True
    elif mafia_count >= others_count:
        await bot.send_message(chat_id, TXT["game_over_mafia"])
        await lift_all_restrictions(bot, chat_id)
        joined_player_ids.clear()
        return True
    return False

import logging
from aiogram import Bot
from aiogram.types import CallbackQuery
import re

# Players and roles
players = {}
player_order = []
roles = {}

# Escape function
def escape_md(text: str) -> str:
    return re.sub(r'([_\*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)

# Game state
game_state = {
    "alive": set(),
    "doctor_self_used": None,
    "night_actions": {
        "mafia_votes": {},
        "doctor": None,
        "lawyer": None,
        "commissioner_check": None
    },
    "last_words": {},
    "awaiting_last_words": set()
}

# Submit abilities
def submit_commissioner_check(comm_id, target_id):
    game_state["night_actions"]["commissioner_check"] = (comm_id, target_id)

def submit_lawyer_hide(lawyer_id, target_id):
    game_state["night_actions"]["lawyer"] = target_id

def submit_doctor_protect(doc_id, target_id):
    if doc_id == target_id:
        if game_state["doctor_self_used"]:
            return False
        game_state["doctor_self_used"] = True
    game_state["night_actions"]["doctor"] = target_id
    return True

# Resolve abilities at the end of night
async def resolve_special_roles(bot: Bot):
    actions = game_state["night_actions"]
    protected = actions["doctor"]
    hidden = actions["lawyer"]

    # Commissioner check (delayed until now)
    if actions["commissioner_check"]:
        comm_id, target_id = actions["commissioner_check"]
        role = roles.get(target_id)

        if target_id == hidden:
            logging.info(f"Lawyer is hiding {players[target_id]}")
            role = "Citizen"

        try:
            await bot.send_message(comm_id, f"{players[target_id]}'s role is: {role}")
            logging.info(f"Commissioner {players[comm_id]} checked {players[target_id]}: saw {role}")
        except Exception as e:
            logging.error(f"Failed to send Commissioner result to {players[comm_id]}: {e}")

        # Notify the target
        try:
            await bot.send_message(target_id, "🕵️ Քննիչը ստուգել է ձեզ այս գիշեր։")
            logging.info(f"Notified {players[target_id]} that they were checked by the Commissioner.")
        except Exception as e:
            logging.error(f"Failed to notify {players[target_id]} of being checked: {e}")

    # Reset actions
    game_state["night_actions"] = {
        "mafia_votes": {},
        "doctor": None,
        "lawyer": None,
        "commissioner_check": None
    }

# Night button handling
async def handle_night_action(callback: CallbackQuery, bot: Bot, chat_id: int):
    data = callback.data
    user_id = callback.from_user.id
    from phases import current_phase
    
    if current_phase != "night":
        await callback.answer("⛔ Գործողությունները միայն գիշերը կարելի է անել։", show_alert=True)
        return

    if data.startswith("commcheck_"):
        target_id = int(data.split("_")[1])
        submit_commissioner_check(user_id, target_id)
        await callback.message.edit_text(f"✅ Դուք ստուգեցիք {players[target_id]} -ին։")
        await bot.send_message(chat_id, "🕵️ Քննիչը սկսեց հետաքննություն։")

    elif data.startswith("docprotect_"):
        target_id = int(data.split("_")[1])
        success = submit_doctor_protect(user_id, target_id)
        if success:
            await callback.message.edit_text(f"✅ Դուք որոշեցիք պաշտպանել {players[target_id]} -ին։")
            await bot.send_message(chat_id, "🩺 Ինչ-որ մեկը փորձեց պաշտպանել խաղացողի։")
        else:
            await callback.message.edit_text("❌ Դուք ձեզ արդեն պաշտպանել էք։")

    elif data.startswith("lawyerhide_"):
        target_id = int(data.split("_")[1])
        submit_lawyer_hide(user_id, target_id)
        await callback.message.edit_text(f"✅ Դուք թաքցրեցիք {players[target_id]} -ի դերը։")
        await bot.send_message(chat_id, "💼 Փաստաբանը գործի անցավ։")

    await callback.answer()

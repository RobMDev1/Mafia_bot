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

# Game state related to roles
game_state = {
    "alive": set(),
    "doctor_self_used": None,
    "night_actions": {
        "mafia_votes": {},
        "doctor": None,
        "lawyer": None,
        "don_check": None,
        "commissioner_check": None
    },
    "last_words": {},  # {user_id: message}
    "awaiting_last_words": set()  # players eligible to submit final words
}

# Submit role abilities

def submit_don_check(don_id, target_id):
    game_state["night_actions"]["don_check"] = (don_id, target_id)

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

# Resolve role abilities

async def resolve_special_roles(bot):
    actions = game_state["night_actions"]
    protected = actions["doctor"]
    hidden = actions["lawyer"]

    # Don checks for Commissioner
    if actions["don_check"]:
        don_id, target_id = actions["don_check"]
        is_commissioner = roles.get(target_id) == "Commissioner"
        text = f"{players[target_id]} is{' ' if is_commissioner else ' NOT '}the Commissioner."
        await bot.send_message(don_id, text)

    # Commissioner checks role (with Lawyer interference)
    if actions["commissioner_check"]:
        comm_id, target_id = actions["commissioner_check"]
        role = roles.get(target_id)
        if target_id == hidden:
            role = "Citizen"
        await bot.send_message(comm_id, f"{players[target_id]}'s role is: {role}")

    # Reset actions
    game_state["night_actions"] = {
        "mafia_votes": {},
        "doctor": None,
        "lawyer": None,
        "don_check": None,
        "commissioner_check": None
    }

# Handle role-specific button callbacks

async def handle_night_action(callback: CallbackQuery, bot: Bot):
    data = callback.data
    user_id = callback.from_user.id


    if data.startswith("commcheck_"):
        target_id = int(data.split("_")[1])
        submit_commissioner_check(user_id, target_id)
        await callback.message.edit_text(f"✅ Դուք ստուգեցիք {players[target_id]} -ին.")

    elif data.startswith("docprotect_"):
        target_id = int(data.split("_")[1])
        success = submit_doctor_protect(user_id, target_id)
        if success:
            await callback.message.edit_text(f"✅ Դուք որոշեցիք պաշտպանել {players[target_id]} -ին.")
        else:
            await callback.message.edit_text("❌ Դուք ձեզ արդեն պաշտպանել էք.")

    elif data.startswith("lawyerhide_"):
        target_id = int(data.split("_")[1])
        submit_lawyer_hide(user_id, target_id)
        await callback.message.edit_text(f"✅ Դուք թաքցրեցիք {players[target_id]} -ի դերը.")

    await callback.answer()


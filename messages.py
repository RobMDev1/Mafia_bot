import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from roles import players, player_order, roles
from strings import strings_hy as TXT

player_list_message_id = None

def escape_md(text: str) -> str:
    # Escape all MarkdownV2 special characters
    return re.sub(r'([_\*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)

async def start_game_message(message):
    global player_list_message_id
    join_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Game", callback_data="join_game")]
    ])
    sent = await message.answer("Game started! Players, click to join:", reply_markup=join_button)
    player_list_message_id = sent.message_id
    await update_player_list(message.bot, message.chat.id)

async def update_player_list(bot, chat_id):
    global player_list_message_id
    player_list = "\n".join([
        f"{i+1}. {escape_md(players[pid])}" for i, pid in enumerate(player_order)
    ])
    text = f"*Current Players:*\n{player_list}"
    join_button = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Join Game", callback_data="join_game")]
    ])
    await bot.edit_message_text(
        chat_id=chat_id,
        message_id=player_list_message_id,
        text=text,
        reply_markup=join_button
        # No parse_mode — plain text!
    )


async def send_roles(bot):
    for player_id in player_order:
        role = roles[player_id]
        await bot.send_message(player_id, f"Your role is: {role}")


async def announce_day(bot, chat_id):
    await bot.send_animation(chat_id, animation="https://media.giphy.com/media/89zcO0bvR9D5Bi2Qx7/giphy.gif?cid=790b7611ylkuz7vbreiu4ml5eh162fwqybsrf1ucrqef362x&ep=v1_gifs_search&rid=giphy.gif&ct=g")
    await bot.send_message(chat_id, "🌞 Օրվա փուլը սկսվել է։ Քննարկեք և կասկածեք։")


async def announce_night(bot, chat_id):
    await bot.send_animation(chat_id, animation="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExZmpmemdyeXkzZGZ0emxhMmZpNDZwZDZicDh3cjdmYmF6YWt4MDF2bCZlcD12MV9naWZzX3NlYXJjaCZjdD1n/nV5l2SFsU93ckaWlyn/giphy.gif")
    await bot.send_message(chat_id, "🌙 Գիշերային փուլը։ Հատուկ դերերը գործում են։")

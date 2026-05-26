from aiogram import Router, types
from aiogram.filters import CommandStart
from app.models import User
from app.bot.localization import MESSAGES
from app.bot.keyboards import get_main_menu
from app.config import settings

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, user: User, is_new_referred_user: bool):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    text = msgs["welcome"]
    if is_new_referred_user:
        text = f"{msgs['welcome_ref']}\n\n{text}"
        
    is_admin = user.id in settings.ADMIN_IDS
    kb = get_main_menu(lang, is_admin=is_admin)
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

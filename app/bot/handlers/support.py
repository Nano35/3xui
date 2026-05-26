from aiogram import Router, F, types
from app.models import User
from app.bot.localization import MESSAGES
from app.config import settings

router = Router()

@router.message(F.text.in_([MESSAGES["ru"]["menu_support"], MESSAGES["en"]["menu_support"]]))
async def cmd_support(message: types.Message, user: User):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    text = msgs["support_text"].format(support_handle=settings.SUPPORT_USERNAME)
    await message.answer(text, parse_mode="HTML")

@router.message(F.text.in_([MESSAGES["ru"].get("menu_about", "ℹ️ О сервисе"), MESSAGES["en"].get("menu_about", "ℹ️ About Service")]))
async def cmd_about(message: types.Message, user: User):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    text = msgs.get("about_service_text", "О сервисе")
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Пользовательское соглашение" if lang == "ru" else "📄 User Agreement", url=settings.AGREEMENT_URL)],
        [InlineKeyboardButton(text="🔒 Политика конфиденциальности" if lang == "ru" else "🔒 Privacy Policy", url=settings.PRIVACY_URL)]
    ])
    
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

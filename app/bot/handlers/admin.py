from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models import User, Subscription, Payment, PaymentStatus
from app.config import settings

router = Router()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

def is_admin_filter(message: types.Message) -> bool:
    return message.from_user.id in settings.ADMIN_IDS

@router.message(F.text.in_(["⚙️ Админ-панель", "⚙️ Admin Panel"]))
@router.message(Command("admin"))
async def admin_menu_handler(message: types.Message, db_session: AsyncSession):
    if not is_admin_filter(message):
        return
        
    # Gather statistics
    total_users_query = await db_session.execute(select(func.count(User.id)))
    total_users = total_users_query.scalar() or 0
    
    total_subs_query = await db_session.execute(select(func.count(Subscription.id)))
    total_subs = total_subs_query.scalar() or 0
    
    total_rev_query = await db_session.execute(
        select(func.sum(Payment.amount_kopeks)).where(Payment.status == PaymentStatus.COMPLETED)
    )
    total_rev_kopeks = total_rev_query.scalar() or 0
    total_rev = total_rev_kopeks / 100.0
    
    stats_text = (
        "⚙️ <b>Панель управления администратора</b>\n\n"
        f"👥 Всего пользователей в боте: <b>{total_users}</b>\n"
        f"🔑 Всего созданных подписок: <b>{total_subs}</b>\n"
        f"💳 Общий объем продаж: <b>{total_rev:.2f} руб.</b>\n\n"
        f"🌐 Веб-интерфейс: {settings.WEB_URL}/admin/\n"
    )
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📢 Рассылка сообщения", callback_data="admin_broadcast")],
        [types.InlineKeyboardButton(text="🖥️ Открыть Web-панель", url=f"{settings.WEB_URL}/admin/")]
    ])
    
    await message.answer(stats_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in settings.ADMIN_IDS:
        await callback.answer("У вас нет прав.", show_alert=True)
        return
        
    await callback.message.answer("✏️ Введите сообщение для рассылки всем пользователям бота (поддерживается HTML-разметка):")
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.answer()

@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: types.Message, state: FSMContext, db_session: AsyncSession):
    if not is_admin_filter(message):
        await state.clear()
        return
        
    broadcast_text = message.text
    await state.clear()
    
    # Get all users
    users_query = await db_session.execute(select(User.id))
    user_ids = users_query.scalars().all()
    
    await message.answer(f"⏳ Начинаю рассылку для {len(user_ids)} пользователей...")
    
    success_count = 0
    fail_count = 0
    
    for uid in user_ids:
        try:
            # Send message using bot instance
            await message.bot.send_message(chat_id=uid, text=broadcast_text, parse_mode="HTML")
            success_count += 1
        except Exception:
            fail_count += 1
            
    await message.answer(
        "✅ <b>Рассылка завершена!</b>\n\n"
        f"📈 Успешно отправлено: <b>{success_count}</b>\n"
        f"📉 Не удалось отправить: <b>{fail_count}</b>",
        parse_mode="HTML"
    )

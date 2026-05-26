import json
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import User, Subscription, SubscriptionStatus, ReferralReward, Payment, PaymentGateway, PaymentStatus, TariffPlan, Server, SystemSetting
from app.bot.localization import MESSAGES
from app.services.payments import PaymentService
from app.services.xui_service import generate_subscription_link, update_vpn_client, format_datetime_msk
from app.bot.keyboards import (
    get_profile_menu_keyboard,
    get_subscriptions_list_keyboard,
    get_sub_detail_keyboard,
    get_renew_durations_keyboard,
    get_renew_payment_methods_keyboard,
    get_renew_gateways_keyboard,
    get_deposit_gateways_keyboard,
    get_back_to_profile_keyboard,
    get_payment_keyboard
)
from app.config import settings

logger = logging.getLogger(__name__)
router = Router()

class ProfileState(StatesGroup):
    entering_amount = State()
    entering_promocode = State()

def format_bytes(b: int) -> str:
    """Format bytes into a human readable string in GB."""
    gb = b / (1024 ** 3)
    return f"{gb:.2f}"

# Main Profile menu trigger via text message
@router.message(F.text.in_([MESSAGES["ru"]["menu_profile"], MESSAGES["en"]["menu_profile"]]))
async def show_profile_msg(message: types.Message, user: User, db_session: AsyncSession, state: FSMContext):
    await state.clear()
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    balance_rub = user.balance_kopeks / 100.0
    
    # Check if they already have a trial subscription
    trial_sub_query = await db_session.execute(
        select(Subscription).join(TariffPlan).where(
            Subscription.user_id == user.id,
            TariffPlan.price_kopeks == 0
        )
    )
    has_trial = trial_sub_query.scalars().first() is not None
            
    text = msgs["profile_main"].format(
        user_id=user.id,
        balance=f"{balance_rub:.2f}"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_profile_menu_keyboard(lang, has_trial=has_trial))

# Main Profile menu trigger via callback
@router.callback_query(F.data == "profile_main")
async def show_profile_cb(callback: types.CallbackQuery, user: User, db_session: AsyncSession, state: FSMContext):
    await state.clear()
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    balance_rub = user.balance_kopeks / 100.0
    
    # Check if they already have a trial subscription
    trial_sub_query = await db_session.execute(
        select(Subscription).join(TariffPlan).where(
            Subscription.user_id == user.id,
            TariffPlan.price_kopeks == 0
        )
    )
    has_trial = trial_sub_query.scalars().first() is not None
            
    text = msgs["profile_main"].format(
        user_id=callback.from_user.id,
        balance=f"{balance_rub:.2f}"
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_profile_menu_keyboard(lang, has_trial=has_trial))
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=get_profile_menu_keyboard(lang, has_trial=has_trial))
    await callback.answer()

# Section 1.2: My Subscriptions list
@router.callback_query(F.data == "profile_my_subs")
async def profile_my_subs(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    subs_query = await db_session.execute(
        select(Subscription).options(selectinload(Subscription.tariff)).where(
            Subscription.user_id == user.id,
            Subscription.status != SubscriptionStatus.DELETED
        )
    )
    subs = subs_query.scalars().all()
    
    if not subs:
        await callback.message.edit_text(
            msgs["no_subs"],
            parse_mode="HTML",
            reply_markup=get_back_to_profile_keyboard(lang)
        )
    else:
        text = "🎫 <b>Ваши подписки:</b>" if lang == "ru" else "🎫 <b>Your subscriptions:</b>"
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_subscriptions_list_keyboard(subs, lang)
        )
    await callback.answer()

# View single subscription details
@router.callback_query(F.data.startswith("view_sub:"))
async def view_sub(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    sub_id = callback.data.split(":")[1]
    
    subscription = await db_session.execute(
        select(Subscription).options(selectinload(Subscription.tariff)).where(Subscription.sub_id == sub_id)
    )
    sub = subscription.scalars().first()
    if not sub:
        await callback.answer("Подписка не найдена." if lang == "ru" else "Subscription not found.")
        return
        
    config_link = "Не удалось сгенерировать"
    server = await db_session.get(Server, sub.server_id)
    if server:
        config_link = generate_subscription_link(server, sub.sub_id)
            
    expiry_str = format_datetime_msk(sub.expires_at, lang)
    tariff_name = sub.tariff.name_ru if lang == "ru" else sub.tariff.name_en
    limit_str = format_bytes(sub.traffic_limit_bytes) if sub.traffic_limit_bytes > 0 else ("∞" if lang == "ru" else "Unlimited")
    used_str = format_bytes(sub.total_used_bytes)
    
    # Calculate tariff duration in days
    duration_days = sub.tariff.duration_days
    
    sub_text = (
        f"🎫 <b>Подписка {sub.sub_id}</b>\n\n"
        f"• Статус: <b>{sub.status.value}</b>\n"
        f"• Тариф: <i>{tariff_name}</i> ({duration_days} дней)\n"
        f"• Трафик: <b>{used_str} / {limit_str} GB</b>\n"
        f"• Действует до: <b>{expiry_str}</b>\n\n"
        f"🔗 <b>Ссылка для подключения:</b>\n<code>{config_link}</code>"
        if lang == "ru" else
        f"🎫 <b>Subscription {sub.sub_id}</b>\n\n"
        f"• Status: <b>{sub.status.value}</b>\n"
        f"• Tariff: <i>{tariff_name}</i> ({duration_days} days)\n"
        f"• Traffic: <b>{used_str} / {limit_str} GB</b>\n"
        f"• Expires: <b>{expiry_str}</b>\n\n"
        f"🔗 <b>Config Link:</b>\n<code>{config_link}</code>"
    )
    
    is_trial = sub.tariff.price_kopeks == 0
    await callback.message.edit_text(
        sub_text,
        parse_mode="HTML",
        reply_markup=get_sub_detail_keyboard(sub_id, lang, auto_renew=sub.auto_renew, show_renew=not is_trial)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_auto_renew:"))
async def toggle_auto_renew_handler(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    sub_id = callback.data.split(":")[1]
    
    sub_query = await db_session.execute(
        select(Subscription).options(selectinload(Subscription.tariff)).where(Subscription.sub_id == sub_id)
    )
    sub = sub_query.scalars().first()
    if not sub:
        await callback.answer("Подписка не найдена." if lang == "ru" else "Subscription not found.")
        return
        
    sub.auto_renew = not sub.auto_renew
    db_session.add(sub)
    await db_session.commit()
    
    if sub.auto_renew:
        msg = "✅ Автопродление включено! Баланс будет списываться при окончании срока подписки." if lang == "ru" else "✅ Auto-renewal enabled! Balance will be deducted at subscription expiry."
    else:
        msg = "❌ Автопродление выключено." if lang == "ru" else "❌ Auto-renewal disabled."
        
    await callback.answer(msg, show_alert=True)
    
    config_link = "Не удалось сгенерировать"
    server = await db_session.get(Server, sub.server_id)
    if server:
        config_link = generate_subscription_link(server, sub.sub_id)
            
    expiry_str = format_datetime_msk(sub.expires_at, lang)
    tariff_name = sub.tariff.name_ru if lang == "ru" else sub.tariff.name_en
    limit_str = format_bytes(sub.traffic_limit_bytes) if sub.traffic_limit_bytes > 0 else ("∞" if lang == "ru" else "Unlimited")
    used_str = format_bytes(sub.total_used_bytes)
    duration_days = sub.tariff.duration_days
    
    sub_text = (
        f"🎫 <b>Подписка {sub.sub_id}</b>\n\n"
        f"• Статус: <b>{sub.status.value}</b>\n"
        f"• Тариф: <i>{tariff_name}</i> ({duration_days} дней)\n"
        f"• Трафик: <b>{used_str} / {limit_str} GB</b>\n"
        f"• Действует до: <b>{expiry_str}</b>\n\n"
        f"🔗 <b>Ссылка для подключения:</b>\n<code>{config_link}</code>"
        if lang == "ru" else
        f"🎫 <b>Subscription {sub.sub_id}</b>\n\n"
        f"• Status: <b>{sub.status.value}</b>\n"
        f"• Tariff: <i>{tariff_name}</i> ({duration_days} days)\n"
        f"• Traffic: <b>{used_str} / {limit_str} GB</b>\n"
        f"• Expires: <b>{expiry_str}</b>\n\n"
        f"🔗 <b>Config Link:</b>\n<code>{config_link}</code>"
    )
    
    is_trial = sub.tariff.price_kopeks == 0
    await callback.message.edit_text(
        sub_text,
        parse_mode="HTML",
        reply_markup=get_sub_detail_keyboard(sub_id, lang, auto_renew=sub.auto_renew, show_renew=not is_trial)
    )

# Section 1.3: Renew subscription flow (select which sub to renew)
@router.callback_query(F.data == "profile_renew_subs")
async def profile_renew_subs(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    lang = user.language or "ru"
    
    subs_query = await db_session.execute(
        select(Subscription).options(selectinload(Subscription.tariff)).where(
            Subscription.user_id == user.id,
            Subscription.status != SubscriptionStatus.DELETED
        )
    )
    subs = subs_query.scalars().all()
    # Filter out trial/test subscriptions (price_kopeks == 0)
    subs = [s for s in subs if s.tariff.price_kopeks > 0]
    
    if not subs:
        msg = "У вас пока нет подписок для продления. Сначала купите подписку в магазине!" if lang == "ru" else "You don't have any subscriptions to renew yet. Purchase a subscription first!"
        await callback.message.edit_text(msg, reply_markup=get_back_to_profile_keyboard(lang))
    elif len(subs) == 1:
        # Directly go to selecting duration for that single sub
        await renew_sub_from_detail(callback, user, db_session, subs[0].sub_id)
    else:
        # Show list to choose which one
        text = "Выберите подписку для продления:" if lang == "ru" else "Choose subscription to renew:"
        keyboard = []
        for sub in subs:
            label = f"🎫 {sub.sub_id} ({sub.tariff.name_ru if lang == 'ru' else sub.tariff.name_en})"
            keyboard.append([InlineKeyboardButton(text=label, callback_data=f"renew_sub_from_detail:{sub.sub_id}")])
        keyboard.append([InlineKeyboardButton(text=MESSAGES[lang]["back"], callback_data="profile_main")])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

# Callback handler for renewing specific sub (duration selection)
@router.callback_query(F.data.startswith("renew_sub_from_detail:"))
async def renew_sub_from_detail_cb(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    sub_id = callback.data.split(":")[1]
    await renew_sub_from_detail(callback, user, db_session, sub_id)
    await callback.answer()

async def renew_sub_from_detail(callback: types.CallbackQuery, user: User, db_session: AsyncSession, sub_id: str):
    lang = user.language or "ru"

    # Fetch subscription to check if it's a trial
    sub_query = await db_session.execute(
        select(Subscription).options(selectinload(Subscription.tariff)).where(Subscription.sub_id == sub_id)
    )
    sub = sub_query.scalars().first()
    if not sub:
        await callback.message.edit_text(
            "Подписка не найдена." if lang == "ru" else "Subscription not found.",
            reply_markup=get_back_to_profile_keyboard(lang)
        )
        return
        
    if sub.tariff.price_kopeks == 0:
        await callback.message.edit_text(
            "Тестовую подписку нельзя продлить. Пожалуйста, приобретите новую подписку в магазине." 
            if lang == "ru" else 
            "Trial subscription cannot be renewed. Please purchase a new subscription in the shop.",
            reply_markup=get_back_to_profile_keyboard(lang)
        )
        return

    text = (
        f"🔄 <b>Продление подписки {sub_id}</b>\n\n"
        "Выберите желаемый период продления:"
        if lang == "ru" else
        f"🔄 <b>Renewing subscription {sub_id}</b>\n\n"
        "Select desired renewal duration:"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_renew_durations_keyboard(sub_id, lang)
    )

# Select payment method (Balance or Gateway) for a given duration
@router.callback_query(F.data.startswith("renew_dur:"))
async def renew_dur(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    parts = callback.data.split(":")
    sub_id = parts[1]
    days = int(parts[2])
    sub_query = await db_session.execute(select(Subscription).where(Subscription.sub_id == sub_id))
    sub = sub_query.scalars().first()
    if not sub:
        await callback.answer("Подписка не найдена." if lang == "ru" else "Subscription not found.")
        return
    tariff = await db_session.get(TariffPlan, sub.tariff_id)
    if not tariff:
        await callback.answer("Тариф не найден." if lang == "ru" else "Tariff not found.")
        return
        
    if tariff.price_kopeks == 0:
        await callback.answer(
            "Тестовую подписку нельзя продлить." if lang == "ru" else "Trial subscription cannot be renewed.",
            show_alert=True
        )
        return
        
    # Cost proportional to duration
    cost_rub = (days / tariff.duration_days) * (tariff.price_kopeks / 100.0)
    # round to nearest kopek/integer
    cost_rub = round(cost_rub, 2)
    
    text = (
        f"🔄 <b>Продление подписки {sub_id} на {days} дней</b>\n\n"
        f"Стоимость: <b>{cost_rub:.2f} руб.</b>\n"
        f"Ваш текущий баланс: <b>{user.balance_kopeks / 100.0:.2f} руб.</b>\n\n"
        "Выберите способ оплаты:"
        if lang == "ru" else
        f"🔄 <b>Renewing subscription {sub_id} for {days} days</b>\n\n"
        f"Cost: <b>{cost_rub:.2f} RUB</b>\n"
        f"Your current balance: <b>{user.balance_kopeks / 100.0:.2f} RUB</b>\n\n"
        "Select payment method:"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_renew_payment_methods_keyboard(sub_id, days, cost_rub, lang)
    )
    await callback.answer()

# Option A: Pay with Balance
@router.callback_query(F.data.startswith("renew_pay_bal:"))
async def renew_pay_bal(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    parts = callback.data.split(":")
    sub_id = parts[1]
    days = int(parts[2])
    sub_query = await db_session.execute(select(Subscription).where(Subscription.sub_id == sub_id))
    sub = sub_query.scalars().first()
    if not sub:
        await callback.answer("Подписка не найдена." if lang == "ru" else "Subscription not found.")
        return
    tariff = await db_session.get(TariffPlan, sub.tariff_id)
    if not tariff:
        await callback.answer("Тариф не найден." if lang == "ru" else "Tariff not found.")
        return
        
    cost_kopeks = int(round((days / tariff.duration_days) * tariff.price_kopeks))
    
    if user.balance_kopeks < cost_kopeks:
        msg = "❌ Недостаточно средств на балансе. Пожалуйста, пополните баланс!" if lang == "ru" else "❌ Insufficient balance. Please top up your balance!"
        await callback.answer(msg, show_alert=True)
        return
        
    # Deduct balance
    user.balance_kopeks -= cost_kopeks
    db_session.add(user)
    
    # Create successful payment record
    payment_id = f"bal_{uuid_hex()}"
    payment = Payment(
        id=payment_id,
        user_id=user.id,
        amount_kopeks=cost_kopeks,
        currency="RUB",
        gateway=PaymentGateway.BALANCE,
        gateway_payment_id=payment_id,
        status=PaymentStatus.COMPLETED,
        payload=json.dumps({
            "renew_days": days,
            "subscription_id": sub_id
        })
    )
    db_session.add(payment)
    await db_session.commit()
    
    # Process subscription extension
    from app.bot.handlers.shop import deliver_subscription
    await deliver_subscription(callback.message, payment, db_session, lang)
    await callback.answer()

def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:12]

# Option B: Select external payment gateway for renewal
@router.callback_query(F.data.startswith("renew_pay_gate:"))
async def renew_pay_gate(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    parts = callback.data.split(":")
    sub_id = parts[1]
    days = int(parts[2])
    
    await callback.message.edit_text(
        "Выберите платежную систему для продления:" if lang == "ru" else "Select payment gateway for renewal:",
        reply_markup=get_renew_gateways_keyboard(sub_id, days, lang)
    )
    await callback.answer()

# Process renewal external payment selection
@router.callback_query(F.data.startswith("renew_gateway:"))
async def renew_gateway_cb(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    parts = callback.data.split(":")
    sub_id = parts[1]
    days = int(parts[2])
    gateway_str = parts[3]
    sub_query = await db_session.execute(select(Subscription).where(Subscription.sub_id == sub_id))
    sub = sub_query.scalars().first()
    if not sub:
        await callback.answer("Подписка не найдена." if lang == "ru" else "Subscription not found.")
        return
    tariff = await db_session.get(TariffPlan, sub.tariff_id)
    if not tariff:
        await callback.answer("Тариф не найден." if lang == "ru" else "Tariff not found.")
        return
        
    cost_kopeks = int(round((days / tariff.duration_days) * tariff.price_kopeks))
    
    # Create payment intent
    gateway = PaymentGateway(gateway_str)
    payment, checkout_url = await PaymentService.create_payment_intent(
        db_session=db_session,
        user_id=user.id,
        amount_kopeks=cost_kopeks,
        gateway=gateway,
        tariff_id=tariff.id,
        server_id=sub.server_id,
        extra_payload={
            "renew_days": days,
            "subscription_id": sub_id
        }
    )
    
    if not payment or not checkout_url:
        await callback.answer("Ошибка при создании счета." if lang == "ru" else "Error generating invoice.", show_alert=True)
        return
        
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    await callback.message.edit_text(
        msgs["payment_created"],
        parse_mode="HTML",
        reply_markup=get_payment_keyboard(payment.id, checkout_url, lang)
    )
    await callback.answer()

# Section 1.4: Referral/Partner program
@router.callback_query(F.data == "profile_partner")
async def profile_partner(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Get bot username
    bot_info = await callback.message.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start={user.referral_code}"
    
    # Count referrals
    ref_count_query = await db_session.execute(
        select(func.count(User.id)).where(User.referred_by_id == user.id)
    )
    ref_count = ref_count_query.scalar() or 0
    
    # Sum earned commissions
    earned_query = await db_session.execute(
        select(func.sum(ReferralReward.amount_kopeks)).where(ReferralReward.referrer_id == user.id)
    )
    earned_kopeks = earned_query.scalar() or 0
    earned_rub = float(earned_kopeks) / 100.0
    
    percent = settings.REFERRAL_PERCENT
    text = msgs["partner_desc"].format(
        percent=percent,
        ref_link=ref_link,
        ref_count=ref_count,
        earned=f"{earned_rub:.2f}"
    )
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_back_to_profile_keyboard(lang)
    )
    await callback.answer()

# Section 1.5: Top Up Balance FSM trigger
@router.callback_query(F.data == "profile_topup")
async def profile_topup(callback: types.CallbackQuery, user: User, state: FSMContext):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    await callback.message.edit_text(
        msgs["balance_topup"],
        parse_mode="HTML",
        reply_markup=get_back_to_profile_keyboard(lang)
    )
    await state.set_state(ProfileState.entering_amount)
    await callback.answer()

# Process entering deposit amount
@router.message(ProfileState.entering_amount)
async def process_entering_amount(message: types.Message, state: FSMContext, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    amount_str = message.text.strip()
    
    try:
        amount_rub = int(amount_str)
        if amount_rub <= 0:
            raise ValueError
    except ValueError:
        msg = "❌ Пожалуйста, введите положительное целое число рублей:" if lang == "ru" else "❌ Please enter a positive integer amount in RUB:"
        await message.answer(msg)
        return
        
    await state.clear()
    
    # Show gateway selection for deposit
    text = f"Сумма пополнения: <b>{amount_rub} руб.</b>\nВыберите способ оплаты:" if lang == "ru" else f"Top up amount: <b>{amount_rub} RUB</b>\nSelect payment method:"
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_deposit_gateways_keyboard(amount_rub, lang)
    )

# Process selection of deposit gateway
@router.callback_query(F.data.startswith("deposit_gateway:"))
async def deposit_gateway_cb(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    parts = callback.data.split(":")
    amount_rub = int(parts[1])
    gateway_str = parts[2]
    
    gateway = PaymentGateway(gateway_str)
    amount_kopeks = amount_rub * 100
    
    payment, checkout_url = await PaymentService.create_payment_intent(
        db_session=db_session,
        user_id=user.id,
        amount_kopeks=amount_kopeks,
        gateway=gateway
        # No tariff_id, meaning it is a deposit payment
    )
    
    if not payment or not checkout_url:
        await callback.answer("Ошибка при создании счета." if lang == "ru" else "Error generating invoice.", show_alert=True)
        return
        
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    await callback.message.edit_text(
        msgs["payment_created"],
        parse_mode="HTML",
        reply_markup=get_payment_keyboard(payment.id, checkout_url, lang)
    )
    await callback.answer()

# Section 1.5: Deposit History
@router.callback_query(F.data == "profile_history")
async def profile_history(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Fetch last 10 completed payments (deposits or promocodes)
    # We display payments where amount_kopeks > 0 and status is COMPLETED
    payments_query = await db_session.execute(
        select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == PaymentStatus.COMPLETED
        ).order_by(Payment.created_at.desc()).limit(10)
    )
    payments = payments_query.scalars().all()
    
    if not payments:
        await callback.message.edit_text(
            msgs["no_history"],
            parse_mode="HTML",
            reply_markup=get_back_to_profile_keyboard(lang)
        )
    else:
        history_text = ""
        for pm in payments:
            # Determine payment description/gateway
            gw_label = pm.gateway.value
            if pm.gateway == PaymentGateway.PROMOCODE:
                try:
                    payload = json.loads(pm.payload) if pm.payload else {}
                    promo = payload.get("promocode", "")
                    gw_label = f"Промокод ({promo})" if lang == "ru" else f"Promo ({promo})"
                except Exception:
                    gw_label = "Промокод" if lang == "ru" else "Promo"
            elif pm.gateway == PaymentGateway.BALANCE:
                gw_label = "Баланс" if lang == "ru" else "Balance"
                
            history_text += msgs["history_item"].format(
                date=pm.created_at.strftime("%d.%m.%Y %H:%M"),
                amount=f"{pm.amount_kopeks / 100.0:.2f}",
                gateway=gw_label
            )
            
        await callback.message.edit_text(
            msgs["history_desc"].format(history=history_text),
            parse_mode="HTML",
            reply_markup=get_back_to_profile_keyboard(lang)
        )
    await callback.answer()

# Section 1.5: Promocode activation FSM trigger
@router.callback_query(F.data == "profile_promocode")
async def profile_promocode(callback: types.CallbackQuery, user: User, state: FSMContext):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    await callback.message.edit_text(
        msgs["promocode_enter"],
        parse_mode="HTML",
        reply_markup=get_back_to_profile_keyboard(lang)
    )
    await state.set_state(ProfileState.entering_promocode)
    await callback.answer()

# Process entering promocode
@router.message(ProfileState.entering_promocode)
async def process_entering_promocode(message: types.Message, state: FSMContext, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    code_str = message.text.strip()
    
    await state.clear()
    
    success, result_str = await PaymentService.apply_promocode(db_session, user.id, code_str)
    
    if not success:
        err_msg = msgs["promocode_error"].format(error=result_str)
        await message.answer(err_msg, parse_mode="HTML")
        return
        
    if result_str.startswith("SUBSCRIPTION:"):
        payment_id = result_str.split(":")[1]
        # Deliver the subscription promocode immediately
        payment = await db_session.get(Payment, payment_id)
        if payment:
            from app.bot.handlers.shop import deliver_subscription
            await deliver_subscription(message, payment, db_session, lang)
            await message.answer("🎉 <b>Промокод на подписку успешно активирован!</b>" if lang == "ru" else "🎉 <b>Subscription promocode activated successfully!</b>", parse_mode="HTML")
        else:
            await message.answer("⚠️ Внутренняя ошибка при доставке подписки." if lang == "ru" else "⚠️ Internal error delivering subscription.")
    else:
        # It was a balance promocode, result_str is the success message
        await message.answer(f"✅ {result_str}", parse_mode="HTML")

# Section 1.6: Instructions menu
@router.callback_query(F.data == "profile_instructions")
async def profile_instructions(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Try fetching custom instructions from SystemSetting
    setting_query = await db_session.execute(
        select(SystemSetting).where(SystemSetting.key == "instructions_text")
    )
    setting = setting_query.scalars().first()
    
    inst_text = setting.value if setting else msgs["default_instructions"]
    
    await callback.message.edit_text(
        msgs["instructions_title"].format(text=inst_text),
        parse_mode="HTML",
        reply_markup=get_back_to_profile_keyboard(lang)
    )
    await callback.answer()

# Process trial subscription activation
@router.callback_query(F.data == "profile_trial")
async def profile_trial_handler(callback: types.CallbackQuery, user: User, db_session: AsyncSession):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # 1. Check if they already have a trial subscription
    trial_tariff_query = await db_session.execute(
        select(TariffPlan).where(TariffPlan.price_kopeks == 0, TariffPlan.duration_days == 3)
    )
    trial_tariff = trial_tariff_query.scalars().first()
    
    # If trial tariff is somehow missing, we seed it dynamically
    if not trial_tariff:
        trial_tariff = TariffPlan(
            name_ru="Тестовый (3 дня)",
            name_en="Test Plan (3 Days)",
            duration_days=3,
            traffic_limit_gb=10,
            price_kopeks=0,
            is_enabled=True
        )
        db_session.add(trial_tariff)
        await db_session.commit()
        await db_session.refresh(trial_tariff)
        
    trial_sub_query = await db_session.execute(
        select(Subscription).join(TariffPlan).where(
            Subscription.user_id == user.id,
            TariffPlan.price_kopeks == 0
        )
    )
    if trial_sub_query.scalars().first():
        await callback.answer(
            "Вы уже использовали тестовый период!" if lang == "ru" else "You have already used the test period!",
            show_alert=True
        )
        return
        
    # 2. Find an active server
    server_query = await db_session.execute(
        select(Server).where(Server.is_enabled == True)
    )
    server = server_query.scalars().first()
    if not server:
        await callback.answer(
            "К сожалению, сейчас нет свободных серверов для выдачи теста." if lang == "ru" else "Sorry, no active servers are available to provision trial.",
            show_alert=True
        )
        return

    # 3. Create the trial client on X-UI panel
    import uuid
    from app.services.xui_service import create_vpn_client
    
    sub_id = str(uuid.uuid4())[:8]
    client_uuid = str(uuid.uuid4())
    client_email = f"usr_{user.id}_sub_{sub_id}"
    
    expires_at = datetime.utcnow() + timedelta(days=3)
    traffic_limit_bytes = 10 * 1024 * 1024 * 1024 # 10 GB
    inbound_id = 1
    
    try:
        config_link = await create_vpn_client(
            server=server,
            inbound_id=inbound_id,
            email=client_email,
            uuid_str=client_uuid,
            expires_at=expires_at,
            traffic_limit_bytes=traffic_limit_bytes
        )
        
        subscription = Subscription(
            sub_id=sub_id,
            user_id=user.id,
            tariff_id=trial_tariff.id,
            server_id=server.id,
            inbound_id=inbound_id,
            client_uuid=client_uuid,
            client_email=client_email,
            status=SubscriptionStatus.ACTIVE,
            expires_at=expires_at,
            traffic_limit_bytes=traffic_limit_bytes
        )
        db_session.add(subscription)
        await db_session.commit()
        
        success_msg = (
            "✅ <b>Тестовый период успешно активирован!</b>\n\n"
            "Вам выдана подписка на 3 дня с лимитом 10 ГБ.\n\n"
            "🔗 <b>Ссылка для подключения:</b>\n"
            f"<code>{config_link}</code>\n\n"
            "Инструкцию по настройке приложения вы можете найти в личном кабинете."
            if lang == "ru" else
            "✅ <b>Test period activated successfully!</b>\n\n"
            "You have been granted a 3-day subscription with a 10 GB limit.\n\n"
            "🔗 <b>Connection link:</b>\n"
            f"<code>{config_link}</code>"
        )
        await callback.message.edit_text(
            success_msg,
            parse_mode="HTML",
            reply_markup=get_back_to_profile_keyboard(lang)
        )
        
    except Exception as e:
        logger.error(f"Failed to create trial subscription for user {user.id}: {e}", exc_info=True)
        await callback.answer(
            "Произошла ошибка при создании подписки. Попробуйте позже." if lang == "ru" else "An error occurred. Please try again later.",
            show_alert=True
        )


import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, TariffPlan, Server, Payment, PaymentGateway, PaymentStatus, Subscription, SubscriptionStatus
from app.services.payments import PaymentService
from app.services.xui_service import create_vpn_client, update_vpn_client, format_datetime_msk
from app.bot.localization import MESSAGES
from app.bot.keyboards import (
    get_tariffs_keyboard,
    get_servers_keyboard,
    get_gateways_keyboard,
    get_payment_keyboard
)
from app.config import settings

logger = logging.getLogger(__name__)
router = Router()

class ShopState(StatesGroup):
    choosing_tariff = State()
    choosing_server = State()
    choosing_gateway = State()
    waiting_for_payment = State()

@router.message(F.text.in_([MESSAGES["ru"]["menu_shop"], MESSAGES["en"]["menu_shop"]]))
async def start_shop(message: types.Message, user: User, db_session: AsyncSession, state: FSMContext):
    await state.clear()
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Fetch active tariffs (excluding trial/free tariffs)
    tariffs_query = await db_session.execute(
        select(TariffPlan).where(TariffPlan.is_enabled == True, TariffPlan.price_kopeks > 0)
    )
    tariffs = tariffs_query.scalars().all()
    
    if not tariffs:
        await message.answer("Извините, в данный момент нет доступных тарифных планов." if lang == "ru" else "Sorry, there are no tariff plans available at the moment.")
        return
        
    kb = get_tariffs_keyboard(tariffs, lang)
    await message.answer(msgs["shop_choose_tariff"], reply_markup=kb, parse_mode="HTML")
    await state.set_state(ShopState.choosing_tariff)

@router.callback_query(F.data.startswith("select_tariff:"))
async def select_tariff_handler(callback: types.CallbackQuery, state: FSMContext, db_session: AsyncSession, user: User):
    tariff_id = int(callback.data.split(":")[1])
    await state.update_data(tariff_id=tariff_id)
    
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Fetch active servers
    servers_query = await db_session.execute(
        select(Server).where(Server.is_enabled == True)
    )
    servers = servers_query.scalars().all()
    
    if not servers:
        await callback.answer("Нет доступных серверов" if lang == "ru" else "No servers available", show_alert=True)
        return
        
    kb = get_servers_keyboard(servers, lang)
    await callback.message.edit_text(msgs["shop_choose_server"], reply_markup=kb, parse_mode="HTML")
    await state.set_state(ShopState.choosing_server)
    await callback.answer()

@router.callback_query(F.data == "shop_back_tariffs")
async def back_to_tariffs_handler(callback: types.CallbackQuery, state: FSMContext, db_session: AsyncSession, user: User):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Fetch active tariffs (excluding trial/free tariffs)
    tariffs_query = await db_session.execute(
        select(TariffPlan).where(TariffPlan.is_enabled == True, TariffPlan.price_kopeks > 0)
    )
    tariffs = tariffs_query.scalars().all()
    
    kb = get_tariffs_keyboard(tariffs, lang)
    await callback.message.edit_text(msgs["shop_choose_tariff"], reply_markup=kb, parse_mode="HTML")
    await state.set_state(ShopState.choosing_tariff)
    await callback.answer()

@router.callback_query(F.data.startswith("select_server:"))
async def select_server_handler(callback: types.CallbackQuery, state: FSMContext, db_session: AsyncSession, user: User):
    server_id = int(callback.data.split(":")[1])
    await state.update_data(server_id=server_id)
    
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    data = await state.get_data()
    tariff = await db_session.get(TariffPlan, data["tariff_id"])
    
    price_rub = tariff.price_kopeks / 100.0
    kb = get_gateways_keyboard(lang, balance_kopeks=user.balance_kopeks)
    
    await callback.message.edit_text(
        msgs["shop_choose_gateway"].format(amount=f"{price_rub:.2f}"),
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.set_state(ShopState.choosing_gateway)
    await callback.answer()

@router.callback_query(F.data == "shop_back_servers")
async def back_to_servers_handler(callback: types.CallbackQuery, state: FSMContext, db_session: AsyncSession, user: User):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    servers_query = await db_session.execute(
        select(Server).where(Server.is_enabled == True)
    )
    servers = servers_query.scalars().all()
    
    kb = get_servers_keyboard(servers, lang)
    await callback.message.edit_text(msgs["shop_choose_server"], reply_markup=kb, parse_mode="HTML")
    await state.set_state(ShopState.choosing_server)
    await callback.answer()

@router.callback_query(F.data.startswith("select_gateway:"))
async def select_gateway_handler(callback: types.CallbackQuery, state: FSMContext, db_session: AsyncSession, user: User):
    gateway_str = callback.data.split(":")[1]
    gateway = PaymentGateway(gateway_str)
    
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    data = await state.get_data()
    tariff = await db_session.get(TariffPlan, data["tariff_id"])
    server = await db_session.get(Server, data["server_id"])
    
    price_kopeks = tariff.price_kopeks
    price_rub = price_kopeks / 100.0
    
    # Balance payment flow
    if gateway == PaymentGateway.BALANCE:
        if user.balance_kopeks < price_kopeks:
            msg = "❌ Недостаточно средств на балансе. Пожалуйста, пополните баланс!" if lang == "ru" else "❌ Insufficient balance. Please top up your balance!"
            await callback.answer(msg, show_alert=True)
            return
            
        # Deduct balance
        user.balance_kopeks -= price_kopeks
        db_session.add(user)
        
        import uuid
        payment_id = f"bal_{uuid.uuid4().hex[:12]}"
        payment = Payment(
            id=payment_id,
            user_id=user.id,
            amount_kopeks=price_kopeks,
            currency="RUB",
            gateway=gateway,
            gateway_payment_id=payment_id,
            status=PaymentStatus.COMPLETED,
            payload=json.dumps({"tariff_id": tariff.id, "server_id": server.id})
        )
        db_session.add(payment)
        await db_session.commit()
        
        # Deliver subscription
        await deliver_subscription(callback.message, payment, db_session, lang)
        await state.clear()
        await callback.answer()
        return

    # Telegram Stars Invoice flow
    if gateway == PaymentGateway.TELEGRAM_STARS:
        stars_amount = max(1, int(price_kopeks / 200)) # Simple 1 Star = 2 RUB conversion
        payment_id = f"stars_{callback.from_user.id}_{int(datetime.utcnow().timestamp())}"
        
        # Create payment record in DB
        payment = Payment(
            id=payment_id,
            user_id=user.id,
            amount_kopeks=price_kopeks,
            currency="STARS",
            gateway=gateway,
            gateway_payment_id=payment_id,
            status=PaymentStatus.PENDING,
            payload=json.dumps({"tariff_id": tariff.id, "server_id": server.id})
        )
        db_session.add(payment)
        await db_session.commit()
        
        await callback.message.delete()
        await callback.message.answer_invoice(
            title=tariff.name_ru if lang == "ru" else tariff.name_en,
            description=f"VPN Subscription for {tariff.duration_days} days" if lang == "en" else f"VPN Подписка на {tariff.duration_days} дней",
            payload=payment_id,
            provider_token="", # Empty for Stars
            currency="XTR",
            prices=[types.LabeledPrice(label="Stars" if lang == "en" else "Звезды", amount=stars_amount)],
            start_parameter="vpn_buy"
        )
        await state.clear()
        await callback.answer()
        return

    # Regular payment intent creation
    payment, checkout_url = await PaymentService.create_payment_intent(
        db_session=db_session,
        user_id=user.id,
        amount_kopeks=price_kopeks,
        gateway=gateway,
        tariff_id=tariff.id,
        server_id=server.id
    )
    
    # If API not configured or error occurs (e.g. testing / sandbox), provide a sandbox payment option!
    if not checkout_url:
        # Create a sandbox payment URL
        payment_id = f"sandbox_{callback.from_user.id}_{int(datetime.utcnow().timestamp())}"
        payment = Payment(
            id=payment_id,
            user_id=user.id,
            amount_kopeks=price_kopeks,
            currency="RUB",
            gateway=gateway,
            gateway_payment_id=f"sb_{payment_id}",
            status=PaymentStatus.PENDING,
            payload=json.dumps({"tariff_id": tariff.id, "server_id": server.id})
        )
        db_session.add(payment)
        await db_session.commit()
        checkout_url = f"{settings.WEB_URL}/sandbox/pay?id={payment_id}"
        logger.info(f"Created sandbox payment URL for {gateway}: {checkout_url}")
        
    kb = get_payment_keyboard(payment.id, checkout_url, lang)
    
    # For manual crypto transfers, add manual payment details text
    instructions = ""
    if gateway == PaymentGateway.TON:
        instructions = f"\n\n💎 <b>TON Transfer Instructions:</b>\nОтправьте <code>{price_rub/92.0:.4f} TON</code> на адрес:\n<code>{settings.TON_WALLET or 'UQ...wallet_address'}</code>\nПосле этого нажмите проверить."
    elif gateway == PaymentGateway.USDT_TRC20:
        instructions = f"\n\n💵 <b>USDT TRC20 Transfer Instructions:</b>\nОтправьте <code>{price_rub/92.0:.2f} USDT</code> на адрес:\n<code>{settings.USDT_TRC20_WALLET or 'T...wallet_address'}</code>\nПосле этого нажмите проверить."
        
    await callback.message.edit_text(
        f"{msgs['payment_created']}{instructions}",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data.startswith("check_pay:"))
async def check_payment_handler(callback: types.CallbackQuery, db_session: AsyncSession, user: User):
    payment_id = callback.data.split(":")[1]
    
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    payment = await db_session.get(Payment, payment_id)
    if not payment:
        await callback.answer("Платеж не найден" if lang == "ru" else "Payment not found", show_alert=True)
        return
        
    if payment.status == PaymentStatus.COMPLETED:
        await deliver_subscription(callback.message, payment, db_session, lang)
        await callback.answer()
        return
        
    # Check if sandbox payment or normal payment completed
    is_paid = False
    if payment.id.startswith("sandbox_") or (payment.gateway_payment_id and (payment.gateway_payment_id.startswith("sb_") or payment.gateway_payment_id.startswith("rollypay_mock_"))):
        # Auto approve sandbox payments on check for easy testing!
        is_paid = True
    else:
        # Check actual status
        is_paid = await PaymentService.check_and_complete_payment(db_session, payment.id)
        
    if is_paid:
        if payment.status != PaymentStatus.COMPLETED:
            await PaymentService.complete_payment(db_session, payment)
        await deliver_subscription(callback.message, payment, db_session, lang)
    else:
        await callback.answer(msgs["payment_pending"], show_alert=True)

@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_handler(callback: types.CallbackQuery, user: User):
    lang = user.language or "ru"
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    await callback.message.edit_text("❌ Платеж отменен." if lang == "ru" else "❌ Payment cancelled.", reply_markup=None)
    await callback.answer()

async def deliver_subscription(message: types.Message, payment: Payment, db_session: AsyncSession, lang: str):
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    # Parse payload
    try:
        metadata = json.loads(payment.payload) if payment.payload else {}
    except Exception:
        metadata = {}
        
    renew_days = metadata.get("renew_days")
    subscription_id = metadata.get("subscription_id")
    
    # Check if this is a balance top-up (deposit) payment
    is_deposit = False
    try:
        if not metadata.get("tariff_id") and not renew_days:
            is_deposit = True
    except Exception:
        is_deposit = True
        
    if is_deposit:
        user = await db_session.get(User, payment.user_id)
        amount_rub = payment.amount_kopeks / 100.0
        balance_rub = user.balance_kopeks / 100.0 if user else 0.0
        
        try:
            await message.delete()
        except Exception:
            pass
            
        await message.answer(
            f"✅ <b>Баланс успешно пополнен на {amount_rub} руб.!</b>\n\n"
            f"Ваш текущий баланс: <b>{balance_rub} руб.</b>"
            if lang == "ru" else
            f"✅ <b>Balance successfully topped up by {amount_rub} RUB!</b>\n\n"
            f"Your current balance: <b>{balance_rub} RUB</b>",
            parse_mode="HTML"
        )
        return
    
    if renew_days and subscription_id:
        # Renewal flow
        sub_query = await db_session.execute(select(Subscription).where(Subscription.sub_id == subscription_id))
        subscription = sub_query.scalars().first()
        if not subscription:
            await message.answer("Ошибка: подписка для продления не найдена." if lang == "ru" else "Error: subscription to renew not found.")
            return
            
        server = await db_session.get(Server, subscription.server_id)
        if not server:
            await message.answer("Ошибка: сервер подписки не найден." if lang == "ru" else "Error: subscription server not found.")
            return
            
        # Extend expires_at
        now = datetime.utcnow()
        if subscription.expires_at and subscription.expires_at > now:
            subscription.expires_at = subscription.expires_at + timedelta(days=renew_days)
        else:
            subscription.expires_at = now + timedelta(days=renew_days)
            
        subscription.status = SubscriptionStatus.ACTIVE
        db_session.add(subscription)
        await db_session.commit()
        
        # Update client on panel
        try:
            await update_vpn_client(
                server=server,
                inbound_id=subscription.inbound_id,
                client_uuid=subscription.client_uuid,
                email=subscription.client_email,
                enable=True,
                expires_at=subscription.expires_at,
                traffic_limit_bytes=subscription.traffic_limit_bytes
            )
        except Exception as e:
            logger.error(f"Failed to update VPN client on panel: {e}", exc_info=True)
            
        try:
            await message.delete()
        except Exception:
            pass
            
        await message.answer(
            f"✅ <b>Подписка {subscription.sub_id} успешно продлена на {renew_days} дней!</b>\n\n"
            f"Действует до: <b>{format_datetime_msk(subscription.expires_at, lang)}</b>"
            if lang == "ru" else
            f"✅ <b>Subscription {subscription.sub_id} successfully renewed for {renew_days} days!</b>\n\n"
            f"Expires: <b>{format_datetime_msk(subscription.expires_at, lang)}</b>",
            parse_mode="HTML"
        )
        return

    # Normal subscription purchase flow
    tariff = await db_session.get(TariffPlan, metadata.get("tariff_id"))
    server = await db_session.get(Server, metadata.get("server_id"))
    
    if not tariff or not server:
        await message.answer("Ошибка при обработке заказа: тариф или сервер удален." if lang == "ru" else "Order processing error: tariff or server deleted.")
        return
        
    # Create subscription
    import uuid
    sub_id = str(uuid.uuid4())[:8]
    client_uuid = str(uuid.uuid4())
    client_email = f"usr_{payment.user_id}_sub_{sub_id}"
    
    expires_at = datetime.utcnow() + timedelta(days=tariff.duration_days)
    traffic_limit_bytes = tariff.traffic_limit_gb * 1024 * 1024 * 1024
    
    # Create on panel
    try:
        # For simplicity, we assume inbound ID 1 is configured on the server
        inbound_id = 1
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
            user_id=payment.user_id,
            tariff_id=tariff.id,
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
        
        # Delete payment prompt message
        try:
            await message.delete()
        except Exception:
            pass
            
        await message.answer(
            msgs["payment_success"].format(config_link=config_link),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to deliver subscription client on panel: {e}", exc_info=True)
        await message.answer(
            "⚠️ Оплата прошла, но возникла ошибка при создании ключа на VPN сервере. Пожалуйста, обратитесь в поддержку с вашим ID."
            if lang == "ru" else
            "⚠️ Payment received, but an error occurred while generating the VPN key. Please contact support with your ID."
        )

# PreCheckout and SuccessfulPayment handlers for Telegram Stars
@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def success_payment_handler(message: types.Message, db_session: AsyncSession, user: User):
    payment_id = message.successful_payment.invoice_payload
    payment = await db_session.get(Payment, payment_id)
    if payment and payment.status == PaymentStatus.PENDING:
        await PaymentService.complete_payment(db_session, payment)
        lang = user.language or "ru"
        await deliver_subscription(message, payment, db_session, lang)

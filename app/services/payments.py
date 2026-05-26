import json
import logging
import uuid
import hmac
import hashlib
from typing import Tuple, Optional, Dict, Any
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.models import (
    Payment, PaymentGateway, PaymentStatus, User, ReferralReward,
    Promocode, UserPromocode, PromocodeType, Subscription, SubscriptionStatus, TariffPlan, Server
)
from app.services.xui_service import create_vpn_client, update_vpn_client

logger = logging.getLogger(__name__)

class PaymentService:
    @staticmethod
    async def create_yookassa_payment(payment_id: str, amount_rub: float, description: str) -> Optional[str]:
        """
        Creates a payment in YooKassa and returns the confirmation redirect URL.
        """
        if not settings.YOOKASSA_ENABLED:
            logger.warning("YooKassa is disabled in settings.")
            return None
            
        url = "https://api.yookassa.ru/v3/payments"
        headers = {
            "Idempotence-Key": payment_id,
            "Content-Type": "application/json"
        }
        
        payload = {
            "amount": {
                "value": f"{amount_rub:.2f}",
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": f"{settings.WEB_URL}/payment/success?id={payment_id}"
            },
            "description": description,
            "metadata": {
                "payment_id": payment_id
            }
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    url,
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
                    headers=headers,
                    json=payload
                )
                if resp.status_code == 200:
                    data = resp.json()
                    confirmation = data.get("confirmation", {})
                    # YooKassa payment ID (we should store this in gateway_payment_id)
                    gateway_id = data.get("id")
                    return confirmation.get("confirmation_url"), gateway_id
                else:
                    logger.error(f"YooKassa API error {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"YooKassa connection error: {e}")
        return None, None

    @staticmethod
    async def create_cryptobot_payment(payment_id: str, amount_usd: float, description: str) -> Optional[str]:
        """
        Creates an invoice in CryptoBot and returns the pay URL.
        """
        if not settings.CRYPTOBOT_ENABLED:
            logger.warning("CryptoBot is disabled in settings.")
            return None
            
        base_url = "https://testnet-pay.cryptobot.in" if settings.CRYPTOBOT_TESTNET else "https://pay.cryptobot.in"
        url = f"{base_url}/api/createInvoice"
        
        headers = {
            "Crypto-Pay-API-Token": settings.CRYPTOBOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        payload = {
            "asset": "USDT",  # Default to USDT
            "amount": f"{amount_usd:.2f}",
            "description": description,
            "paid_btn_name": "callback",
            "paid_btn_url": f"{settings.WEB_URL}/payment/success?id={payment_id}",
            "payload": payment_id
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        result = data.get("result", {})
                        pay_url = result.get("pay_url")
                        gateway_id = str(result.get("invoice_id"))
                        return pay_url, gateway_id
                logger.error(f"CryptoBot API error: {resp.text}")
            except Exception as e:
                logger.error(f"CryptoBot connection error: {e}")
        return None, None

    @staticmethod
    async def create_rollypay_payment(payment_id: str, amount_rub: float, description: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Creates a payment in RollyPay and returns the pay URL and RollyPay payment ID.
        """
        if not settings.ROLLYPAY_ENABLED:
            logger.warning("RollyPay is disabled in settings.")
            return None, None
            
        # Sandbox fallback if api key is placeholder
        if not settings.ROLLYPAY_API_KEY or settings.ROLLYPAY_API_KEY.startswith("rpk_test_api_key_placeholder") or "placeholder" in settings.ROLLYPAY_API_KEY:
            logger.info("Using RollyPay Sandbox Simulation")
            sandbox_url = f"{settings.WEB_URL}/sandbox/pay?id={payment_id}"
            return sandbox_url, f"rollypay_mock_{payment_id}"
            
        url = "https://rollypay.io/api/v1/payments"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": settings.ROLLYPAY_API_KEY,
            "X-Nonce": str(uuid.uuid4())
        }
        
        payload = {
            "amount": f"{amount_rub:.2f}",
            "payment_currency": "RUB",
            "order_id": payment_id,
            "terminal_id": settings.ROLLYPAY_TERMINAL_ID,
            "description": description,
            "success_redirect_url": f"{settings.WEB_URL}/payment/success?id={payment_id}",
            "fail_redirect_url": f"{settings.WEB_URL}/payment/fail?id={payment_id}"
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    pay_url = data.get("pay_url")
                    gateway_id = data.get("payment_id")
                    return pay_url, gateway_id
                else:
                    logger.error(f"RollyPay API error {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"RollyPay connection error: {e}")
        return None, None

    @staticmethod
    async def verify_rollypay_payment(gateway_payment_id: str) -> bool:
        """
        Checks the status of a RollyPay payment via API.
        """
        if not settings.ROLLYPAY_ENABLED or not settings.ROLLYPAY_API_KEY:
            return False
            
        if gateway_payment_id.startswith("rollypay_mock_"):
            return True
            
        url = f"https://rollypay.io/api/v1/payments/{gateway_payment_id}"
        headers = {
            "X-API-Key": settings.ROLLYPAY_API_KEY,
            "X-Nonce": str(uuid.uuid4())
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    status = str(data.get("status", "")).lower()
                    return status == "paid"
            except Exception as e:
                logger.error(f"RollyPay verification connection error: {e}")
        return False

    @classmethod
    async def create_payment_intent(
        cls,
        db_session: AsyncSession,
        user_id: int,
        amount_kopeks: int,
        gateway: PaymentGateway,
        tariff_id: Optional[int] = None,
        server_id: Optional[int] = None,
        extra_payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[Payment], Optional[str]]:
        """
        Creates a Payment record in database and initializes the payment in the selected gateway.
        Returns the Payment object and the redirect/checkout URL.
        """
        payment_id = str(uuid.uuid4())
        amount_rub = amount_kopeks / 100.0
        
        description = f"Mrzky VPN Subscription (User ID: {user_id})"
        checkout_url = None
        gateway_payment_id = None
        
        # Prepare metadata payload
        metadata = {
            "tariff_id": tariff_id,
            "server_id": server_id
        }
        if extra_payload:
            metadata.update(extra_payload)
        
        if gateway == PaymentGateway.YOOKASSA:
            checkout_url, gateway_payment_id = await cls.create_yookassa_payment(payment_id, amount_rub, description)
        elif gateway == PaymentGateway.CRYPTO_BOT:
            amount_usd = amount_rub / 92.0  # simple conversion rate for demo
            checkout_url, gateway_payment_id = await cls.create_cryptobot_payment(payment_id, amount_usd, description)
        elif gateway == PaymentGateway.ROLLYPAY:
            checkout_url, gateway_payment_id = await cls.create_rollypay_payment(payment_id, amount_rub, description)
        elif gateway == PaymentGateway.TELEGRAM_STARS:
            checkout_url = "tg_stars_invoice"
            gateway_payment_id = f"stars_{payment_id}"
        elif gateway == PaymentGateway.TON:
            checkout_url = settings.TON_WALLET
            gateway_payment_id = f"ton_{payment_id}"
        elif gateway == PaymentGateway.USDT_TRC20:
            checkout_url = settings.USDT_TRC20_WALLET
            gateway_payment_id = f"usdt_{payment_id}"
        elif gateway == PaymentGateway.BALANCE:
            checkout_url = "balance_payment"
            gateway_payment_id = f"bal_{payment_id}"
            
        if not checkout_url:
            return None, None
            
        payment = Payment(
            id=payment_id,
            user_id=user_id,
            amount_kopeks=amount_kopeks,
            currency="RUB" if gateway != PaymentGateway.TELEGRAM_STARS else "STARS",
            gateway=gateway,
            gateway_payment_id=gateway_payment_id,
            status=PaymentStatus.PENDING,
            payload=json.dumps(metadata)
        )
        
        # If it is tariff_id, assign it directly to the model attribute
        if tariff_id:
            payment.tariff_id = tariff_id
            
        db_session.add(payment)
        await db_session.commit()
        
        return payment, checkout_url

    @staticmethod
    async def verify_yookassa_payment(gateway_payment_id: str) -> bool:
        """
        Checks the status of a YooKassa payment via API.
        """
        if not settings.YOOKASSA_ENABLED:
            return False
            
        url = f"https://api.yookassa.ru/v3/payments/{gateway_payment_id}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    url,
                    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("status") == "succeeded"
            except Exception as e:
                logger.error(f"YooKassa verification connection error: {e}")
        return False

    @staticmethod
    async def verify_cryptobot_payment(gateway_payment_id: str) -> bool:
        """
        Checks the status of a CryptoBot invoice via API.
        """
        if not settings.CRYPTOBOT_ENABLED:
            return False
            
        base_url = "https://testnet-pay.cryptobot.in" if settings.CRYPTOBOT_TESTNET else "https://pay.cryptobot.in"
        url = f"{base_url}/api/getInvoices"
        
        headers = {
            "Crypto-Pay-API-Token": settings.CRYPTOBOT_API_TOKEN,
            "Content-Type": "application/json"
        }
        
        payload = {
            "invoice_ids": [int(gateway_payment_id)]
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        result = data.get("result", {})
                        items = result.get("items", [])
                        if items:
                            return items[0].get("status") == "paid"
            except Exception as e:
                logger.error(f"CryptoBot verification connection error: {e}")
        return False

    @classmethod
    async def check_and_complete_payment(cls, db_session: AsyncSession, payment_id: str) -> bool:
        """
        Checks the remote status of a pending payment, and if successful, processes subscription delivery
        and referral rewards.
        """
        payment = await db_session.get(Payment, payment_id)
        if not payment or payment.status != PaymentStatus.PENDING:
            return False
            
        is_paid = False
        
        if payment.gateway == PaymentGateway.YOOKASSA:
            is_paid = await cls.verify_yookassa_payment(payment.gateway_payment_id)
        elif payment.gateway == PaymentGateway.CRYPTO_BOT:
            is_paid = await cls.verify_cryptobot_payment(payment.gateway_payment_id)
        elif payment.gateway == PaymentGateway.ROLLYPAY:
            is_paid = await cls.verify_rollypay_payment(payment.gateway_payment_id)
        elif payment.gateway in [PaymentGateway.TELEGRAM_STARS, PaymentGateway.TON, PaymentGateway.USDT_TRC20]:
            # Stars/TON/USDT are marked manually by admin or webhook handler
            pass
            
        if is_paid:
            await cls.complete_payment(db_session, payment)
            return True
            
        return False

    @classmethod
    async def complete_payment(cls, db_session: AsyncSession, payment: Payment) -> None:
        """
        Completes the payment process:
        1. Marks Payment status as COMPLETED.
        2. If deposit, credits user's balance.
        3. Calculates and awards referral commissions (only for external gateways).
        """
        if payment.status == PaymentStatus.COMPLETED:
            return
            
        payment.status = PaymentStatus.COMPLETED
        db_session.add(payment)
        
        # Credit user balance if it is a deposit
        is_deposit = False
        try:
            metadata = json.loads(payment.payload) if payment.payload else {}
            if not metadata.get("tariff_id"):
                is_deposit = True
        except Exception:
            is_deposit = True
            
        user = await db_session.get(User, payment.user_id)
        if user and is_deposit:
            user.balance_kopeks += payment.amount_kopeks
            db_session.add(user)
            logger.info(f"Credited deposit of {payment.amount_kopeks} kopeks to user {user.id} balance.")
            
        # Referral commission logic (only for external gateways, not BALANCE or PROMOCODE)
        if user and user.referred_by_id and payment.gateway not in [PaymentGateway.BALANCE, PaymentGateway.PROMOCODE]:
            if payment.amount_kopeks >= settings.REFERRAL_MIN_DEPOSIT_KOPEKS:
                commission = int(payment.amount_kopeks * settings.REFERRAL_PERCENT / 100)
                
                # Check if this reward wasn't already created
                existing_reward = await db_session.execute(
                    select(ReferralReward).where(ReferralReward.payment_id == payment.id)
                )
                if not existing_reward.scalars().first():
                    reward = ReferralReward(
                        referrer_id=user.referred_by_id,
                        referee_id=user.id,
                        payment_id=payment.id,
                        amount_kopeks=commission,
                        is_credited=True
                    )
                    db_session.add(reward)
                    
                    # Credit to referrer balance
                    referrer = await db_session.get(User, user.referred_by_id)
                    if referrer:
                        referrer.balance_kopeks += commission
                        db_session.add(referrer)
                        logger.info(f"Credited referral commission of {commission} kopeks to user {referrer.id}")
                        
        await db_session.commit()

    @classmethod
    async def apply_promocode(cls, db_session: AsyncSession, user_id: int, code_str: str) -> Tuple[bool, str]:
        """
        Applies a promocode to the user.
        Returns:
            Tuple[bool, message_text]
        """
        import datetime
        code_str = code_str.strip().upper()
        # Find promocode
        query = select(Promocode).where(Promocode.code == code_str, Promocode.is_active == True)
        result = await db_session.execute(query)
        promocode = result.scalars().first()
        
        if not promocode:
            return False, "Промокод не найден или уже неактивен."
            
        # Check expiry date
        if promocode.expires_at and promocode.expires_at < datetime.datetime.utcnow():
            promocode.is_active = False
            db_session.add(promocode)
            await db_session.commit()
            return False, "Срок действия промокода истек."
            
        # Check uses limit
        if promocode.uses_count >= promocode.max_uses:
            promocode.is_active = False
            db_session.add(promocode)
            await db_session.commit()
            return False, "Промокод уже использован максимальное количество раз."
            
        # Check if this user already used this promocode
        user_promo_query = select(UserPromocode).where(
            UserPromocode.user_id == user_id,
            UserPromocode.promocode_id == promocode.id
        )
        up_result = await db_session.execute(user_promo_query)
        if up_result.scalars().first():
            return False, "Вы уже активировали этот промокод."
            
        # Get user
        user = await db_session.get(User, user_id)
        if not user:
            return False, "Пользователь не найден."
            
        # Create a payment record to track this promocode activation
        payment_id = f"promo_{uuid.uuid4().hex[:12]}"
        
        if promocode.type == PromocodeType.BALANCE:
            # Credit balance
            user.balance_kopeks += promocode.value_kopeks
            db_session.add(user)
            
            # Create payment record
            payment = Payment(
                id=payment_id,
                user_id=user_id,
                amount_kopeks=promocode.value_kopeks,
                currency="RUB",
                gateway=PaymentGateway.PROMOCODE,
                status=PaymentStatus.COMPLETED,
                payload=json.dumps({"promocode": code_str})
            )
            db_session.add(payment)
            
            # Record usage
            user_promo = UserPromocode(user_id=user_id, promocode_id=promocode.id)
            db_session.add(user_promo)
            
            promocode.uses_count += 1
            if promocode.uses_count >= promocode.max_uses:
                promocode.is_active = False
            db_session.add(promocode)
            
            await db_session.commit()
            val_rub = promocode.value_kopeks / 100
            return True, f"Промокод успешно активирован! На ваш баланс зачислено {val_rub:.2f} руб."
            
        elif promocode.type == PromocodeType.SUBSCRIPTION:
            if not promocode.tariff_id:
                return False, "Внутренняя ошибка промокода: тариф не указан."
                
            tariff = await db_session.get(TariffPlan, promocode.tariff_id)
            if not tariff:
                return False, "Внутренняя ошибка: указанный в промокоде тариф не найден."
                
            # Create payment record for the subscription
            duration = promocode.duration_days or tariff.duration_days
            payment = Payment(
                id=payment_id,
                user_id=user_id,
                amount_kopeks=0,
                currency="RUB",
                gateway=PaymentGateway.PROMOCODE,
                status=PaymentStatus.COMPLETED,
                payload=json.dumps({
                    "promocode": code_str,
                    "tariff_id": promocode.tariff_id,
                    "duration_days": duration
                })
            )
            db_session.add(payment)
            
            # Record usage
            user_promo = UserPromocode(user_id=user_id, promocode_id=promocode.id)
            db_session.add(user_promo)
            
            promocode.uses_count += 1
            if promocode.uses_count >= promocode.max_uses:
                promocode.is_active = False
            db_session.add(promocode)
            
            await db_session.commit()
            return True, f"SUBSCRIPTION:{payment_id}"
            
        return False, "Неизвестный тип промокода."

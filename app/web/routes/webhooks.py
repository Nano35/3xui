import logging
import json
import hmac
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Payment, PaymentStatus
from app.services.payments import PaymentService
from app.services.xui_service import create_vpn_client
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/webhook/yookassa")
async def yookassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook handler for YooKassa payment events.
    """
    try:
        body = await request.json()
        logger.info(f"YooKassa webhook received: {body}")
        
        event = body.get("event")
        if event == "payment.succeeded":
            obj = body.get("object", {})
            gateway_payment_id = obj.get("id")
            
            # Find payment
            stmt = select(Payment).where(Payment.gateway_payment_id == gateway_payment_id)
            result = await db.execute(stmt)
            payment = result.scalars().first()
            
            if payment and payment.status == PaymentStatus.PENDING:
                await PaymentService.complete_payment(db, payment)
                logger.info(f"YooKassa payment {payment.id} completed via webhook.")
                
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error in YooKassa webhook: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid request")

@router.post("/webhook/cryptobot")
async def cryptobot_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook handler for CryptoBot payment events.
    """
    try:
        body = await request.json()
        logger.info(f"CryptoBot webhook received: {body}")
        
        # CryptoBot sends update_type = 'invoice_paid'
        update_type = body.get("update_type")
        if update_type == "invoice_paid":
            payload = body.get("payload", {})
            gateway_payment_id = str(payload.get("invoice_id"))
            
            # Find payment
            stmt = select(Payment).where(Payment.gateway_payment_id == gateway_payment_id)
            result = await db.execute(stmt)
            payment = result.scalars().first()
            
            if payment and payment.status == PaymentStatus.PENDING:
                await PaymentService.complete_payment(db, payment)
                logger.info(f"CryptoBot payment {payment.id} completed via webhook.")
                
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error in CryptoBot webhook: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid request")

@router.get("/payment/success", response_class=HTMLResponse)
async def payment_success_page(id: str, db: AsyncSession = Depends(get_db)):
    """
    Redirect or simple HTML page showing successful payment.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Success</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; text-align: center; max-width: 400px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3); border: 1px solid #334155; }
            .icon { font-size: 4rem; color: #10b981; margin-bottom: 1rem; }
            h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
            p { color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem; }
            .btn { display: inline-block; background: #3b82f6; color: white; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: 500; transition: background 0.2s; }
            .btn:hover { background: #2563eb; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✓</div>
            <h1>Оплата прошла успешно!</h1>
            <p>Ваш платеж обработан. Вернитесь в Telegram-бот и нажмите кнопку «Проверить оплату» для получения настроек VPN.</p>
            <a href="https://t.me/share/url?url=vpn" class="btn">Вернуться в Telegram</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.get("/payment/fail", response_class=HTMLResponse)
async def payment_fail_page(id: str, db: AsyncSession = Depends(get_db)):
    """
    Redirect or simple HTML page showing failed/cancelled payment.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Payment Failed</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; text-align: center; max-width: 400px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.3); border: 1px solid #334155; }
            .icon { font-size: 4rem; color: #f43f5e; margin-bottom: 1rem; }
            h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
            p { color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem; }
            .btn { display: inline-block; background: #3b82f6; color: white; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: 500; transition: background 0.2s; }
            .btn:hover { background: #2563eb; }
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon">✗</div>
            <h1>Оплата не удалась</h1>
            <p>Произошла ошибка при обработке платежа или оплата была отменена. Попробуйте еще раз в Telegram-боте.</p>
            <a href="https://t.me/mrzkyvpn_bot/" class="btn">Вернуться в Telegram</a>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/sandbox/pay", response_class=HTMLResponse)
async def sandbox_payment_page(id: str, db: AsyncSession = Depends(get_db)):
    """
    Interactive Sandbox payment simulation page for developer testing.
    """
    payment = await db.get(Payment, id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
        
    amount_rub = payment.amount_kopeks / 100.0
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Mrzky VPN Sandbox Payment</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
            .card {{ background: #1e293b; padding: 2.5rem; border-radius: 1rem; text-align: center; max-width: 400px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); border: 1px solid #334155; }}
            .badge {{ display: inline-block; background: #f59e0b; color: #1e293b; padding: 0.25rem 0.75rem; border-radius: 9999px; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 1rem; }}
            h1 {{ font-size: 1.5rem; margin-bottom: 0.5rem; }}
            .price {{ font-size: 2.5rem; font-weight: 700; color: #3b82f6; margin: 1rem 0; }}
            p {{ color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem; }}
            .btn {{ display: inline-block; background: #10b981; color: white; padding: 0.75rem 1.5rem; border-radius: 0.5rem; text-decoration: none; font-weight: 500; border: none; font-size: 1rem; cursor: pointer; width: 100%; transition: background 0.2s; }}
            .btn:hover {{ background: #059669; }}
        </style>
    </head>
    <body>
        <div class="card">
            <span class="badge">Тестовый режим</span>
            <h1>Имитация оплаты подписки</h1>
            <p>Вы собираетесь совершить тестовую оплату в демонстрационном режиме Sandbox.</p>
            <div class="price">{amount_rub:.2f} ₽</div>
            <form action="/sandbox/complete" method="POST">
                <input type="hidden" name="payment_id" value="{id}">
                <button type="submit" class="btn">Подтвердить оплату</button>
            </form>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.post("/sandbox/complete")
async def sandbox_complete(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Processes simulated success for sandbox payment.
    """
    form_data = await request.form()
    payment_id = form_data.get("payment_id")
    
    payment = await db.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
        
    if payment.status == PaymentStatus.PENDING:
        await PaymentService.complete_payment(db, payment)
        logger.info(f"Sandbox payment {payment.id} completed successfully.")
        
    return RedirectResponse(url=f"/payment/success?id={payment_id}", status_code=303)


@router.post("/webhook/rollypay")
async def rollypay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Webhook handler for RollyPay payment events.
    """
    try:
        # Get raw body for signature verification
        raw_body = await request.body()
        
        # Verify signature
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        
        if not signature or not timestamp:
            logger.warning("RollyPay webhook missing signature or timestamp headers.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing signature headers")
            
        if settings.ROLLYPAY_SIGNING_SECRET and not settings.ROLLYPAY_SIGNING_SECRET.startswith("rpk_test_signing_secret_placeholder"):
            # Compute expected signature
            payload = f"{timestamp}.".encode("utf-8") + raw_body
            expected_sig = hmac.new(
                settings.ROLLYPAY_SIGNING_SECRET.encode("utf-8"),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_sig, signature):
                logger.warning("RollyPay webhook signature verification failed.")
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

        body = json.loads(raw_body.decode("utf-8"))
        logger.info(f"RollyPay webhook received: {body}")
        
        payment_status = str(body.get("status", "")).lower()
        if payment_status == "paid":
            order_id = body.get("order_id")
            
            # Find payment
            stmt = select(Payment).where(Payment.id == order_id)
            result = await db.execute(stmt)
            payment = result.scalars().first()
            
            if payment and payment.status == PaymentStatus.PENDING:
                await PaymentService.complete_payment(db, payment)
                logger.info(f"RollyPay payment {payment.id} completed via webhook.")
                
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in RollyPay webhook: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid request")

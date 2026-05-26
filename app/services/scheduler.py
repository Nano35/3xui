import asyncio
import logging
from typing import Optional
from datetime import datetime
from aiogram import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import Subscription, SubscriptionStatus, Server
from app.services.xui_service import sync_all_client_traffic, disable_vpn_client

logger = logging.getLogger(__name__)

class VPNBackgroundScheduler:
    def __init__(self, bot: Optional[Bot] = None):
        self.bot = bot
        self._running = False
        self._task = None

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run())
            logger.info("VPN Background Scheduler started.")

    async def stop(self):
        if self._running:
            self._running = False
            if self._task:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            logger.info("VPN Background Scheduler stopped.")

    async def _run(self):
        while self._running:
            try:
                # 1. Sync traffic usage from 3x-ui panel, check expiration and handle auto-renewal
                logger.info("Starting traffic sync and expiration check with 3x-ui...")
                await sync_all_client_traffic(bot=self.bot)
                logger.info("Traffic sync and expiration check complete.")
                
            except Exception as e:
                logger.error(f"Error in background scheduler loop: {e}", exc_info=True)
                
            # Sleep interval (default to 1 hour / 3600 seconds)
            await asyncio.sleep(settings.SYNC_INTERVAL_SECONDS)

    async def check_subscriptions(self):
        async with async_session() as session:
            # Fetch active subscriptions
            stmt = select(Subscription).where(Subscription.status == SubscriptionStatus.ACTIVE)
            result = await session.execute(stmt)
            active_subs = result.scalars().all()
            
            now = datetime.utcnow()
            
            for sub in active_subs:
                expired = False
                reason = ""
                
                # Check date expiry
                if sub.expires_at and sub.expires_at < now:
                    expired = True
                    reason = "expired"
                    
                # Check traffic limit (if limit > 0)
                elif sub.traffic_limit_bytes > 0 and sub.total_used_bytes >= sub.traffic_limit_bytes:
                    expired = True
                    reason = "traffic_limit_exceeded"
                    
                if expired:
                    logger.info(f"Subscription {sub.sub_id} is disabled due to {reason}.")
                    
                    # Get server settings to disable client
                    server = await session.get(Server, sub.server_id)
                    if server:
                        try:
                            # Disable in 3x-ui
                            success = await disable_vpn_client(
                                server=server,
                                inbound_id=sub.inbound_id,
                                client_uuid=sub.client_uuid,
                                email=sub.client_email
                            )
                            
                            if success:
                                # Update database status
                                sub.status = (
                                    SubscriptionStatus.EXPIRED if reason == "expired"
                                    else SubscriptionStatus.SUSPENDED
                                )
                                session.add(sub)
                                await session.commit()
                                
                                # Notify user via Telegram Bot
                                if self.bot:
                                    try:
                                        lang = "ru" # default or fetch user lang
                                        # Let's get user language
                                        from app.models import User
                                        user = await session.get(User, sub.user_id)
                                        if user:
                                            lang = user.language or "ru"
                                            
                                        if reason == "expired":
                                            text = (
                                                f"⚠️ <b>Ваша подписка {sub.sub_id} истекла!</b>\n\n"
                                                "Доступ к VPN приостановлен. Пожалуйста, продлите подписку в меню «Личный кабинет»."
                                                if lang == "ru" else
                                                f"⚠️ <b>Your subscription {sub.sub_id} has expired!</b>\n\n"
                                                "VPN access suspended. Please renew your subscription in the 'Profile' menu."
                                            )
                                        else:
                                            text = (
                                                f"⚠️ <b>Лимит трафика на подписке {sub.sub_id} исчерпан!</b>\n\n"
                                                "Доступ к VPN приостановлен. Пожалуйста, перейдите в личный кабинет для смены тарифа или продления."
                                                if lang == "ru" else
                                                f"⚠️ <b>Traffic limit for subscription {sub.sub_id} has been reached!</b>\n\n"
                                                "VPN access suspended. Please visit your profile to upgrade or renew."
                                            )
                                        await self.bot.send_message(chat_id=sub.user_id, text=text, parse_mode="HTML")
                                    except Exception as bot_err:
                                        logger.error(f"Failed to send expiry notification to user {sub.user_id}: {bot_err}")
                        except Exception as xui_err:
                            logger.error(f"Failed to disable client {sub.client_email} on panel: {xui_err}")

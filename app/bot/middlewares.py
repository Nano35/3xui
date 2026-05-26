import uuid
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import User

logger = logging.getLogger(__name__)

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with self.session_pool() as session:
            data["db_session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                logger.error(f"Middleware transaction rollback due to error: {e}", exc_info=True)
                raise

class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        telegram_user = data.get("event_from_user")
        if not telegram_user:
            return await handler(event, data)

        db_session: AsyncSession = data["db_session"]
        
        # Fetch user
        user = await db_session.get(User, telegram_user.id)
        
        # Flag to indicate if this is a newly registered user via referral
        data["is_new_referred_user"] = False
        
        if not user:
            # Generate a unique referral code
            ref_code = str(uuid.uuid4())[:8]
            
            # Check for deep linking parameter in /start
            referred_by_id = None
            msg = None
            if isinstance(event, Message):
                msg = event
            elif hasattr(event, "message") and isinstance(event.message, Message):
                msg = event.message

            if msg and msg.text and msg.text.startswith("/start "):
                parts = msg.text.split()
                if len(parts) > 1:
                    ref_param = parts[1]
                    # Find user who owns this referral code
                    ref_query = await db_session.execute(
                        select(User).where(User.referral_code == ref_param)
                    )
                    referrer = ref_query.scalars().first()
                    # User cannot refer themselves
                    if referrer and referrer.id != telegram_user.id:
                        referred_by_id = referrer.id
                        data["is_new_referred_user"] = True
                        logger.info(f"User {telegram_user.id} registered via referral from {referrer.id}")
            
            user = User(
                id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
                language=telegram_user.language_code if telegram_user.language_code in ["ru", "en"] else "ru",
                referral_code=ref_code,
                referred_by_id=referred_by_id
            )
            db_session.add(user)
            await db_session.flush() # Sync ID
            
        else:
            # Check if this user was imported and is entering the bot for the first time
            if user.first_name is None:
                # Update their unlimited subscriptions to 7 days
                from app.models import Subscription, SubscriptionStatus, Server
                from app.services.xui_service import update_vpn_client
                from datetime import datetime, timedelta
                
                try:
                    subs_query = await db_session.execute(
                        select(Subscription).where(
                            Subscription.user_id == user.id,
                            Subscription.status != SubscriptionStatus.DELETED
                        )
                    )
                    subs = subs_query.scalars().all()
                    for sub in subs:
                        if sub.expires_at is None:
                            sub.expires_at = datetime.utcnow() + timedelta(days=7)
                            db_session.add(sub)
                            
                            server = await db_session.get(Server, sub.server_id)
                            if server:
                                try:
                                    await update_vpn_client(
                                        server=server,
                                        inbound_id=sub.inbound_id,
                                        client_uuid=sub.client_uuid,
                                        email=sub.client_email,
                                        enable=sub.status == SubscriptionStatus.ACTIVE,
                                        expires_at=sub.expires_at,
                                        traffic_limit_bytes=sub.traffic_limit_bytes
                                    )
                                    logger.info(f"Automatically converted unlimited subscription {sub.sub_id} to 7 days for user {user.id} upon first bot entry.")
                                except Exception as e:
                                    logger.error(f"Failed to sync newly set 7-day expiry to 3x-ui panel for sub {sub.sub_id}: {e}")
                except Exception as e:
                    logger.error(f"Error checking/converting unlimited subscriptions for user {user.id}: {e}", exc_info=True)
            
            # Keep usernames and names up to date
            updated = False
            if user.username != telegram_user.username:
                user.username = telegram_user.username
                updated = True
            if user.first_name != telegram_user.first_name:
                user.first_name = telegram_user.first_name
                updated = True
            if user.last_name != telegram_user.last_name:
                user.last_name = telegram_user.last_name
                updated = True
            if updated:
                db_session.add(user)
                
        data["user"] = user
        return await handler(event, data)

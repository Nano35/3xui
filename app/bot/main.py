import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Server, TariffPlan
from app.bot.middlewares import DbSessionMiddleware, UserMiddleware
from app.bot.handlers import start, support, profile, shop, admin

logger = logging.getLogger(__name__)

async def init_default_data():
    """Populates the database with default server and tariffs if empty."""
    async with async_session() as session:
        # Check if servers table is empty
        servers_query = await session.execute(select(Server))
        first_server = servers_query.scalars().first()
        
        from urllib.parse import urlparse
        parsed = urlparse(settings.XUI_API_URL)
        token = settings.XUI_API_KEY or f"{settings.XUI_USERNAME}:{settings.XUI_PASSWORD}"
        
        if not first_server:
            default_server = Server(
                name="Primary VPN Server",
                host=parsed.hostname or "heklet.duckdns.org",
                port=parsed.port or 443,
                base_path=parsed.path or "/",
                api_token=token,
                is_enabled=True,
                status="UNKNOWN"
            )
            session.add(default_server)
            logger.info("Added default Server using .env panel settings.")
        else:
            # Sync existing primary server details with .env if they differ
            updated = False
            expected_host = parsed.hostname or "heklet.duckdns.org"
            expected_port = parsed.port or 443
            expected_path = parsed.path or "/"
            
            if first_server.host != expected_host:
                first_server.host = expected_host
                updated = True
            if first_server.port != expected_port:
                first_server.port = expected_port
                updated = True
            if first_server.base_path != expected_path:
                first_server.base_path = expected_path
                updated = True
            if first_server.api_token != token:
                first_server.api_token = token
                updated = True
                
            if updated:
                session.add(first_server)
                logger.info("Updated existing primary Server config from .env settings.")
            
        # Check if tariff plans table is empty
        tariffs_query = await session.execute(select(TariffPlan))
        if not tariffs_query.scalars().first():
            tariffs = [
                TariffPlan(
                    name_ru="Тестовый (3 дня)",
                    name_en="Test Plan (3 Days)",
                    duration_days=3,
                    traffic_limit_gb=10,
                    price_kopeks=0,
                    is_enabled=True
                ),
                TariffPlan(
                    name_ru="Стандартный (30 дней)",
                    name_en="Standard (30 Days)",
                    duration_days=30,
                    traffic_limit_gb=100,
                    price_kopeks=15000, # 150.00 RUB
                    is_enabled=True
                ),
                TariffPlan(
                    name_ru="Премиум (90 дней)",
                    name_en="Premium (90 Days)",
                    duration_days=90,
                    traffic_limit_gb=300,
                    price_kopeks=35000, # 350.00 RUB
                    is_enabled=True
                ),
                TariffPlan(
                    name_ru="Безлимитный (30 дней)",
                    name_en="Unlimited (30 Days)",
                    duration_days=30,
                    traffic_limit_gb=0,
                    price_kopeks=25000, # 250.00 RUB
                    is_enabled=True
                )
            ]
            session.add_all(tariffs)
            logger.info("Added default Tariff Plans.")
            
        await session.commit()

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Run default database seeding
    await init_default_data()

    # Initialize bot
    bot = Bot(token=settings.BOT_TOKEN)
    
    # Initialize storage
    storage = MemoryStorage()
    if settings.REDIS_URL:
        try:
            redis = Redis.from_url(settings.REDIS_URL)
            # Ping redis to check if online
            await redis.ping()
            storage = RedisStorage(redis=redis)
            logger.info("Using Redis FSM storage.")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}. Falling back to MemoryStorage.")

    dp = Dispatcher(storage=storage)

    # Register middlewares
    dp.update.outer_middleware(DbSessionMiddleware(async_session))
    dp.update.middleware(UserMiddleware())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(support.router)
    dp.include_router(profile.router)
    dp.include_router(shop.router)
    dp.include_router(admin.router)

    # Skip updates on start
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Initialize background scheduler
    from app.services.scheduler import VPNBackgroundScheduler
    scheduler = VPNBackgroundScheduler(bot=bot)
    scheduler.start()
    
    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await scheduler.stop()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())

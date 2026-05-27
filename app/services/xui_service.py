import logging
import json
import time
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Server, Subscription, SubscriptionStatus
from app.services.xui_client import XuiClient, XuiClientError
from app.config import settings

logger = logging.getLogger(__name__)

def format_datetime_msk(dt: Optional[datetime], lang: str = "ru") -> str:
    """
    Formats a naive UTC datetime to Moscow (UTC+3) time.
    """
    if not dt:
        return "Безлимит" if lang == "ru" else "Unlimited"
    local_dt = dt + timedelta(hours=3)
    return local_dt.strftime("%d.%m.%Y %H:%M")

def get_client_for_server(server: Server) -> XuiClient:
    """
    Creates an XuiClient instance from a Server database model.
    """
    # Parse the server host to get a clean API base URL
    # If the server host doesn't start with http/https, build it from host and port
    host_str = server.host
    if not (host_str.startswith("http://") or host_str.startswith("https://")):
        # Check base_path prefix
        bp = server.base_path.strip("/")
        bp_suffix = f"/{bp}" if bp else ""
        base_url = f"https://{host_str}:{server.port}{bp_suffix}"
    else:
        base_url = host_str
        
    # We support api_key or basic_auth depending on token prefix
    # If the token contains a colon (username:password), it is basic_auth
    if ":" in server.api_token:
        username, password = server.api_token.split(":", 1)
        return XuiClient(
            base_url=base_url,
            auth_type="basic_auth",
            username=username,
            password=password
        )
    else:
        return XuiClient(
            base_url=base_url,
            auth_type="api_key",
            api_key=server.api_token
        )

async def sync_server_status(server: Server, db_session: AsyncSession) -> bool:
    """
    Tests connection to the server and updates its status in the database.
    """
    async with get_client_for_server(server) as client:
        try:
            await client.get_system_stats()
            server.status = "ONLINE"
            is_online = True
        except Exception as e:
            logger.error(f"Server {server.name} status check failed: {e}")
            server.status = "OFFLINE"
            is_online = False
            
        db_session.add(server)
        await db_session.commit()
        return is_online

# Cache to store inbound details to avoid hitting 3x-ui API on every VLESS link generation
# Key: (server_id, inbound_id), Value: (expiry_timestamp, inbound_dict)
_inbound_cache = {}
INBOUND_CACHE_TTL = 3600  # Cache for 1 hour

def clear_inbound_cache(server_id: int):
    """Clears cached inbound settings for a specific server."""
    keys_to_remove = [k for k in _inbound_cache.keys() if k[0] == server_id]
    for k in keys_to_remove:
        _inbound_cache.pop(k, None)

def clear_all_inbound_cache():
    """Clears cached inbound settings for all servers."""
    _inbound_cache.clear()

def generate_subscription_link(server: Server, sub_id: str) -> str:
    """
    Generates the 3x-ui subscription link for a given server and sub_id.
    """
    if server.subscription_url_template:
        template = server.subscription_url_template.strip()
        if "{sub_id}" in template:
            return template.format(sub_id=sub_id)
        if template.endswith("/sub") or template.endswith("/sub/"):
            return f"{template.rstrip('/')}/{sub_id}"
        else:
            return f"{template.rstrip('/')}/sub/{sub_id}"

    host_str = server.host
    if not (host_str.startswith("http://") or host_str.startswith("https://")):
        bp = server.base_path.strip("/") if server.base_path else ""
        bp_suffix = f"/{bp}" if bp else ""
        base_url = f"https://{host_str}:{server.port}{bp_suffix}"
    else:
        base_url = host_str.rstrip("/")
        
    return f"{base_url}/sub/{sub_id}"

async def generate_vless_link(server: Server, inbound_id: int, client_uuid: str, client_email: str) -> str:
    """
    Fetches the client links from the 3x-ui server, and returns them.
    If multiple links exist, they are returned separated by newlines.
    Falls back to generating a single link manually if getLinks fails.
    """
    try:
        async with get_client_for_server(server) as client:
            links = await client.get_client_links(client_email)
            if links:
                return "\n".join(links)
    except Exception as e:
        logger.warning(f"Failed to fetch client links from panel API for {client_email}: {e}")

    now = time.time()
    cache_key = (server.id, inbound_id)
    inbound = None
    
    # Check cache first
    if cache_key in _inbound_cache:
        expiry, cached_inbound = _inbound_cache[cache_key]
        if now < expiry:
            inbound = cached_inbound
            
    if not inbound:
        try:
            async with get_client_for_server(server) as client:
                if client.client:
                    client.client.timeout = httpx.Timeout(3.0)
                inbound = await client.get_inbound(inbound_id)
                if inbound:
                    _inbound_cache[cache_key] = (now + INBOUND_CACHE_TTL, inbound)
        except Exception as e:
            logger.error(f"Failed to fetch inbound {inbound_id} from server {server.name} for link generation: {e}")
            if cache_key in _inbound_cache:
                _, inbound = _inbound_cache[cache_key]
                logger.info(f"Using expired cache for inbound {inbound_id} due to network error")

    if not inbound:
        raise ValueError(f"Inbound ID {inbound_id} not reachable on server {server.name}")
        
    port = inbound.get("port", 443)
    protocol = inbound.get("protocol", "vless")
    
    try:
        stream_settings = json.loads(inbound.get("streamSettings", "{}"))
    except Exception:
        stream_settings = {}
        
    try:
        inbound_settings = json.loads(inbound.get("settings", "{}"))
    except Exception:
        inbound_settings = {}
        
    clients = inbound_settings.get("clients", [])
    target_client = next((c for c in clients if c.get("email") == client_email), None)
    flow = target_client.get("flow", "") if target_client else ""
    
    network = stream_settings.get("network", "tcp")
    security = stream_settings.get("security", "none")
    
    if server.host.startswith("http://") or server.host.startswith("https://"):
        parsed = urlparse(server.host)
        host = parsed.hostname
    else:
        host = server.host
        
    remark = client_email
    
    if protocol == "vless" and security == "reality":
        reality_settings = stream_settings.get("realitySettings", {})
        pbk = reality_settings.get("settings", {}).get("publicKey", "")
        
        server_names = reality_settings.get("serverNames", [])
        sni = server_names[0] if server_names else ""
        
        short_ids = reality_settings.get("shortIds", [])
        sid = short_ids[0] if short_ids else ""
        
        if not flow:
            flow = "xtls-rprx-vision"
            
        link = (
            f"vless://{client_uuid}@{host}:{port}?"
            f"type={network}&"
            f"security=reality&"
            f"pbk={pbk}&"
            f"fp=chrome&"
            f"sni={sni}&"
            f"sid={sid}&"
            f"flow={flow}"
            f"#{remark}"
        )
        return link
    else:
        link = f"{protocol}://{client_uuid}@{host}:{port}?type={network}&security={security}#{remark}"
        return link

async def create_vpn_client(
    server: Server,
    inbound_id: int,
    email: str,
    uuid_str: str,
    expires_at: datetime,
    traffic_limit_bytes: int = 0,
    flow: str = "xtls-rprx-vision",
    limit_ip: int = None
) -> str:
    """
    Creates a new client in 3x-ui and returns their config link.
    Binds the client to all active inbounds on the server.
    """
    if limit_ip is None:
        limit_ip = settings.XUI_LIMIT_IP
        
    expiry_time_ms = int(expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if expires_at else 0
    
    tg_id = 0
    sub_id = None
    if email.startswith("usr_"):
        try:
            parts = email.split("_")
            tg_id = int(parts[1])
            sub_id = email.split("_sub_")[-1]
        except Exception:
            pass

    async with get_client_for_server(server) as client:
        # Fetch all active inbounds on this server to bind to
        inbounds = []
        try:
            inbounds = await client.get_inbounds()
            active_inbound_ids = [ib["id"] for ib in inbounds if ib.get("enable", True)]
        except Exception as e:
            logger.warning(f"Failed to fetch active inbounds on server {server.name}: {e}")
            active_inbound_ids = []
            
        if not active_inbound_ids:
            active_inbound_ids = [inbound_id]

        # Check if client already exists
        existing = await client.get_client(inbound_id, email)
        if existing:
            logger.warning(f"Client {email} already exists. Updating instead.")
            await client.update_client(
                inbound_id=inbound_id,
                client_uuid=uuid_str,
                email=email,
                limit_ip=limit_ip,
                total_gb=traffic_limit_bytes,
                expiry_time=expiry_time_ms,
                enable=True,
                flow=flow,
                tg_id=tg_id,
                sub_id=sub_id
            )
        else:
            try:
                await client.add_client(
                    inbound_ids=active_inbound_ids,
                    email=email,
                    client_uuid=uuid_str,
                    limit_ip=limit_ip,
                    total_gb=traffic_limit_bytes,
                    expiry_time=expiry_time_ms,
                    flow=flow,
                    tg_id=tg_id,
                    sub_id=sub_id
                )
            except Exception as e:
                logger.warning(f"Failed to add client to all active inbounds ({active_inbound_ids}) on server {server.name}: {e}. Retrying with local inbounds only.")
                local_inbound_ids = [
                    ib["id"] for ib in inbounds 
                    if ib.get("enable", True) and (ib.get("nodeId") is None or ib.get("nodeId") == 0)
                ]
                if not local_inbound_ids:
                    local_inbound_ids = [inbound_id]
                
                if local_inbound_ids != active_inbound_ids:
                    await client.add_client(
                        inbound_ids=local_inbound_ids,
                        email=email,
                        client_uuid=uuid_str,
                        limit_ip=limit_ip,
                        total_gb=traffic_limit_bytes,
                        expiry_time=expiry_time_ms,
                        flow=flow,
                        tg_id=tg_id,
                        sub_id=sub_id
                    )
                else:
                    raise e
            
    return generate_subscription_link(server, sub_id or uuid_str)

async def update_vpn_client(
    server: Server,
    inbound_id: int,
    client_uuid: str,
    email: str,
    enable: bool,
    expires_at: datetime,
    traffic_limit_bytes: int = 0,
    flow: str = "xtls-rprx-vision",
    limit_ip: int = None
) -> None:
    """
    Updates client parameters on the 3x-ui panel.
    """
    if limit_ip is None:
        limit_ip = settings.XUI_LIMIT_IP
        
    expiry_time_ms = int(expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if expires_at else 0
    
    tg_id = 0
    sub_id = None
    if email.startswith("usr_"):
        try:
            parts = email.split("_")
            tg_id = int(parts[1])
            sub_id = email.split("_sub_")[-1]
        except Exception:
            pass

    async with get_client_for_server(server) as client:
        await client.update_client(
            inbound_id=inbound_id,
            client_uuid=client_uuid,
            email=email,
            limit_ip=limit_ip,
            total_gb=traffic_limit_bytes,
            expiry_time=expiry_time_ms,
            enable=enable,
            flow=flow,
            tg_id=tg_id,
            sub_id=sub_id
        )

async def delete_vpn_client(server: Server, inbound_id: int, client_uuid: str, client_email: Optional[str] = None) -> None:
    """
    Deletes client from the 3x-ui panel.
    """
    email_or_uuid = client_email or client_uuid
    async with get_client_for_server(server) as client:
        try:
            await client.delete_client(inbound_id, email_or_uuid)
        except XuiClientError as e:
            if e.status_code == 404:
                logger.warning(f"Client {email_or_uuid} not found during delete on server {server.name}")
            else:
                raise

async def sync_traffic_and_expiry(db_session: AsyncSession, bot = None) -> dict:
    """
    Iterates over all non-deleted subscriptions, fetches current traffic usage
    and expiration details from their respective servers, updates the database,
    and deactivates/expires subscriptions that exceed limits or date.
    Optimized to fetch all clients in a single API call per server.
    """
    # Fetch all subscriptions that are not deleted
    result = await db_session.execute(
        select(Subscription).where(Subscription.status != SubscriptionStatus.DELETED)
    )
    subscriptions = result.scalars().all()
    
    # Group subscriptions by server to minimize connection overhead
    server_subs = {}
    for sub in subscriptions:
        server_subs.setdefault(sub.server_id, []).append(sub)
        
    stats = {"processed": 0, "expired": 0, "limited": 0, "errors": 0}
    
    for server_id, subs in server_subs.items():
        # Fetch the server
        server = await db_session.get(Server, server_id)
        if not server or not server.is_enabled:
            continue
            
        async with get_client_for_server(server) as client:
            try:
                # Fetch all clients on the server in a single call
                all_clients = await client.get_all_clients()
                client_map = {c["email"]: c for c in all_clients}
            except Exception as e:
                logger.error(f"Failed to fetch clients from server {server.name}: {e}")
                stats["errors"] += len(subs)
                continue

            for sub in subs:
                stats["processed"] += 1
                try:
                    c_data = client_map.get(sub.client_email)
                    if not c_data:
                        logger.warning(f"Subscription client {sub.client_email} not found on server {server.name}")
                        continue
                        
                    # Update traffic in DB
                    sub.up_used_bytes = c_data.get("up", 0)
                    sub.down_used_bytes = c_data.get("down", 0)
                    sub.total_used_bytes = sub.up_used_bytes + sub.down_used_bytes
                    
                    # Update settings and status from 3x-ui to allow changes made in 3x-ui to reflect in the bot
                    expiry_time_ms = c_data.get("expiryTime", 0)
                    if expiry_time_ms > 0:
                        sub.expires_at = datetime.utcfromtimestamp(expiry_time_ms / 1000.0)
                    else:
                        sub.expires_at = None
                        
                    sub.traffic_limit_bytes = c_data.get("totalGB", 0)
                    
                    enabled = c_data.get("enable", True)
                    if not enabled:
                        if sub.status == SubscriptionStatus.ACTIVE:
                            sub.status = SubscriptionStatus.SUSPENDED
                    else:
                        if sub.status in (SubscriptionStatus.SUSPENDED, SubscriptionStatus.EXPIRED):
                            now = datetime.utcnow()
                            is_expired = sub.expires_at and sub.expires_at < now
                            is_limited = sub.traffic_limit_bytes > 0 and sub.total_used_bytes >= sub.traffic_limit_bytes
                            if not is_expired and not is_limited:
                                sub.status = SubscriptionStatus.ACTIVE
                                    
                    # Check expiry
                    now = datetime.utcnow()
                    is_expired = False
                    if sub.expires_at and sub.expires_at < now:
                        is_expired = True
                        
                    # Check traffic limit
                    is_limited = False
                    if sub.traffic_limit_bytes > 0 and sub.total_used_bytes >= sub.traffic_limit_bytes:
                        is_limited = True
                        
                    # Attempt Auto-Renewal if needed and possible
                    auto_renewed = False
                    if (is_expired or is_limited) and sub.auto_renew:
                        from app.models import TariffPlan, User, Payment, PaymentStatus, PaymentGateway
                        from datetime import timedelta
                        tariff = await db_session.get(TariffPlan, sub.tariff_id)
                        user = await db_session.get(User, sub.user_id)
                        
                        if tariff and tariff.price_kopeks > 0 and user:
                            if user.balance_kopeks >= tariff.price_kopeks:
                                # Deduct balance
                                user.balance_kopeks -= tariff.price_kopeks
                                db_session.add(user)
                                
                                # Calculate new expiration
                                new_expires = (sub.expires_at if sub.expires_at and sub.expires_at > now else now) + timedelta(days=tariff.duration_days)
                                sub.expires_at = new_expires
                                sub.status = SubscriptionStatus.ACTIVE
                                sub.total_used_bytes = 0
                                sub.up_used_bytes = 0
                                sub.down_used_bytes = 0
                                db_session.add(sub)
                                
                                # Create payment record
                                import uuid
                                payment_id = f"auto_{uuid.uuid4().hex[:12]}"
                                payment = Payment(
                                    id=payment_id,
                                    user_id=user.id,
                                    amount_kopeks=tariff.price_kopeks,
                                    currency="RUB",
                                    gateway=PaymentGateway.BALANCE,
                                    gateway_payment_id=payment_id,
                                    status=PaymentStatus.COMPLETED,
                                    payload=json.dumps({
                                        "renew_days": tariff.duration_days,
                                        "subscription_id": sub.sub_id,
                                        "auto_renew": True
                                    })
                                )
                                db_session.add(payment)
                                
                                # Reset traffic on panel
                                try:
                                    await client.reset_client_traffic(sub.inbound_id, sub.client_email)
                                except Exception as reset_err:
                                    logger.error(f"Failed to reset client traffic on panel for sub {sub.sub_id}: {reset_err}")
                                    
                                # Parse tg_id and sub_id for panel updates
                                tg_id = 0
                                sub_id = None
                                if sub.client_email.startswith("usr_"):
                                    try:
                                        parts = sub.client_email.split("_")
                                        tg_id = int(parts[1])
                                        sub_id = sub.client_email.split("_sub_")[-1]
                                    except Exception:
                                        pass

                                # Enable and update expiry on panel
                                await client.update_client(
                                    inbound_id=sub.inbound_id,
                                    client_uuid=sub.client_uuid,
                                    email=sub.client_email,
                                    limit_ip=settings.XUI_LIMIT_IP,
                                    total_gb=sub.traffic_limit_bytes,
                                    expiry_time=int(sub.expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if sub.expires_at else 0,
                                    enable=True,
                                    tg_id=tg_id,
                                    sub_id=sub_id
                                )
                                
                                auto_renewed = True
                                is_expired = False
                                is_limited = False
                                
                                # Notify user
                                if bot:
                                    try:
                                        lang = user.language or "ru"
                                        text = (
                                            f"🔄 <b>Автопродление подписки {sub.sub_id} успешно выполнено!</b>\n\n"
                                            f"Списано с баланса: <b>{tariff.price_kopeks / 100:.2f} руб.</b>\n"
                                            f"Новый срок действия: <b>{format_datetime_msk(sub.expires_at, lang)}</b>"
                                            if lang == "ru" else
                                            f"🔄 <b>Subscription {sub.sub_id} has been auto-renewed successfully!</b>\n\n"
                                            f"Deducted from balance: <b>{tariff.price_kopeks / 100:.2f} RUB</b>\n"
                                            f"New expiry: <b>{format_datetime_msk(sub.expires_at, lang)}</b>"
                                        )
                                        await bot.send_message(chat_id=user.id, text=text, parse_mode="HTML")
                                    except Exception as bot_err:
                                        logger.error(f"Failed to send auto-renewal notification to user {user.id}: {bot_err}")
                            else:
                                # Not enough balance, notify user about failed auto-renewal
                                if bot:
                                    try:
                                        lang = user.language or "ru"
                                        text = (
                                            f"⚠️ <b>Ошибка автопродления подписки {sub.sub_id}!</b>\n\n"
                                            f"Недостаточно средств на балансе для продления.\n"
                                            f"Требуется: <b>{tariff.price_kopeks / 100:.2f} руб.</b>\n"
                                            f"Ваш баланс: <b>{user.balance_kopeks / 100:.2f} руб.</b>\n\n"
                                            f"Пожалуйста, пополните баланс."
                                            if lang == "ru" else
                                            f"⚠️ <b>Subscription {sub.sub_id} auto-renewal failed!</b>\n\n"
                                            f"Insufficient funds.\n"
                                            f"Required: <b>{tariff.price_kopeks / 100:.2f} RUB</b>\n"
                                            f"Your balance: <b>{user.balance_kopeks / 100:.2f} RUB</b>\n\n"
                                            f"Please top up your balance."
                                        )
                                        await bot.send_message(chat_id=user.id, text=text, parse_mode="HTML")
                                    except Exception as bot_err:
                                        logger.error(f"Failed to send auto-renewal failure notification to user {user.id}: {bot_err}")
                         
                    # Update status if still expired/limited
                    if is_expired:
                        if sub.status != SubscriptionStatus.EXPIRED:
                            sub.status = SubscriptionStatus.EXPIRED
                            
                            # Parse tg_id and sub_id for panel updates
                            tg_id = 0
                            sub_id = None
                            if sub.client_email.startswith("usr_"):
                                try:
                                    parts = sub.client_email.split("_")
                                    tg_id = int(parts[1])
                                    sub_id = sub.client_email.split("_sub_")[-1]
                                except Exception:
                                    pass

                            # Disable in panel
                            await client.update_client(
                                inbound_id=sub.inbound_id,
                                client_uuid=sub.client_uuid,
                                email=sub.client_email,
                                limit_ip=settings.XUI_LIMIT_IP,
                                total_gb=sub.traffic_limit_bytes,
                                expiry_time=int(sub.expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if sub.expires_at else 0,
                                enable=False,
                                tg_id=tg_id,
                                sub_id=sub_id
                            )
                            stats["expired"] += 1
                            
                            # Notify user
                            if bot:
                                try:
                                    from app.models import User
                                    user = await db_session.get(User, sub.user_id)
                                    lang = user.language or "ru" if user else "ru"
                                    text = (
                                        f"⚠️ <b>Ваша подписка {sub.sub_id} истекла!</b>\n\n"
                                        "Доступ к VPN приостановлен. Пожалуйста, продлите подписку в меню «Личный кабинет»."
                                        if lang == "ru" else
                                        f"⚠️ <b>Your subscription {sub.sub_id} has expired!</b>\n\n"
                                        "VPN access suspended. Please renew your subscription in the 'Profile' menu."
                                    )
                                    await bot.send_message(chat_id=sub.user_id, text=text, parse_mode="HTML")
                                except Exception as bot_err:
                                    logger.error(f"Failed to send expiry notification to user {sub.user_id}: {bot_err}")
                                    
                    elif is_limited:
                        if sub.status != SubscriptionStatus.SUSPENDED:
                            sub.status = SubscriptionStatus.SUSPENDED
                            
                            # Parse tg_id and sub_id for panel updates
                            tg_id = 0
                            sub_id = None
                            if sub.client_email.startswith("usr_"):
                                try:
                                    parts = sub.client_email.split("_")
                                    tg_id = int(parts[1])
                                    sub_id = sub.client_email.split("_sub_")[-1]
                                except Exception:
                                    pass

                            # Disable in panel
                            await client.update_client(
                                inbound_id=sub.inbound_id,
                                client_uuid=sub.client_uuid,
                                email=sub.client_email,
                                limit_ip=settings.XUI_LIMIT_IP,
                                total_gb=sub.traffic_limit_bytes,
                                expiry_time=int(sub.expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if sub.expires_at else 0,
                                enable=False,
                                tg_id=tg_id,
                                sub_id=sub_id
                            )
                            stats["limited"] += 1
                            
                            # Notify user
                            if bot:
                                try:
                                    from app.models import User
                                    user = await db_session.get(User, sub.user_id)
                                    lang = user.language or "ru" if user else "ru"
                                    text = (
                                        f"⚠️ <b>Лимит трафика на подписке {sub.sub_id} исчерпан!</b>\n\n"
                                        "Доступ к VPN приостановлен. Пожалуйста, перейдите в личный кабинет для смены тарифа или продления."
                                        if lang == "ru" else
                                        f"⚠️ <b>Traffic limit for subscription {sub.sub_id} has been reached!</b>\n\n"
                                        "VPN access suspended. Please visit your profile to upgrade or renew."
                                    )
                                    await bot.send_message(chat_id=sub.user_id, text=text, parse_mode="HTML")
                                except Exception as bot_err:
                                    logger.error(f"Failed to send limit notification to user {sub.user_id}: {bot_err}")
                                    
                    else:
                        # Ensure active status and enable in panel if suspended or updated
                        if sub.status == SubscriptionStatus.SUSPENDED:
                            sub.status = SubscriptionStatus.ACTIVE
                            
                            # Parse tg_id and sub_id for panel updates
                            tg_id = 0
                            sub_id = None
                            if sub.client_email.startswith("usr_"):
                                try:
                                    parts = sub.client_email.split("_")
                                    tg_id = int(parts[1])
                                    sub_id = sub.client_email.split("_sub_")[-1]
                                except Exception:
                                    pass

                            await client.update_client(
                                inbound_id=sub.inbound_id,
                                client_uuid=sub.client_uuid,
                                email=sub.client_email,
                                limit_ip=settings.XUI_LIMIT_IP,
                                total_gb=sub.traffic_limit_bytes,
                                expiry_time=int(sub.expires_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if sub.expires_at else 0,
                                enable=True,
                                tg_id=tg_id,
                                sub_id=sub_id
                            )
                            
                    db_session.add(sub)
                except Exception as e:
                    logger.error(f"Failed to sync subscription {sub.client_email} on server {server.name}: {e}")
                    stats["errors"] += 1
                    
        await db_session.commit()
        
    return stats

async def sync_all_client_traffic(bot = None) -> dict:
    """Compatibility wrapper that runs sync_traffic_and_expiry using a local DB session."""
    from app.database import async_session
    async with async_session() as session:
        return await sync_traffic_and_expiry(session, bot=bot)

async def disable_vpn_client(server: Server, inbound_id: int, client_uuid: str, email: str) -> bool:
    """Compatibility wrapper that disables a VPN client in the 3x-ui panel."""
    try:
        await update_vpn_client(
            server=server,
            inbound_id=inbound_id,
            client_uuid=client_uuid,
            email=email,
            enable=False,
            expires_at=None
        )
        return True
    except Exception as e:
        logger.error(f"disable_vpn_client failed for {email}: {e}")
        return False

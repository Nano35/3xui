import logging
import uuid as uuid_lib
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, Subscription, SubscriptionStatus, Server, TariffPlan
from app.services.xui_service import get_client_for_server
from app.config import settings

logger = logging.getLogger(__name__)


async def preview_clients(server: Server) -> List[Dict[str, Any]]:
    """
    Fetches all clients from a 3x-ui server and returns them as a flat list
    with human-readable metadata for the admin preview UI.
    """
    async with get_client_for_server(server) as client:
        all_clients = await client.get_all_clients()
    
    result = []
    for c in all_clients:
        expiry_ts = c.get("expiryTime", 0)
        if expiry_ts and expiry_ts > 0:
            # 3x-ui stores expiry as ms timestamp
            expiry_dt = datetime.utcfromtimestamp(expiry_ts / 1000)
            expiry_str = expiry_dt.isoformat() + "Z"
        else:
            expiry_str = "Unlimited"
        
        total_bytes = c.get("totalGB", 0)  # despite the name, this is in bytes in modern 3x-ui
        used_bytes = c.get("up", 0) + c.get("down", 0)
        
        result.append({
            "email": c["email"],
            "uuid": c["uuid"],
            "tgId": c.get("tgId", ""),
            "enable": c.get("enable", True),
            "expiryTime": expiry_ts,
            "expires_at_str": expiry_str,
            "traffic_limit_bytes": total_bytes,
            "used_bytes": used_bytes,
            "traffic_limit_gb": round(total_bytes / (1024**3), 2) if total_bytes > 0 else 0,
            "used_gb": round(used_bytes / (1024**3), 2),
            "inbound_id": c["inbound_id"],
            "inbound_remark": c.get("inbound_remark", ""),
            "flow": c.get("flow", ""),
            "limitIp": c.get("limitIp", 0),
        })
    
    return result


async def import_clients(
    server: Server,
    db_session: AsyncSession,
    mappings: List[Dict[str, Any]],
    default_tariff_id: int
) -> Dict[str, Any]:
    """
    Imports clients from 3x-ui into the bot database.
    
    Each mapping dict should contain:
      - email: str (client email on 3x-ui)
      - telegram_id: int (Telegram user ID to bind to)
    
    The function:
      1. Creates User records if they don't exist
      2. Creates Subscription records linked to the user
      3. Updates tgId on the 3x-ui panel for the client
      4. Skips clients whose client_email already exists in subscriptions
    
    Returns a summary dict with counts of imported, skipped, and errored entries.
    """
    # Validate tariff exists
    tariff = await db_session.get(TariffPlan, default_tariff_id)
    if not tariff:
        return {"imported": 0, "skipped": 0, "errors": 1, "error_details": ["Default tariff not found"]}
    
    # Fetch all clients from the server for lookup
    async with get_client_for_server(server) as xui_client:
        all_clients = await xui_client.get_all_clients()
    
    # Build a lookup by email
    clients_by_email = {c["email"]: c for c in all_clients}
    
    stats = {"imported": 0, "skipped": 0, "errors": 0, "error_details": []}
    
    for mapping in mappings:
        email = mapping.get("email", "").strip()
        telegram_id = mapping.get("telegram_id")
        
        if not email or not telegram_id:
            stats["errors"] += 1
            stats["error_details"].append(f"Missing email or telegram_id for mapping: {mapping}")
            continue
        
        try:
            telegram_id = int(telegram_id)
        except (ValueError, TypeError):
            stats["errors"] += 1
            stats["error_details"].append(f"Invalid telegram_id '{telegram_id}' for {email}")
            continue
        
        # Check if this client email is already imported
        existing_sub = await db_session.execute(
            select(Subscription).where(Subscription.client_email == email)
        )
        if existing_sub.scalars().first():
            stats["skipped"] += 1
            continue
        
        # Look up client data from 3x-ui
        panel_client = clients_by_email.get(email)
        if not panel_client:
            stats["errors"] += 1
            stats["error_details"].append(f"Client '{email}' not found on 3x-ui server")
            continue
        
        try:
            # Ensure User exists
            user = await db_session.get(User, telegram_id)
            if not user:
                ref_code = str(uuid_lib.uuid4())[:8]
                user = User(
                    id=telegram_id,
                    username=None,
                    first_name=None,
                    last_name=None,
                    language="ru",
                    referral_code=ref_code,
                    referred_by_id=None
                )
                db_session.add(user)
                await db_session.flush()
            
            # Parse expiry
            expiry_ts = panel_client.get("expiryTime", 0)
            if expiry_ts and expiry_ts > 0:
                expires_at = datetime.utcfromtimestamp(expiry_ts / 1000)
            else:
                expires_at = None
            
            # Create Subscription
            sub_id = f"imp_{uuid_lib.uuid4().hex[:10]}"
            traffic_limit = panel_client.get("totalGB", 0)
            used_up = panel_client.get("up", 0)
            used_down = panel_client.get("down", 0)
            
            # Determine status
            now = datetime.utcnow()
            if not panel_client.get("enable", True):
                status = SubscriptionStatus.SUSPENDED
            elif expires_at and expires_at < now:
                status = SubscriptionStatus.EXPIRED
            elif traffic_limit > 0 and (used_up + used_down) >= traffic_limit:
                status = SubscriptionStatus.SUSPENDED
            else:
                status = SubscriptionStatus.ACTIVE
            
            subscription = Subscription(
                sub_id=sub_id,
                user_id=telegram_id,
                tariff_id=default_tariff_id,
                server_id=server.id,
                inbound_id=panel_client["inbound_id"],
                client_uuid=panel_client["uuid"],
                client_email=email,
                status=status,
                expires_at=expires_at,
                traffic_limit_bytes=traffic_limit,
                total_used_bytes=used_up + used_down,
                up_used_bytes=used_up,
                down_used_bytes=used_down
            )
            db_session.add(subscription)
            
            stats["imported"] += 1
            
        except Exception as e:
            stats["errors"] += 1
            stats["error_details"].append(f"Error importing {email}: {str(e)}")
            logger.error(f"Error importing client {email}: {e}", exc_info=True)
    
    await db_session.commit()
    
    # Update tgId on 3x-ui panel for successfully imported clients
    imported_emails = [
        m["email"] for m in mappings
        if m.get("email", "").strip() in clients_by_email
        and m.get("telegram_id")
    ]
    
    if imported_emails:
        try:
            async with get_client_for_server(server) as xui_client:
                for mapping in mappings:
                    email = mapping.get("email", "").strip()
                    tg_id = mapping.get("telegram_id")
                    panel_client = clients_by_email.get(email)
                    if panel_client and tg_id:
                        try:
                            expiry_ts = panel_client.get("expiryTime", 0)
                            await xui_client.update_client(
                                inbound_id=panel_client["inbound_id"],
                                client_uuid=panel_client["uuid"],
                                email=email,
                                limit_ip=panel_client.get("limitIp", settings.XUI_LIMIT_IP),
                                total_gb=panel_client.get("totalGB", 0),
                                expiry_time=expiry_ts,
                                enable=panel_client.get("enable", True),
                                flow=panel_client.get("flow", ""),
                            )
                            logger.info(f"Updated tgId for {email} on 3x-ui panel")
                        except Exception as e:
                            logger.warning(f"Failed to update tgId for {email} on panel: {e}")
        except Exception as e:
            logger.error(f"Failed to connect to 3x-ui for tgId updates: {e}")
    
    return stats

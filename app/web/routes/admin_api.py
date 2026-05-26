import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel
from datetime import datetime

from app.database import get_db
from app.models import Server, Subscription, User, Payment, PaymentStatus
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin")

security = HTTPBasic()

def authenticate_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Simple HTTP Basic Authentication check for API endpoints."""
    if credentials.username != settings.ADMIN_USERNAME or credentials.password != settings.ADMIN_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Pydantic schemas for request validation
class ServerCreate(BaseModel):
    name: str
    host: str
    port: int
    base_path: str = "/"
    api_token: str
    is_enabled: bool = True

class ServerUpdate(BaseModel):
    name: str
    host: str
    port: int
    base_path: str
    api_token: str
    is_enabled: bool

class SubscriptionUpdate(BaseModel):
    expires_at: Optional[datetime] = None
    traffic_limit_bytes: int
    status: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    balance_kopeks: int

class TariffCreate(BaseModel):
    name_ru: str
    name_en: str
    duration_days: int
    traffic_limit_gb: int
    price_kopeks: int
    is_enabled: bool = True

class TariffUpdate(BaseModel):
    name_ru: str
    name_en: str
    duration_days: int
    traffic_limit_gb: int
    price_kopeks: int
    is_enabled: bool

# Endpoints

@router.get("/stats", dependencies=[Depends(authenticate_admin)])
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    # Sync with 3x-ui servers to get latest traffic and settings
    from app.services.xui_service import sync_traffic_and_expiry
    try:
        await sync_traffic_and_expiry(db)
    except Exception as e:
        logger.error(f"Failed to sync traffic during admin stats get: {e}")

    # Counts
    total_users_query = await db.execute(select(func.count(User.id)))
    total_users = total_users_query.scalar() or 0

    total_subs_query = await db.execute(select(func.count(Subscription.id)))
    total_subs = total_subs_query.scalar() or 0

    total_revenue_query = await db.execute(
        select(func.sum(Payment.amount_kopeks)).where(Payment.status == PaymentStatus.COMPLETED)
    )
    total_revenue_kopeks = total_revenue_query.scalar() or 0
    total_revenue = total_revenue_kopeks / 100.0

    pending_payments_query = await db.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
    )
    pending_payments = pending_payments_query.scalar() or 0

    # Recent payments (last 10)
    payments_stmt = select(Payment).order_by(desc(Payment.created_at)).limit(10)
    payments_result = await db.execute(payments_stmt)
    recent_payments = []
    for p in payments_result.scalars().all():
        recent_payments.append({
            "id": p.id,
            "user_id": p.user_id,
            "amount": p.amount_kopeks / 100.0,
            "gateway": p.gateway.value,
            "status": p.status.value,
            "created_at": p.created_at.isoformat() + "Z"
        })

    return {
        "stats": {
            "total_users": total_users,
            "total_subscriptions": total_subs,
            "total_revenue": total_revenue,
            "pending_payments": pending_payments
        },
        "recent_payments": recent_payments
    }

@router.post("/cache/clear", dependencies=[Depends(authenticate_admin)])
async def clear_cache():
    from app.services.xui_service import clear_all_inbound_cache
    clear_all_inbound_cache()
    logger.info("Admin manually cleared inbound caches for all servers.")
    return {"success": True}

@router.get("/servers", dependencies=[Depends(authenticate_admin)])
async def get_servers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Server))
    servers = result.scalars().all()
    return servers

@router.post("/servers", dependencies=[Depends(authenticate_admin)])
async def create_server(data: ServerCreate, db: AsyncSession = Depends(get_db)):
    server = Server(
        name=data.name,
        host=data.host,
        port=data.port,
        base_path=data.base_path,
        api_token=data.api_token,
        is_enabled=data.is_enabled,
        status="UNKNOWN"
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server

@router.put("/servers/{server_id}", dependencies=[Depends(authenticate_admin)])
async def update_server(server_id: int, data: ServerUpdate, db: AsyncSession = Depends(get_db)):
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
        
    server.name = data.name
    server.host = data.host
    server.port = data.port
    server.base_path = data.base_path
    server.api_token = data.api_token
    server.is_enabled = data.is_enabled
    
    db.add(server)
    await db.commit()
    await db.refresh(server)
    
    from app.services.xui_service import clear_inbound_cache
    clear_inbound_cache(server_id)
    
    return server

@router.delete("/servers/{server_id}", dependencies=[Depends(authenticate_admin)])
async def delete_server(server_id: int, db: AsyncSession = Depends(get_db)):
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    await db.delete(server)
    await db.commit()
    
    from app.services.xui_service import clear_inbound_cache
    clear_inbound_cache(server_id)
    
    return {"success": True}

@router.get("/subscriptions", dependencies=[Depends(authenticate_admin)])
async def get_subscriptions(db: AsyncSession = Depends(get_db)):
    # Sync with 3x-ui servers to get latest traffic and settings
    from app.services.xui_service import sync_traffic_and_expiry
    try:
        await sync_traffic_and_expiry(db)
    except Exception as e:
        logger.error(f"Failed to sync traffic during admin subscriptions get: {e}")

    # Join subscription and user/tariff information
    result = await db.execute(select(Subscription))
    subs = result.scalars().all()
    
    formatted = []
    for s in subs:
        formatted.append({
            "sub_id": s.sub_id,
            "user_id": s.user_id,
            "tariff_id": s.tariff_id,
            "server_id": s.server_id,
            "client_uuid": s.client_uuid,
            "client_email": s.client_email,
            "status": s.status.value,
            "expires_at": s.expires_at.isoformat() + "Z" if s.expires_at else None,
            "traffic_limit_bytes": s.traffic_limit_bytes,
            "total_used_bytes": s.total_used_bytes,
            "created_at": s.created_at.isoformat() + "Z"
        })
    return formatted

@router.put("/subscriptions/{sub_id}", dependencies=[Depends(authenticate_admin)])
async def update_subscription(sub_id: str, data: SubscriptionUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.sub_id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
        
    from datetime import timezone
    if data.expires_at:
        if data.expires_at.tzinfo is not None:
            sub.expires_at = data.expires_at.astimezone(timezone.utc).replace(tzinfo=None)
        else:
            sub.expires_at = data.expires_at
    else:
        sub.expires_at = None
        
    sub.traffic_limit_bytes = data.traffic_limit_bytes
    
    from app.models import SubscriptionStatus, Server
    from app.services.xui_service import update_vpn_client
    
    sub.status = SubscriptionStatus(data.status)
    db.add(sub)
    
    # Fetch server details before committing
    server = await db.get(Server, sub.server_id)
    
    # Commit changes immediately to release database locks
    await db.commit()
    await db.refresh(sub)
    
    # Sync with 3x-ui server outside the open database transaction
    if server:
        try:
            await update_vpn_client(
                server=server,
                inbound_id=sub.inbound_id,
                client_uuid=sub.client_uuid,
                email=sub.client_email,
                enable=(sub.status == SubscriptionStatus.ACTIVE),
                expires_at=sub.expires_at,
                traffic_limit_bytes=sub.traffic_limit_bytes
            )
            logger.info(f"Synchronized updated subscription {sub.sub_id} with 3x-ui panel.")
        except Exception as e:
            logger.error(f"Failed to sync updated subscription {sub.sub_id} with 3x-ui: {e}")
            raise HTTPException(status_code=500, detail=f"Saved in database, but failed to update on 3x-ui: {str(e)}")
            
    return sub


@router.delete("/subscriptions/{sub_id}", dependencies=[Depends(authenticate_admin)])
async def delete_subscription(sub_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscription).where(Subscription.sub_id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
        
    # Mark as deleted and delete from 3x-ui
    from app.models import SubscriptionStatus, Server
    from app.services.xui_service import delete_vpn_client
    
    sub.status = SubscriptionStatus.DELETED
    db.add(sub)
    
    server = await db.get(Server, sub.server_id)
    inbound_id = sub.inbound_id
    client_uuid = sub.client_uuid
    
    # Commit changes immediately to release database locks
    await db.commit()
    
    if server:
        try:
            await delete_vpn_client(server, inbound_id, client_uuid)
            logger.info(f"Deleted subscription client {client_uuid} from 3x-ui panel.")
        except Exception as e:
            logger.error(f"Failed to delete subscription client {client_uuid} from 3x-ui: {e}")
            
    return {"success": True}


@router.get("/users", dependencies=[Depends(authenticate_admin)])
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return users


@router.put("/users/{user_id}", dependencies=[Depends(authenticate_admin)])
async def update_user(user_id: int, data: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.username = data.username
    user.first_name = data.first_name
    user.last_name = data.last_name
    user.balance_kopeks = data.balance_kopeks
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}", dependencies=[Depends(authenticate_admin)])
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Find all user subscriptions
    subs_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subs = subs_result.scalars().all()
    
    from app.models import Server, SubscriptionStatus
    from app.services.xui_service import delete_vpn_client
    
    # Mark all subscriptions as DELETED in database first
    sub_details = []
    for sub in subs:
        sub.status = SubscriptionStatus.DELETED
        db.add(sub)
        sub_details.append({
            "server_id": sub.server_id,
            "inbound_id": sub.inbound_id,
            "client_uuid": sub.client_uuid
        })
        
    await db.delete(user)
    
    # Commit changes immediately to release database locks
    await db.commit()
    
    # Now delete from 3x-ui servers outside the open database transaction
    for sd in sub_details:
        server = await db.get(Server, sd["server_id"])
        if server:
            try:
                await delete_vpn_client(server, sd["inbound_id"], sd["client_uuid"])
                logger.info(f"Deleted subscription client {sd['client_uuid']} from 3x-ui panel during user deletion.")
            except Exception as e:
                logger.error(f"Failed to delete client {sd['client_uuid']} on server {server.name} during user deletion: {e}")
                
    return {"success": True}


class PromocodeCreate(BaseModel):
    code: str
    type: str # "BALANCE" or "SUBSCRIPTION"
    value_kopeks: Optional[int] = 0
    tariff_id: Optional[int] = None
    duration_days: Optional[int] = 0
    max_uses: Optional[int] = 1
    expires_at: Optional[datetime] = None


@router.get("/promocodes", dependencies=[Depends(authenticate_admin)])
async def get_promocodes(db: AsyncSession = Depends(get_db)):
    from app.models import Promocode
    result = await db.execute(select(Promocode).order_by(desc(Promocode.created_at)))
    return result.scalars().all()


@router.post("/promocodes", dependencies=[Depends(authenticate_admin)])
async def create_promocode(data: PromocodeCreate, db: AsyncSession = Depends(get_db)):
    from app.models import Promocode, PromocodeType
    # Check if code already exists
    exists = await db.execute(select(Promocode).where(Promocode.code == data.code.upper()))
    if exists.scalars().first():
        raise HTTPException(status_code=400, detail="Promocode already exists")
        
    promocode = Promocode(
        code=data.code.upper(),
        type=PromocodeType(data.type),
        value_kopeks=data.value_kopeks,
        tariff_id=data.tariff_id,
        duration_days=data.duration_days,
        max_uses=data.max_uses,
        uses_count=0,
        expires_at=data.expires_at,
        is_active=True
    )
    db.add(promocode)
    await db.commit()
    await db.refresh(promocode)
    return promocode


@router.delete("/promocodes/{promo_id}", dependencies=[Depends(authenticate_admin)])
async def delete_promocode(promo_id: int, db: AsyncSession = Depends(get_db)):
    from app.models import Promocode
    promocode = await db.get(Promocode, promo_id)
    if not promocode:
        raise HTTPException(status_code=404, detail="Promocode not found")
    await db.delete(promocode)
    await db.commit()
    return {"success": True}


@router.get("/tariffs", dependencies=[Depends(authenticate_admin)])
async def get_tariffs(db: AsyncSession = Depends(get_db)):
    from app.models import TariffPlan
    result = await db.execute(select(TariffPlan))
    return result.scalars().all()


@router.post("/tariffs", dependencies=[Depends(authenticate_admin)])
async def create_tariff(data: TariffCreate, db: AsyncSession = Depends(get_db)):
    from app.models import TariffPlan
    tariff = TariffPlan(
        name_ru=data.name_ru,
        name_en=data.name_en,
        duration_days=data.duration_days,
        traffic_limit_gb=data.traffic_limit_gb,
        price_kopeks=data.price_kopeks,
        is_enabled=data.is_enabled
    )
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)
    return tariff


@router.put("/tariffs/{tariff_id}", dependencies=[Depends(authenticate_admin)])
async def update_tariff(tariff_id: int, data: TariffUpdate, db: AsyncSession = Depends(get_db)):
    from app.models import TariffPlan
    tariff = await db.get(TariffPlan, tariff_id)
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff plan not found")
        
    tariff.name_ru = data.name_ru
    tariff.name_en = data.name_en
    tariff.duration_days = data.duration_days
    tariff.traffic_limit_gb = data.traffic_limit_gb
    tariff.price_kopeks = data.price_kopeks
    tariff.is_enabled = data.is_enabled
    
    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)
    return tariff


@router.delete("/tariffs/{tariff_id}", dependencies=[Depends(authenticate_admin)])
async def delete_tariff(tariff_id: int, db: AsyncSession = Depends(get_db)):
    from app.models import TariffPlan
    tariff = await db.get(TariffPlan, tariff_id)
    if not tariff:
        raise HTTPException(status_code=404, detail="Tariff plan not found")
    await db.delete(tariff)
    await db.commit()
    return {"success": True}


# ─── Import from 3x-ui ───────────────────────────────────────────────

@router.get("/import/preview/{server_id}", dependencies=[Depends(authenticate_admin)])
async def import_preview(server_id: int, db: AsyncSession = Depends(get_db)):
    """Preview all clients on a given 3x-ui server for import."""
    server = await db.get(Server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    from app.services.xui_import import preview_clients
    
    try:
        clients = await preview_clients(server)
    except Exception as e:
        logger.error(f"Failed to preview clients from server {server.name}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Failed to connect to 3x-ui: {str(e)}")
    
    # Mark clients that are already imported
    for c in clients:
        existing = await db.execute(
            select(Subscription).where(Subscription.client_email == c["email"])
        )
        c["already_imported"] = existing.scalars().first() is not None
    
    return clients


class ImportMapping(BaseModel):
    email: str
    telegram_id: int

class ImportRequest(BaseModel):
    server_id: int
    default_tariff_id: int
    mappings: List[ImportMapping]


@router.post("/import/execute", dependencies=[Depends(authenticate_admin)])
async def import_execute(data: ImportRequest, db: AsyncSession = Depends(get_db)):
    """Execute import of selected clients from 3x-ui into the bot database."""
    server = await db.get(Server, data.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    
    from app.services.xui_import import import_clients
    
    mappings_dicts = [{"email": m.email, "telegram_id": m.telegram_id} for m in data.mappings]
    
    try:
        result = await import_clients(
            server=server,
            db_session=db,
            mappings=mappings_dicts,
            default_tariff_id=data.default_tariff_id
        )
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    
    return result

import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, BigInteger, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.database import Base

class Role(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"
    SUPERADMIN = "SUPERADMIN"

class PaymentGateway(str, enum.Enum):
    CRYPTO_BOT = "CRYPTO_BOT"
    TELEGRAM_STARS = "TELEGRAM_STARS"
    YOOKASSA = "YOOKASSA"
    ROLLYPAY = "ROLLYPAY"
    TON = "TON"
    USDT_TRC20 = "USDT_TRC20"
    BALANCE = "BALANCE"
    PROMOCODE = "PROMOCODE"

class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"

class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(Role), default=Role.ADMIN)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    
    id = Column(BigInteger, primary_key=True)  # Telegram User ID
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language = Column(String, default="ru")
    balance_kopeks = Column(BigInteger, default=0)
    referral_code = Column(String, unique=True, nullable=False, index=True)
    referred_by_id = Column(BigInteger, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

class Server(Base):
    __tablename__ = "servers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    base_path = Column(String, default="/")
    api_token = Column(String, nullable=False)  # 3x-ui auth token
    is_enabled = Column(Boolean, default=True)
    status = Column(String, default="UNKNOWN")  # ONLINE, OFFLINE, UNKNOWN
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="server", cascade="all, delete-orphan")

class TariffPlan(Base):
    __tablename__ = "tariff_plans"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name_ru = Column(String, nullable=False)
    name_en = Column(String, nullable=False)
    duration_days = Column(Integer, nullable=False)
    traffic_limit_gb = Column(Integer, nullable=False)  # 0 for unlimited
    price_kopeks = Column(BigInteger, nullable=False)
    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="tariff", cascade="all, delete-orphan")

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sub_id = Column(String, unique=True, nullable=False, index=True)  # unique config path token
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    tariff_id = Column(Integer, ForeignKey("tariff_plans.id"), nullable=False)
    server_id = Column(Integer, ForeignKey("servers.id"), nullable=False)
    inbound_id = Column(Integer, nullable=False)  # target inbound numeric ID on 3x-ui
    client_uuid = Column(String, nullable=False)
    client_email = Column(String, unique=True, nullable=False, index=True)  # usr_{userId}_sub_{subId}
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    expires_at = Column(DateTime, nullable=True)
    traffic_limit_bytes = Column(BigInteger, nullable=False)
    total_used_bytes = Column(BigInteger, default=0)
    up_used_bytes = Column(BigInteger, default=0)
    down_used_bytes = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    auto_renew = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="subscriptions")
    tariff = relationship("TariffPlan", back_populates="subscriptions")
    server = relationship("Server", back_populates="subscriptions")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True)  # UUID or external gateway transaction ID
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount_kopeks = Column(BigInteger, nullable=False)
    currency = Column(String, nullable=False)  # RUB, USD, TON, STARS
    gateway = Column(Enum(PaymentGateway), nullable=False)
    gateway_payment_id = Column(String, nullable=True, index=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    payload = Column(String, nullable=True)  # json metadata
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="payments")
    rewards = relationship("ReferralReward", back_populates="payment", cascade="all, delete-orphan")

class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_id = Column(BigInteger, nullable=False)
    referee_id = Column(BigInteger, nullable=False)
    payment_id = Column(String, ForeignKey("payments.id"), nullable=False)
    amount_kopeks = Column(BigInteger, nullable=False)
    is_credited = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    payment = relationship("Payment", back_populates="rewards")

class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(String, nullable=False)
    description = Column(String, nullable=True)


class PromocodeType(str, enum.Enum):
    BALANCE = "BALANCE"
    SUBSCRIPTION = "SUBSCRIPTION"


class Promocode(Base):
    __tablename__ = "promocodes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, unique=True, nullable=False, index=True)
    type = Column(Enum(PromocodeType), nullable=False)
    value_kopeks = Column(BigInteger, default=0)  # For BALANCE type
    duration_days = Column(Integer, default=0)    # For SUBSCRIPTION type
    tariff_id = Column(Integer, ForeignKey("tariff_plans.id"), nullable=True) # associated tariff
    max_uses = Column(Integer, default=1)
    uses_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tariff = relationship("TariffPlan")


class UserPromocode(Base):
    __tablename__ = "user_promocodes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    promocode_id = Column(Integer, ForeignKey("promocodes.id"), nullable=False)
    used_at = Column(DateTime, default=datetime.utcnow)

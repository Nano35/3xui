from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
from app.models import TariffPlan, Server, PaymentGateway
from app.bot.localization import MESSAGES
from app.config import settings

def get_main_menu(lang: str, is_admin: bool = False) -> ReplyKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    buttons = [
        [KeyboardButton(text=msgs["menu_profile"]), KeyboardButton(text=msgs["menu_shop"])],
        [KeyboardButton(text=msgs["menu_support"]), KeyboardButton(text=msgs.get("menu_about", "ℹ️ О сервисе"))]
    ]
    if is_admin:
        buttons.append([KeyboardButton(text=msgs["menu_admin"])])
        
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_tariffs_keyboard(tariffs: List[TariffPlan], lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    for tariff in tariffs:
        name = tariff.name_ru if lang == "ru" else tariff.name_en
        price = tariff.price_kopeks / 100.0
        # Button callback format: select_tariff:{tariff_id}
        keyboard.append([InlineKeyboardButton(
            text=f"{name} — {price:.0f} руб.",
            callback_data=f"select_tariff:{tariff.id}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_servers_keyboard(servers: List[Server], lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    for server in servers:
        # Button callback format: select_server:{server_id}
        keyboard.append([InlineKeyboardButton(
            text=f"🌐 {server.name}",
            callback_data=f"select_server:{server.id}"
        )])
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data="shop_back_tariffs")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_gateways_keyboard(lang: str, balance_kopeks: int = 0) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    
    # Always allow payment from balance
    balance_rub = balance_kopeks / 100.0
    btn_label = f"💰 Баланс ({balance_rub:.2f} руб.)" if lang == "ru" else f"💰 Balance ({balance_rub:.2f} RUB)"
    keyboard.append([InlineKeyboardButton(text=btn_label, callback_data=f"select_gateway:{PaymentGateway.BALANCE.value}")])
    
    # We check each gateway's enabled state from settings
    if getattr(settings, "YOOKASSA_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💳 ЮКасса (Карты РФ)", callback_data=f"select_gateway:{PaymentGateway.YOOKASSA.value}")])
        
    if getattr(settings, "TELEGRAM_STARS_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💎 Telegram Stars", callback_data=f"select_gateway:{PaymentGateway.TELEGRAM_STARS.value}")])
        
    if getattr(settings, "CRYPTOBOT_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🤖 CryptoBot (USDT/TON)", callback_data=f"select_gateway:{PaymentGateway.CRYPTO_BOT.value}")])
        
    if getattr(settings, "ROLLYPAY_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🛒 RollyPay.io (Крипта/Карты)", callback_data=f"select_gateway:{PaymentGateway.ROLLYPAY.value}")])
        
    if getattr(settings, "TON_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🔗 TON (Wallet Transfer)", callback_data=f"select_gateway:{PaymentGateway.TON.value}")])
        
    if getattr(settings, "USDT_TRC20_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💵 USDT TRC20 (Direct)", callback_data=f"select_gateway:{PaymentGateway.USDT_TRC20.value}")])
        
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data="shop_back_servers")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_payment_keyboard(payment_id: str, checkout_url: str, lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    
    keyboard = []
    # If it is TON/USDT/Stars or normal redirect link
    if checkout_url.startswith("http://") or checkout_url.startswith("https://"):
        keyboard.append([InlineKeyboardButton(text=msgs["pay_button"], url=checkout_url)])
    elif checkout_url == "tg_stars_invoice":
        # Handled by standard Invoice, button is not needed or can redirect to invoice payment
        pass
        
    keyboard.append([InlineKeyboardButton(text=msgs["check_pay_button"], callback_data=f"check_pay:{payment_id}")])
    keyboard.append([InlineKeyboardButton(text=msgs["cancel"], callback_data="cancel_payment")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_profile_menu_keyboard(lang: str, has_trial: bool = False) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    if not has_trial:
        keyboard.append([InlineKeyboardButton(text=msgs.get("btn_trial_sub", "🎁 Тестовая подписка (3 дня)"), callback_data="profile_trial")])
        
    keyboard.extend([
        [InlineKeyboardButton(text=msgs["btn_my_sub"], callback_data="profile_my_subs")],
        [InlineKeyboardButton(text=msgs["btn_renew_sub"], callback_data="profile_renew_subs")],
        [InlineKeyboardButton(text=msgs["btn_partner"], callback_data="profile_partner")],
        [
            InlineKeyboardButton(text=msgs["btn_topup"], callback_data="profile_topup"),
            InlineKeyboardButton(text=msgs["btn_history"], callback_data="profile_history")
        ],
        [InlineKeyboardButton(text=msgs["btn_promocode"], callback_data="profile_promocode")],
        [InlineKeyboardButton(text=msgs["btn_instructions"], callback_data="profile_instructions")]
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_subscriptions_list_keyboard(subscriptions: list, lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    for sub in subscriptions:
        label = f"🎫 {sub.sub_id} ({sub.tariff.name_ru if lang == 'ru' else sub.tariff.name_en})"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"view_sub:{sub.sub_id}")])
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data="profile_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_sub_detail_keyboard(sub_id: str, lang: str, auto_renew: bool = False, show_renew: bool = True) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    if show_renew:
        keyboard.append([InlineKeyboardButton(text=msgs["btn_renew_sub"], callback_data=f"renew_sub_from_detail:{sub_id}")])
        btn_auto_text = (
            f"🔄 Автопродление: {'✅ ВКЛ' if auto_renew else '❌ ВЫКЛ'}"
            if lang == "ru" else
            f"🔄 Auto-Renew: {'✅ ON' if auto_renew else '❌ OFF'}"
        )
        keyboard.append([InlineKeyboardButton(text=btn_auto_text, callback_data=f"toggle_auto_renew:{sub_id}")])
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data="profile_my_subs")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_renew_durations_keyboard(sub_id: str, lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    durations = [30, 60, 90, 180, 360]
    keyboard = []
    for days in durations:
        label = f"🔄 {days} дней"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"renew_dur:{sub_id}:{days}")])
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data=f"view_sub:{sub_id}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_renew_payment_methods_keyboard(sub_id: str, days: int, cost_rub: float, lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = [
        [InlineKeyboardButton(text=msgs["btn_pay_balance"], callback_data=f"renew_pay_bal:{sub_id}:{days}")],
        [InlineKeyboardButton(text="💳 Выбрать платежную систему", callback_data=f"renew_pay_gate:{sub_id}:{days}")],
        [InlineKeyboardButton(text=msgs["back"], callback_data=f"renew_sub_from_detail:{sub_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_renew_gateways_keyboard(sub_id: str, days: int, lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    
    if getattr(settings, "YOOKASSA_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💳 ЮКасса (Карты РФ)", callback_data=f"renew_gateway:{sub_id}:{days}:{PaymentGateway.YOOKASSA.value}")])
        
    if getattr(settings, "TELEGRAM_STARS_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💎 Telegram Stars", callback_data=f"renew_gateway:{sub_id}:{days}:{PaymentGateway.TELEGRAM_STARS.value}")])
        
    if getattr(settings, "CRYPTOBOT_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🤖 CryptoBot (USDT/TON)", callback_data=f"renew_gateway:{sub_id}:{days}:{PaymentGateway.CRYPTO_BOT.value}")])
        
    if getattr(settings, "ROLLYPAY_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🛒 RollyPay.io (Крипта/Карты)", callback_data=f"renew_gateway:{sub_id}:{days}:{PaymentGateway.ROLLYPAY.value}")])
        
    if getattr(settings, "TON_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🔗 TON (Wallet Transfer)", callback_data=f"renew_gateway:{sub_id}:{days}:{PaymentGateway.TON.value}")])
        
    if getattr(settings, "USDT_TRC20_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💵 USDT TRC20 (Direct)", callback_data=f"renew_gateway:{sub_id}:{days}:{PaymentGateway.USDT_TRC20.value}")])
        
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data=f"renew_dur:{sub_id}:{days}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_deposit_gateways_keyboard(amount_rub: int, lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    keyboard = []
    
    if getattr(settings, "YOOKASSA_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💳 ЮКасса (Карты РФ)", callback_data=f"deposit_gateway:{amount_rub}:{PaymentGateway.YOOKASSA.value}")])
        
    if getattr(settings, "TELEGRAM_STARS_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💎 Telegram Stars", callback_data=f"deposit_gateway:{amount_rub}:{PaymentGateway.TELEGRAM_STARS.value}")])
        
    if getattr(settings, "CRYPTOBOT_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🤖 CryptoBot (USDT/TON)", callback_data=f"deposit_gateway:{amount_rub}:{PaymentGateway.CRYPTO_BOT.value}")])
        
    if getattr(settings, "ROLLYPAY_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🛒 RollyPay.io (Крипта/Карты)", callback_data=f"deposit_gateway:{amount_rub}:{PaymentGateway.ROLLYPAY.value}")])
        
    if getattr(settings, "TON_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="🔗 TON (Wallet Transfer)", callback_data=f"deposit_gateway:{amount_rub}:{PaymentGateway.TON.value}")])
        
    if getattr(settings, "USDT_TRC20_ENABLED", False):
        keyboard.append([InlineKeyboardButton(text="💵 USDT TRC20 (Direct)", callback_data=f"deposit_gateway:{amount_rub}:{PaymentGateway.USDT_TRC20.value}")])
        
    keyboard.append([InlineKeyboardButton(text=msgs["back"], callback_data="profile_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_back_to_profile_keyboard(lang: str) -> InlineKeyboardMarkup:
    msgs = MESSAGES.get(lang, MESSAGES["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=msgs["back"], callback_data="profile_main")]
    ])


MESSAGES = {
    "ru": {
        "welcome": (
            "👋 <b>Добро пожаловать в Mrzky VPN!</b>\n\n"
            "Мы предоставляем быстрый, безопасный и неограниченный доступ в интернет через протокол VLESS-Reality.\n\n"
            "🚀 <b>Наши преимущества:</b>\n"
            "• Высокая скорость и низкий пинг\n"
            "• Поддержка всех устройств (iOS, Android, Windows, macOS)\n"
            "• Удобная оплата картами РФ, криптой и звездами\n\n"
            "💳 Используйте меню ниже для покупки подписки или просмотра своего профиля!"
        ),
        "welcome_ref": "🎁 Вы зарегистрировались по пригласительной ссылке!",
        "menu_profile": "👤 Личный кабинет",
        "menu_shop": "🛒 Купить подписку",
        "menu_support": "💬 Поддержка",
        "menu_admin": "⚙️ Админ-панель",
        "profile_desc": (
            "👤 <b>Ваш личный кабинет:</b>\n\n"
            "🆔 ID: <code>{user_id}</code>\n"
            "💰 Баланс: <b>{balance} руб.</b>\n"
            "🔗 Реферальная ссылка: <code>{ref_link}</code>\n"
            "👥 Приглашено пользователей: <b>{ref_count}</b>\n\n"
            "🔑 <b>Ваши подписки:</b>\n{subscriptions}"
        ),
        "sub_item": "• Код: <code>{sub_id}</code> | Статус: <b>{status}</b>\n  Тариф: <i>{tariff}</i>\n  Трафик: <b>{used} / {limit} GB</b>\n  Действует до: <b>{expiry}</b>\n  Ссылка: <code>{link}</code>\n",
        "no_subs": "<i>У вас пока нет активных подписок.</i>",
        "shop_choose_tariff": "🛒 <b>Выберите тарифный план:</b>",
        "shop_choose_server": "🌐 <b>Выберите сервер:</b>",
        "shop_choose_gateway": "💳 <b>Выберите способ оплаты:</b>\n\nСумма к оплате: <b>{amount} руб.</b>",
        "payment_created": (
            "🎉 <b>Счет успешно создан!</b>\n\n"
            "Для оплаты нажмите кнопку ниже. После завершения платежа вернитесь в бот и нажмите кнопку <b>«Проверить оплату»</b>."
        ),
        "pay_button": "💳 Перейти к оплате",
        "check_pay_button": "🔄 Проверить оплату",
        "payment_success": (
            "✅ <b>Оплата прошла успешно!</b>\n\n"
            "Ваша подписка активирована. Вот ссылка для подключения к VPN:\n\n"
            "<code>{config_link}</code>\n\n"
            "🚀 <b>Как подключиться?</b>\n"
            "1. Скачайте клиент v2ray (Incy/v2rayNG для Android, Happ/Incy для iOS, Throne для ПК).\n"
            "2. Скопируйте ссылку выше.\n"
            "3. Импортируйте ссылку из буфера обмена в приложении.\n"
            "4. Включите соединение."
        ),
        "payment_pending": "⏳ Платеж еще не подтвержден. Пожалуйста, подождите или попробуйте проверить позже.",
        "payment_failed": "❌ Не удалось подтвердить платеж. Если возникли проблемы, напишите в поддержку.",
        "support_text": (
            "💬 <b>Служба поддержки MRZKY VPN</b>\n\n"
            "Если у вас возникли вопросы по оплате, настройке подключения или работе серверов, напишите нашему администратору:\n\n"
            "📞 Поддержка: {support_handle}\n\n"
            "Мы ответим вам в ближайшее время!"
        ),
        "balance_topup": "💰 <b>Пополнение баланса</b>\n\nВведите сумму пополнения в рублях (целое число):",
        "back": "⬅️ Назад",
        "cancel": "❌ Отмена",

        # Новые ключи
        "profile_main": (
            "👤 <b>Ваш личный кабинет:</b>\n\n"
            "🆔 Telegram ID: <code>{user_id}</code>\n"
            "💰 Текущий баланс: <b>{balance} руб.</b>\n\n"
            "Используйте кнопки ниже для управления подписками, балансом и активации промокодов."
        ),
        "btn_my_sub": "🎫 Моя подписка",
        "btn_renew_sub": "🔄 Продлить подписку",
        "btn_partner": "👥 Партнёрская программа",
        "btn_topup": "💳 Пополнить баланс",
        "btn_history": "📜 История пополнений",
        "btn_promocode": "🎁 Активировать промокод",
        "btn_instructions": "📖 Инструкции",
        "btn_pay_balance": "💰 Оплатить с баланса",
        
        "partner_desc": (
            "👥 <b>Партнёрская программа MRZKY VPN</b>\n\n"
            "Приглашайте друзей и получайте <b>{percent}%</b> с каждого их пополнения на свой баланс!\n\n"
            "🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
            "📊 <b>Ваша статистика:</b>\n"
            "• Приглашено пользователей: <b>{ref_count}</b>\n"
            "• Заработано всего: <b>{earned} руб.</b>"
        ),
        "promocode_enter": "🎁 <b>Введите промокод для активации:</b>",
        "promocode_success": "✅ <b>Промокод успешно активирован!</b>",
        "promocode_error": "❌ <b>Ошибка при активации промокода:</b>\n{error}",
        
        "history_desc": "📜 <b>История ваших пополнений (последние 10 операций):</b>\n\n{history}",
        "history_item": "• {date} | +{amount} руб. | {gateway}\n",
        "no_history": "<i>У вас пока нет истории пополнений.</i>",
        
        "instructions_title": "📖 <b>Инструкции по подключению к MRZKY VPN</b>\n\n{text}",
        "default_instructions": (
            "🚀 <b>Шаг 1: Установите приложение-клиент</b>\n"
            "• <b>Android:</b> Incy, v2rayNG, Sing-box\n"
            "• <b>iOS (iPhone):</b> Happ, Incy, V2Box, V2RayNG или Sing-box\n"
            "• <b>Windows:</b> Throne, Happ или v2rayN\n"
            "• <b>macOS:</b> Happ, Throne или Sing-box\n\n"
            "🚀 <b>Шаг 2: Скопируйте ссылку подписки</b>\n"
            "Перейдите в раздел 'Моя подписка' и скопируйте ссылку подписки (начинается с http:// или https://)\n\n"
            "🚀 <b>Шаг 3: Добавьте конфигурацию в приложение</b>\n"
            "Импортируйте ссылку из буфера обмена (в большинстве приложений это кнопка '+' -> 'Import from clipboard' или 'Import subscription') и нажмите кнопку 'Подключить/Пуск'!"
        ),
        "menu_about": "ℹ️ О сервисе",
        "about_service_text": (
            "ℹ️ <b>О сервисе Mrzky VPN</b>\n\n"
            "Mrzky VPN — это современный, быстрый и стабильный VPN-сервис, работающий на базе передовых протоколов шифрования (VLESS Reality). Мы обеспечиваем полную анонимность, безопасность ваших данных и доступ к любым ресурсам без ограничений скорости.\n\n"
            "📄 Перед использованием сервиса, пожалуйста, ознакомьтесь с нашими юридическими документами, используя кнопки ниже:"
        ),
        "btn_trial_sub": "🎁 Тестовая подписка (3 дня)"
    },
    "en": {
        "welcome": (
            "👋 <b>Welcome to Mrzky VPN!</b>\n\n"
            "We provide high-speed, secure, and unrestricted internet access via VLESS-Reality protocol.\n\n"
            "🚀 <b>Our Advantages:</b>\n"
            "• High speed & low ping\n"
            "• Compatible with all devices (iOS, Android, Windows, macOS)\n"
            "• Easy payment methods (Cards, Crypto, Stars)\n\n"
            "💳 Use the menu below to buy a subscription or manage your profile!"
        ),
        "welcome_ref": "🎁 You have registered using an invitation link!",
        "menu_profile": "👤 My Profile",
        "menu_shop": "🛒 Buy VPN",
        "menu_support": "💬 Support",
        "menu_admin": "⚙️ Admin Panel",
        "profile_desc": (
            "👤 <b>Your Account Details:</b>\n\n"
            "🆔 ID: <code>{user_id}</code>\n"
            "💰 Balance: <b>{balance} RUB</b>\n"
            "🔗 Referral Link: <code>{ref_link}</code>\n"
            "👥 Invited Users: <b>{ref_count}</b>\n\n"
            "🔑 <b>Your VPN Subscriptions:</b>\n{subscriptions}"
        ),
        "sub_item": "• Key: <code>{sub_id}</code> | Status: <b>{status}</b>\n  Tariff: <i>{tariff}</i>\n  Traffic: <b>{used} / {limit} GB</b>\n  Expires: <b>{expiry}</b>\n  Config: <code>{link}</code>\n",
        "no_subs": "<i>You don't have any subscriptions yet.</i>",
        "shop_choose_tariff": "🛒 <b>Select a subscription tariff:</b>",
        "shop_choose_server": "🌐 <b>Select VPN server:</b>",
        "shop_choose_gateway": "💳 <b>Select payment method:</b>\n\nAmount to pay: <b>{amount} RUB</b>",
        "payment_created": (
            "🎉 <b>Invoice created successfully!</b>\n\n"
            "Click the button below to pay. Once completed, return to the bot and click <b>\"Verify Payment\"</b>."
        ),
        "pay_button": "💳 Pay Now",
        "check_pay_button": "🔄 Verify Payment",
        "payment_success": (
            "✅ <b>Payment successful!</b>\n\n"
            "Your VPN access is now active. Here is your configuration link:\n\n"
            "<code>{config_link}</code>\n\n"
            "🚀 <b>How to connect?</b>\n"
            "1. Download v2ray client (v2rayNG/Incy for Android, Incy/Happ for iOS, Throne for PC).\n"
            "2. Copy the link above.\n"
            "3. Import config link from clipboard in the app.\n"
            "4. Start the VPN connection."
        ),
        "payment_pending": "⏳ Payment is not yet confirmed. Please wait a moment or try verifying again.",
        "payment_failed": "❌ Payment verification failed. Contact support if you need assistance.",
        "support_text": (
            "💬 <b>MRZKY VPN Support Service</b>\n\n"
            "If you have any questions regarding billing, connection settings, or servers, message our administrator:\n\n"
            "📞 Contact: {support_handle}\n\n"
            "We will assist you as soon as possible!"
        ),
        "balance_topup": "💰 <b>Top Up Balance</b>\n\nEnter the amount to deposit in RUB (integer):",
        "back": "⬅️ Back",
        "cancel": "❌ Cancel",

        # New keys
        "profile_main": (
            "👤 <b>Your Profile:</b>\n\n"
            "🆔 Telegram ID: <code>{user_id}</code>\n"
            "💰 Current Balance: <b>{balance} RUB</b>\n\n"
            "Use the buttons below to manage your subscriptions, balance, and activate promocodes."
        ),
        "btn_my_sub": "🎫 My Subscription",
        "btn_renew_sub": "🔄 Renew Subscription",
        "btn_partner": "👥 Referral Program",
        "btn_topup": "💳 Top Up Balance",
        "btn_history": "📜 Deposit History",
        "btn_promocode": "🎁 Activate Promocode",
        "btn_instructions": "📖 Instructions",
        "btn_pay_balance": "💰 Pay from Balance",
        
        "partner_desc": (
            "👥 <b>MRZKY VPN Referral Program</b>\n\n"
            "Invite friends and earn <b>{percent}%</b> of their deposits credited directly to your balance!\n\n"
            "🔗 Your Referral Link:\n<code>{ref_link}</code>\n\n"
            "📊 <b>Your Stats:</b>\n"
            "• Invited Users: <b>{ref_count}</b>\n"
            "• Total Earned: <b>{earned} RUB</b>"
        ),
        "promocode_enter": "🎁 <b>Enter promocode to activate:</b>",
        "promocode_success": "✅ <b>Promocode activated successfully!</b>",
        "promocode_error": "❌ <b>Failed to activate promocode:</b>\n{error}",
        
        "history_desc": "📜 <b>Your Deposit History (last 10 transactions):</b>\n\n{history}",
        "history_item": "• {date} | +{amount} RUB | {gateway}\n",
        "no_history": "<i>You don't have any deposit history yet.</i>",
        
        "instructions_title": "📖 <b>Instructions to Connect to MRZKY VPN</b>\n\n{text}",
        "default_instructions": (
            "🚀 <b>Step 1: Install client application</b>\n"
            "• <b>Android:</b> v2rayNG or Sing-box\n"
            "• <b>iOS (iPhone):</b> Happ, Incy, V2Box or Sing-box\n"
            "• <b>Windows:</b> Throne or v2rayN\n"
            "• <b>macOS:</b> Happ, Throne or Sing-box\n\n"
            "🚀 <b>Step 2: Copy subscription link</b>\n"
            "Go to 'My Subscription' section and copy the subscription link (starts with http:// or https://)\n\n"
            "🚀 <b>Step 3: Import configuration in the app</b>\n"
            "Import the link from clipboard (usually via '+' button -> 'Import from clipboard' or 'Import subscription') and tap 'Connect/Start'!"
        ),
        "menu_about": "ℹ️ About Service",
        "about_service_text": (
            "ℹ️ <b>About Mrzky VPN</b>\n\n"
            "Mrzky VPN is a modern, fast, and stable VPN service powered by state-of-the-art encryption protocols (VLESS Reality). We ensure complete anonymity, security of your data, and unrestricted access to any resource without speed limitations.\n\n"
            "📄 Before using our service, please review our legal documents using the buttons below:"
        ),
        "btn_trial_sub": "🎁 Free Trial (3 Days)"
    }
}

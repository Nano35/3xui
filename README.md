# 3xui — Multi-Node VPN Subscription & Billing Manager for Xray (3x-ui)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Aiogram v3](https://img.shields.io/badge/Aiogram-v3-orange.svg)](https://docs.aiogram.dev/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-blue.svg)](https://docs.docker.com/compose/)

**3xui** is a modern, self-hosted, multi-node VPN subscription management system and billing bot. It integrates directly with one or multiple **3x-ui** panels (Xray-core) to automate the entire client lifecycle: user registration, server resource allocation, automated payments/donations, live bandwidth/traffic monitoring, subscription renewal, and automated suspension.

---

## 🌍 Why This Project Matters (Ecosystem & Social Impact)

In regions facing strict censorship and severe internet restrictions, maintaining access to the global network is not just a technical challenge, but a fundamental human right. Protocols like VLESS (with REALITY), Trojan, and Shadowsocks are the lifeline for millions of journalists, developers, students, and citizens to access unbiased news, open-source documentation, and communication tools.

While panels like `3x-ui` are excellent for technical administrators, they are too complex for average, non-technical users. Additionally, managing keys, bandwidth usage, and server costs manually is highly labor-intensive for administrators running community-driven networks.

**3xui bridges this gap:**
- **For Users:** Offers a simple, mobile-friendly Telegram bot interface. Users can obtain VPN configurations, track their traffic limits, and extend their access with one click.
- **For Communities & NGOs:** Allows independent developers, non-profits, and communities to pool resources, run self-hosted VPN infrastructures, automatically monitor server loads, and gather donations or fees to cover VPS costs.
- **Accessibility:** Removes the technical barrier to secure digital privacy, enabling non-technical users to access censorship-circumvention tools safely.

---

## 🚀 Key Features

### 🤖 Telegram Bot (Client Interface)
- **Instant Configuration:** One-click VPN config generation (VLESS, Trojan, Shadowsocks).
- **Usage Tracking:** Live stats showing remaining traffic limits and subscription days.
- **Billing & Payments:** Multi-gateway integration supporting automatic deposits (YooKassa, CryptoBot, Telegram Stars, RollyPay, TON, USDT TRC20).
- **Referral System:** Built-in multi-level referral mechanism to encourage community-driven organic growth.
- **Promocodes:** Support for discount codes and promotional campaigns.

### 🌐 Admin Web Dashboard (FastAPI Backend)
- **Centralized Control:** Unified dashboard to monitor all backend servers and nodes.
- **Statistics:** Visual overview of total users, active subscriptions, revenue, and bandwidth consumption.
- **Server Management:** Add, configure, and monitor connection status of multiple `3x-ui` panels.
- **Tariff & Subscription Control:** Create and modify plans (days, price, traffic limits in GB).
- **Logs & Audit:** Clear logging of transactions, payments, and client allocations.

### ⚙️ Automation & Backend Engine
- **Multi-Node Syncing:** Background scheduler that regularly pulls traffic statistics from all panels and updates the local DB.
- **Auto-Suspension:** Suspends configs instantly when traffic limits are reached or subscriptions expire.
- **Database Migrations:** Out-of-the-box Alembic migrations supporting both SQLite and PostgreSQL.

---

## 🛠 Tech Stack

- **Backend Framework:** FastAPI (Asynchronous Python)
- **Database Interface:** SQLAlchemy 2.0 (async), Alembic (migrations)
- **Database:** SQLite (default/lightweight), PostgreSQL (production-ready)
- **Bot Engine:** Aiogram v3 (async Telegram bot framework)
- **Deployment:** Docker & Docker Compose
- **Scheduling:** Asyncio-based background daemon

---

## 📂 Project Structure

```text
3xui/
├── app/
│   ├── bot/                # Telegram Bot handlers (start, profile, shop, support, admin)
│   ├── services/           # Core logic (xui_client, payments, scheduler)
│   ├── web/                # FastAPI web server and Admin API routes
│   ├── config.py           # Configuration manager
│   ├── database.py         # DB connection helper
│   └── models.py           # Declarative database models (SQLAlchemy)
├── migrations/             # Alembic database migrations
├── Dockerfile              # Docker building configuration
├── docker-compose.yml      # Service definitions (Web app, DB, Bot)
├── requirements.txt        # Package dependencies
└── .env.example            # Template for environment variables
```

---

## ⚙️ Quick Start

### 1. Prerequisites
- Docker and Docker Compose installed.
- A Telegram Bot Token (obtained from [@BotFather](https://t.me/BotFather)).
- One or more running servers with `3x-ui` installed (API access enabled).

### 2. Configure Environment
Clone the repository and copy the environment template:
```bash
git clone https://github.com/Nano35/3xui.git
cd 3xui
cp .env.example .env
```
Edit the `.env` file to set your configuration keys (Bot Token, Database Credentials, Payment keys, Admin user IDs, etc.).

### 3. Deploy
Launch the containerized application using Docker Compose:
```bash
docker-compose up -d --build
```
This command spins up:
1. **Web App (FastAPI)**: Serves webhook endpoints and the Admin dashboard.
2. **Bot Client**: Runs the Telegram bot instance.
3. **Scheduler**: Runs background sync and billing enforcement loops.

---

## 🤝 Contributing

We welcome contributions of all kinds!
- **Bug Reports & Feature Requests:** Please open an [Issue](https://github.com/Nano35/3xui/issues).
- **Code Contributions:** Fork the repository, create your feature branch, and submit a Pull Request.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

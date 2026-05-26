import os
import logging
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.config import settings
from app.web.routes import admin_api, webhooks

logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(
    title="MRZKY VPN Admin & Payment Web Server",
    description="Web server handling bot webhooks, payment redirections, sandbox payments, and admin SPA dashboard API.",
    version="1.0.0"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(webhooks.router)
app.include_router(admin_api.router)

# Ensure static directory exists
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# Mount static files under /admin path
app.mount("/admin", StaticFiles(directory=static_dir, html=True), name="static")

@app.get("/")
async def root_redirect():
    """Redirect home to admin dashboard."""
    return RedirectResponse(url="/admin/")

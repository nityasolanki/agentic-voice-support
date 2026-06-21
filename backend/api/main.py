"""
FastAPI application entry point.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.session import init_db
from backend.services.qdrant import ensure_collections
from backend.api.routes import voice, tickets, orders, outbound
from config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    await ensure_collections()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Agentic Voice Customer Support",
    version="1.0.0",
    description="AI-powered voice customer support with autonomous issue resolution.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(voice.router, prefix="/api/voice", tags=["Voice"])
app.include_router(tickets.router, prefix="/api/tickets", tags=["Tickets"])
app.include_router(orders.router, prefix="/api/orders", tags=["Orders"])
app.include_router(outbound.router, prefix="/api/outbound", tags=["Outbound"])


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

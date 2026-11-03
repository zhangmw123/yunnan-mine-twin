"""矿山数字孪生系统后端入口"""
import asyncio

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from routers import analysis, debug, monitor
from services import twin_engine
from services.weather_sync import router as weather_router

app = FastAPI(title="云南高原露天矿山三维形变监测与溃坝推演系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(monitor.router)
app.include_router(analysis.router)
app.include_router(weather_router)
app.include_router(debug.router)


@app.on_event("startup")
async def startup():
    async def boot():
        # 启动即加载矿卡轨迹（不依赖首个 WebSocket 客户端），保证接口与推流数据一致
        await twin_engine.engine._load_vehicles()
        await asyncio.sleep(1)
        await twin_engine.engine.tick()

    asyncio.create_task(boot())


@app.websocket("/ws/mine-twin")
async def mine_twin(ws: WebSocket):
    await twin_engine.ws_endpoint(ws)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "yunnan-mine-twin"}

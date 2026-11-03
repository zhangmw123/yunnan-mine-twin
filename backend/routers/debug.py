"""前端诊断上报（仅用于本地排障，生产可移除）

前端通过 <img> GET 请求上报 JS 运行时错误与 Cesium 场景状态，
避免在无桌面会话中无法打开 DevTools 的问题。
"""
import json
import os
import time

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/debug", tags=["debug"])

LOG_PATH = os.environ.get("MINE_DIAG_LOG", r"D:/ynmine-pg/diag.log")


@router.get("/collect")
async def collect(type: str = Query("info"), msg: str = Query("")):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        line = json.dumps(
            {"t": time.strftime("%H:%M:%S"), "type": type, "msg": msg[:2000]},
            ensure_ascii=False,
        )
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    return {"code": 0}


@router.get("/last")
async def last(n: int = 200):
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return {"count": len(lines), "lines": [json.loads(x) for x in lines if x.strip()]}
    except FileNotFoundError:
        return {"count": 0, "lines": []}


@router.get("/clear")
async def clear():
    try:
        os.remove(LOG_PATH)
    except FileNotFoundError:
        pass
    return {"code": 0}

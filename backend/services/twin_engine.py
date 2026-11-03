"""
数字孪生实时引擎
- 矿卡沿矿区道路闭环轨迹平滑移动（每秒推送 WebSocket）
- GNSS 位移数据随机游走 + 降雨耦合模拟，异常点触发告警推送
"""
import asyncio
import json
import logging
import math
import random

from fastapi import WebSocket, WebSocketDisconnect

from core import database as db

random.seed(7)

# 孪生引擎自身日志：之前 tick 里一旦抛异常，整个循环会静默死掉，
# 前端表现为「矿卡一直不动、告警不来」，很难排查
_LOG_PATH = "D:/ynmine-pg/engine.log"
_logger = logging.getLogger("twin_engine")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    try:
        _h = logging.FileHandler(_LOG_PATH, encoding="utf-8")
        _h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(_h)
    except Exception:
        pass
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logger.addHandler(_sh)


MINE_LNG, MINE_LAT = 102.562, 24.715


def _dist_m(lng1, lat1, lng2, lat2):
    dx = (lng1 - lng2) * 111320.0 * math.cos(math.radians(lat1))
    dy = (lat1 - lat2) * 110540.0
    return math.hypot(dx, dy)


def _clip_to_mine(coords, lng, lat, radius_m):
    """截取折线中距 (lng,lat) radius 米内的最长连续段；无满足点返回 None"""
    best, cur = [], []
    for p in coords:
        if _dist_m(p[0], p[1], lng, lat) <= radius_m:
            cur.append(p)
            if len(cur) > len(best):
                best = list(cur)
        else:
            cur = []
    return best if len(best) >= 2 else None


def _interp_path(coords, step_m):
    """将折线按米步长插值，返回密集点序列"""
    lat0 = coords[0][1]
    deg_per_m_lat = 1.0 / 110540.0
    deg_per_m_lng = 1.0 / (111320.0 * math.cos(math.radians(lat0)))
    dense = []
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        dist = math.hypot((x2 - x1) / deg_per_m_lng, (y2 - y1) / deg_per_m_lat)
        n = max(1, int(dist / step_m))
        for k in range(n):
            t = k / n
            dense.append([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t])
    dense.append(coords[-1])
    return dense


class TwinEngine:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.vehicles = []          # 每台矿卡: {code, driver, path, idx, speed, elev_base}
        self.load_task = False
        self.tick_no = 0

    async def _load_vehicles(self):
        if self.vehicles:
            return
        rows = await db.fetch("SELECT id, vehicle_code, driver_name, speed_kmh FROM mine_vehicles ORDER BY id")
        # 轨迹必须落在矿区：OSM 道路含大量城镇街道，若直接取第一条路，
        # 矿卡会跑到 2.5km 外的昆阳镇街道上。
        # 取「几何与采场距离 < 600m」的道路中最长的一条（真正穿过采场的运输路），
        # 再按 900m 半径裁剪——不能按 1200m 取，否则选中的可能是仅擦边的过境路。
        main_road = await db.fetchrow(
            """SELECT ST_AsGeoJSON(geom) AS g, ST_Length(geom::geography) AS len
               FROM mine_roads
               WHERE ST_DWithin(geom::geography,
                     ST_SetSRID(ST_MakePoint(102.562, 24.715), 4326)::geography, 600)
               ORDER BY len DESC LIMIT 1""")
        if not main_road:
            main_road = await db.fetchrow(
                """SELECT ST_AsGeoJSON(geom) AS g FROM mine_roads
                   ORDER BY ST_Length(geom::geography) DESC LIMIT 1""")
        if not main_road:
            return
        coords = json.loads(main_road["g"])["coordinates"]
        # 一条长路可能从矿区穿出直通城镇：截取距采场 700m 内的连续路段，
        # 再拼成「去程+回程」的往返运输循环，保证矿卡始终在采场内作业。
        # 注意：OSM 折线顶点稀疏（常常 2km 一个顶点），必须加密后再裁剪，
        # 否则线上虽经过矿区但顶点都在圈外，裁剪会失败。
        dense = _interp_path(coords, 25.0) if len(coords) >= 2 else coords
        coords = _clip_to_mine(dense, MINE_LNG, MINE_LAT, 900.0) or coords
        loop = coords + coords[::-1] if len(coords) >= 2 else coords
        for i, r in enumerate(rows):
            offset = int(len(coords) * i / max(1, len(rows)))
            self.vehicles.append({
                "code": r["vehicle_code"], "driver": r["driver_name"],
                "path": _interp_path(loop + [loop[0]], 8.0),
                "idx": offset, "speed_kmh": float(r["speed_kmh"]),
                "load": random.choice(["满载磷矿石(95t)", "空载返回", "满载剥离物(88t)"]),
            })

    async def register(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)
        if not self.load_task:
            self.load_task = True
            await self._load_vehicles()

    def unregister(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)

    async def tick(self):
        """2 秒主循环：矿卡推进 + 传感器演化。单次异常不得中断整个循环"""
        _logger.info("twin engine tick loop started, vehicles=%d", len(self.vehicles))
        while True:
            try:
                await self._tick_once()
            except Exception:
                _logger.exception("tick 单次执行失败（循环继续）")
            await asyncio.sleep(2)

    async def _tick_once(self):
        self.tick_no += 1
        if self.vehicles:
            for v in self.vehicles:
                # 速度换算：每 2s 推进距离 = v(km/h)/3.6*2 米；轨迹点间距 8m
                # → 每次推进 v*2/(3.6*8) ≈ v*0.069 个索引（原写 v*2.8 会快 40 倍，看起来像瞬移）
                v["idx"] = (v["idx"] + max(1, round(v["speed_kmh"] * 0.069))) % len(v["path"])
                lng, lat = v["path"][v["idx"]]
                nxt = v["path"][(v["idx"] + 20) % len(v["path"])]
                heading = math.degrees(math.atan2(nxt[0] - lng, nxt[1] - lat)) % 360
                v["heading"] = heading
                # 高程由前端按真实地形采样贴地，后端不再写死 1955；
                # 仅更新平面位置与速度，保留各车原有 z（ST_Z(geom)）与 elevation_m
                await db.execute(
                    """UPDATE mine_vehicles SET speed_kmh=$1, updated_at=now(),
                       geom=ST_SetSRID(
                         ST_MakePoint($2, $3, COALESCE(ST_Z(geom), elevation_m)),
                         4326) WHERE vehicle_code=$4""",
                    round(v["speed_kmh"], 1), lng, lat, v["code"])
            await self.broadcast({
                "type": "VEHICLE_POSITION_UPDATE",
                "vehicles": [{"vehicle_code": v["code"], "driver_name": v["driver"],
                              "lng": v["path"][v["idx"]][0], "lat": v["path"][v["idx"]][1],
                              "alt": None, "heading": round(v.get("heading", 0), 1),
                              "speed": v["speed_kmh"], "load_status": v["load"]}
                             for v in self.vehicles]})
        # 传感器随机游走 + 告警检测
        alerts = await db.fetch(
            """SELECT sensor_code, name, disp_rate_mm_d, alert_status FROM mine_sensors
               WHERE alert_status >= 2""")
        for a in alerts:
            # 均值回归随机游走：围绕目标速率小幅波动。
            # 之前是「每 2 秒 +0.15」的单向累加，一分钟就能涨到 40+ mm/d，数据明显失真
            cur = float(a["disp_rate_mm_d"])
            target = 12.0 if a["alert_status"] == 3 else 6.5
            new_rate = round(min(20.0, max(0.5, cur + random.uniform(-0.5, 0.5) + (target - cur) * 0.08)), 2)
            status = 3 if new_rate >= 8.0 else 2 if new_rate >= 5.0 else 1 if new_rate >= 3.0 else 0
            # 注意：$1 在 SET 与算术表达式里会被 asyncpg 推断成不同类型（numeric vs float8），
            # 必须显式 cast，否则报 AmbiguousParameterError 并打断整个 tick 循环
            await db.execute(
                """UPDATE mine_sensors SET disp_rate_mm_d=$1::float8,
                   total_disp_mm=total_disp_mm+$1::float8*0.02::float8,
                   alert_status=$2::int, updated_at=now() WHERE sensor_code=$3""",
                new_rate, status, a["sensor_code"])
            # 告警广播做节流（每 10 个 tick ≈ 20 秒推一次），避免前端告警流刷屏
            if self.tick_no % 10 == 0:
                await self.broadcast({
                    "type": "SENSOR_ALERT",
                    "sensor_code": a["sensor_code"], "name": a["name"],
                    "disp_rate_mm_d": new_rate, "alert_status": status,
                    "message": f"【{'红色滑坡预警' if status == 3 else '橙色预警'}】{a['name']} 位移速率 {new_rate}mm/d",
                })


engine = TwinEngine()


async def ws_endpoint(ws: WebSocket):
    await engine.register(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "EVACUATE":
                await engine.broadcast({
                    "type": "EVACUATE_COMMAND",
                    "message": "【声光撤离指令】滑坡红色告警区内全部作业人员与矿卡立即撤离！",
                })
    except WebSocketDisconnect:
        engine.unregister(ws)

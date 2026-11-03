"""滑坡缓冲区影响分析与溃坝推演接口"""
import json

from fastapi import APIRouter
from pydantic import BaseModel

from core import database as db

router = APIRouter(prefix="/api/v1/mine", tags=["analysis"])


class LandslideImpactReq(BaseModel):
    sensor_code: str
    radii_meters: list[int] = [100, 300, 500]


@router.post("/spatial/landslide-impact")
async def landslide_impact(req: LandslideImpactReq):
    """对触发红色告警的边坡点做多环贴地缓冲区，并检索受威胁矿卡"""
    sensor = await db.fetchrow(
        "SELECT sensor_code, name, ST_X(geom) lng, ST_Y(geom) lat, ST_Z(geom) alt FROM mine_sensors WHERE sensor_code = $1",
        req.sensor_code)
    if not sensor:
        return {"code": 404, "msg": "sensor not found"}

    center = [sensor["lng"], sensor["lat"], sensor["alt"]]
    # PostGIS 地理坐标多环缓冲区：每个半径单独返回一个面要素，便于前端分级着色
    ring_rows = await db.fetch(
        """SELECT r.radius AS radius_m, ST_AsGeoJSON(ST_Buffer(s.geom::geography, r.radius)::geometry) AS geojson
           FROM mine_sensors s, unnest($2::float8[]) AS r(radius)
           WHERE s.sensor_code = $1
           ORDER BY r.radius DESC""", req.sensor_code, req.radii_meters)

    buffer_fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": json.loads(row["geojson"]),
            "properties": {"radius_m": row["radius_m"]},
        } for row in ring_rows if row["geojson"]],
    }

    # 检索缓冲区内受威胁的矿卡
    threatened = await db.fetch(
        """SELECT v.vehicle_code, v.driver_name, v.load_status,
                  round(ST_Distance(v.geom::geography, s.geom::geography)::numeric, 1) AS distance_m,
                  ST_X(v.geom) lng, ST_Y(v.geom) lat, ST_Z(v.geom) alt
           FROM mine_vehicles v, mine_sensors s
           WHERE s.sensor_code = $1
             AND ST_DWithin(v.geom::geography, s.geom::geography, $2)""",
        req.sensor_code, max(req.radii_meters))

    zones = ["核心滑塌红区", "冲击波及橙区", "警戒疏散黄区"]
    vehicles = []
    for v in threatened:
        dist = float(v["distance_m"])
        zone = zones[0] if dist <= req.radii_meters[0] else (
            zones[1] if dist <= req.radii_meters[1] else zones[2])
        vehicles.append({
            "vehicle_code": v["vehicle_code"], "driver_name": v["driver_name"],
            "load_status": v["load_status"], "distance_m": dist, "risk_zone": zone,
            "coordinates": [v["lng"], v["lat"], v["alt"]],
        })

    return {
        "code": 200,
        "data": {
            "sensor_code": req.sensor_code, "sensor_name": sensor["name"],
            "center": center,
            "buffer_polygons_geojson": buffer_fc,
            "threatened_vehicles": vehicles,
            "threatened_count": len(vehicles),
        },
    }


class DamBreachReq(BaseModel):
    start_elev_m: float = 1985
    max_elev_m: float = 2015
    rise_speed: float = 0.3   # 水位上涨速率，单位 m/min


@router.post("/spatial/dam-breach")
async def dam_breach(req: DamBreachReq):
    """尾矿库溃坝推演参数校验与淹没范围预估（三维动态渲染由前端水面 Entity 承担）"""
    tailings = await db.fetchrow(
        """SELECT name, ST_Area(geom::geography) / 1000000.0 AS area_km2, ST_AsGeoJSON(geom) AS geojson
           FROM mine_zones WHERE zone_type = 'tailings' LIMIT 1""")
    if not tailings:
        return {"code": 404, "msg": "no tailings pond found"}
    # 上涨速率以 m/min 计，直接相除得到分钟数
    est_minutes = round((req.max_elev_m - req.start_elev_m) / max(0.01, req.rise_speed), 1)
    return {
        "code": 200,
        "data": {
            "tailings_name": tailings["name"],
            "tailings_area_km2": round(float(tailings["area_km2"]), 2),
            "start_elev_m": req.start_elev_m, "max_elev_m": req.max_elev_m,
            "rise_speed": req.rise_speed, "estimated_duration_min": est_minutes,
            "polygon_geojson": json.loads(tailings["geojson"]),
        },
    }

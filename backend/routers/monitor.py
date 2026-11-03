"""水雨情与传感器监测接口"""
import json

from fastapi import APIRouter, Query

from core import database as db

router = APIRouter(prefix="/api/v1/mine", tags=["monitor"])


def _sensor_fc(rows):
    features = []
    for r in rows:
        coord = json.loads(r["geojson"])["coordinates"]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coord},
            "properties": {
                "sensor_code": r["sensor_code"], "name": r["name"],
                "sensor_type": r["sensor_type"], "elevation_m": r["elevation_m"],
                "disp_rate_mm_d": r["disp_rate_mm_d"], "total_disp_mm": r["total_disp_mm"],
                "water_pressure_kpa": r["water_pressure_kpa"], "alert_status": r["alert_status"],
                "zone_name": r["zone_name"],
                "warning_msg": (
                    f"【红色滑坡预警】位移速率达 {r['disp_rate_mm_d']}mm/d，进入加速蠕变阶段！"
                    if r["alert_status"] == 3 else
                    f"【橙色预警】位移速率 {r['disp_rate_mm_d']}mm/d 超过橙色阈值 5.0mm/d"
                    if r["alert_status"] == 2 else None),
            },
        })
    return {"type": "FeatureCollection", "features": features}


@router.get("/sensors")
async def get_sensors(
    sensor_type: str | None = Query(None, description="gnss / inclinometer / piezometer"),
    alert_only: bool = Query(False, description="仅返回告警点"),
):
    rows = await db.fetch(
        """
        SELECT s.sensor_code, s.name, s.sensor_type, s.elevation_m, s.disp_rate_mm_d,
               s.total_disp_mm, s.water_pressure_kpa, s.alert_status,
               COALESCE(z.name, '') AS zone_name,
               ST_AsGeoJSON(s.geom) AS geojson
        FROM mine_sensors s LEFT JOIN mine_zones z ON s.zone_id = z.id
        WHERE ($1::varchar IS NULL OR s.sensor_type = $1)
          AND ($2 = false OR s.alert_status >= 2)
        ORDER BY s.alert_status DESC, s.sensor_code
        """, sensor_type, alert_only)
    return _sensor_fc(rows)


@router.get("/sensors/{sensor_code}/timeseries")
async def get_timeseries(sensor_code: str, hours: int = 72):
    rows = await db.fetch(
        """SELECT to_char(recorded_at, 'YYYY-MM-DD HH24:MI') AS ts,
                  disp_rate_mm_d, total_disp_mm, rainfall_mm
           FROM sensor_timeseries WHERE sensor_code = $1
             AND recorded_at > now() - ($2 || ' hours')::interval
           ORDER BY recorded_at""", sensor_code, str(hours))
    if not rows:
        return {"sensor_code": sensor_code, "timestamps": [], "disp_rate_series": [],
                "total_disp_series": [], "rainfall_series": []}
    return {
        "sensor_code": sensor_code,
        "timestamps": [r["ts"] for r in rows],
        "disp_rate_series": [r["disp_rate_mm_d"] for r in rows],
        "total_disp_series": [r["total_disp_mm"] for r in rows],
        "rainfall_series": [r["rainfall_mm"] for r in rows],
    }


@router.get("/zones")
async def get_zones():
    rows = await db.fetch(
        """SELECT id, zone_code, name, zone_type, design_bench_angle,
                  current_min_elev, risk_level, ST_AsGeoJSON(geom) AS geojson
           FROM mine_zones ORDER BY id""")
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": json.loads(r["geojson"]),
        "properties": {"id": r["id"], "zone_code": r["zone_code"], "name": r["name"],
                       "zone_type": r["zone_type"], "design_bench_angle": r["design_bench_angle"],
                       "current_min_elev": r["current_min_elev"], "risk_level": r["risk_level"]},
    } for r in rows]}


@router.get("/roads")
async def get_roads():
    rows = await db.fetch(
        "SELECT id, name, road_class, ST_AsGeoJSON(geom) AS geojson FROM mine_roads ORDER BY id")
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature",
        "geometry": json.loads(r["geojson"]),
        "properties": {"id": r["id"], "name": r["name"], "road_class": r["road_class"]},
    } for r in rows]}


@router.get("/overview")
async def get_overview():
    row = await db.fetchrow(
        """SELECT
             (SELECT count(*) FROM mine_sensors) AS total_sensors,
             (SELECT count(*) FROM mine_sensors WHERE alert_status = 3) AS red_alerts,
             (SELECT count(*) FROM mine_sensors WHERE alert_status = 2) AS orange_alerts,
             (SELECT count(*) FROM mine_vehicles) AS vehicles,
             (SELECT count(*) FROM mine_zones) AS zones""")
    return dict(row)

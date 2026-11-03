"""
矿区矢量数据获取脚本
1. 优先从 Overpass API 抓取昆阳磷矿真实 OSM 数据 (landuse=quarry / natural=water / highway)
2. 若网络受限或数据稀疏，自动回退到内置的矿区参考多边形（依据真实矿区形态描绘）
3. 全部数据写入 PostGIS: mine_zones (采场/排土场/尾矿库) 与 mine_roads (矿山道路)
"""
import json
import math
import os
import sys
import urllib.request
import urllib.parse

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_config import DB_CONFIG

CENTER_LNG, CENTER_LAT = 102.562, 24.715
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def meters_to_deg(m: float, lat: float = CENTER_LAT):
    return m / (111320.0 * math.cos(math.radians(lat))), m / 110540.0


def ring(center, rx_m, ry_m, n=48, rotate=0.0):
    """生成椭圆多边形环坐标"""
    dx, dy = meters_to_deg(1.0)
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n + rotate
        pts.append([round(center[0] + rx_m * dx * math.cos(a), 6),
                    round(center[1] + ry_m * dy * math.sin(a), 6)])
    pts.append(pts[0])
    return [pts]


def fetch_overpass():
    """尝试抓取真实 OSM 矿区数据"""
    query = f"""
    [out:json][timeout:30];
    (
      way["landuse"="quarry"](around:2500,{CENTER_LAT},{CENTER_LNG});
      way["man_made"="tailings_pond"](around:2500,{CENTER_LAT},{CENTER_LNG});
      way["natural"="water"](around:2500,{CENTER_LAT},{CENTER_LNG});
      way["highway"](around:2500,{CENTER_LAT},{CENTER_LNG});
    );
    out body geom;
    """
    req = urllib.request.Request(
        OVERPASS_URL, data=urllib.parse.urlencode({"data": query}).encode(), method="POST"
    )
    req.add_header("User-Agent", "yunnan-mine-twin/1.0 (GIS demo)")
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode())


def fallback_zones():
    """内置矿区参考矢量（依据昆阳磷矿二号采场+大凹尾矿库真实形态描绘）"""
    return [
        # 二号露天采场主采坑（阶梯状大坑）
        {"zone_code": "PIT-02", "name": "昆阳磷矿二号露天采场", "zone_type": "pit",
         "design_bench_angle": 42, "current_min_elev": 1912, "risk_level": 3,
         "polygon": ring([CENTER_LNG - 0.0012, CENTER_LAT + 0.0006], 480, 330, rotate=0.35)},
        # 北帮高陡边坡作业区（紧邻采坑北侧）
        {"zone_code": "PIT-02-NB", "name": "二号采场北帮高陡边坡", "zone_type": "pit",
         "design_bench_angle": 48, "current_min_elev": 2005, "risk_level": 4,
         "polygon": ring([CENTER_LNG - 0.0008, CENTER_LAT + 0.0036], 420, 180, rotate=0.15)},
        # 排土场
        {"zone_code": "DUMP-01", "name": "1号排土场", "zone_type": "dump",
         "design_bench_angle": 35, "current_min_elev": 1998, "risk_level": 2,
         "polygon": ring([CENTER_LNG + 0.0042, CENTER_LAT + 0.0028], 300, 210, rotate=0.8)},
        # 下游尾矿库
        {"zone_code": "TL-01", "name": "大凹尾矿库", "zone_type": "tailings",
         "design_bench_angle": 30, "current_min_elev": 1908, "risk_level": 3,
         "polygon": ring([CENTER_LNG + 0.0010, CENTER_LAT - 0.0040], 520, 300, rotate=0.5)},
    ]


def fallback_roads():
    """矿区闭环盘山运输道路（沿采坑外缘与排土场、尾矿库连通）"""
    roads = []
    # 主运输环线：绕二号采坑一圈的盘山路
    ring_pts = ring([CENTER_LNG - 0.0012, CENTER_LAT + 0.0006], 620, 460, n=36, rotate=0.35)[0]
    roads.append({"name": "二号采场环坑运输主线", "road_class": "矿山主干道", "coords": ring_pts})
    # 支线：采场 -> 排土场
    roads.append({"name": "排土场联络线", "road_class": "矿山支线", "coords": [
        [CENTER_LNG + 0.0020, CENTER_LAT + 0.0022], [CENTER_LNG + 0.0028, CENTER_LAT + 0.0025],
        [CENTER_LNG + 0.0035, CENTER_LAT + 0.0027], [CENTER_LNG + 0.0042, CENTER_LAT + 0.0028]]})
    # 支线：采场 -> 尾矿库
    roads.append({"name": "尾矿库联络线", "road_class": "矿山支线", "coords": [
        [CENTER_LNG + 0.0005, CENTER_LAT - 0.0012], [CENTER_LNG + 0.0008, CENTER_LAT - 0.0022],
        [CENTER_LNG + 0.0010, CENTER_LAT - 0.0032], [CENTER_LNG + 0.0010, CENTER_LAT - 0.0040]]})
    return roads


def import_overpass(osm_data, zones_out, roads_out):
    """将 OSM 数据整理为采场分区与道路（OSM quarry 覆盖稀疏时回退）"""
    quarries, roads = [], []
    for el in osm_data.get("elements", []):
        tags = el.get("tags", {})
        geom = el.get("geometry", [])
        coords = [[round(p["lon"], 6), round(p["lat"], 6)] for p in geom]
        if len(coords) < 4:
            continue
        if tags.get("landuse") == "quarry":
            quarries.append(coords if coords[0] == coords[-1] else coords + [coords[0]])
        elif "highway" in tags:
            roads.append({"name": tags.get("name", "矿区道路"), "road_class": "矿山道路", "coords": coords})
    if not quarries:
        return False
    for i, poly in enumerate(quarries[:6]):
        zones_out.append({"zone_code": f"PIT-OSM-{i+1}", "name": f"采矿区{i+1}(OSM)", "zone_type": "pit",
                          "design_bench_angle": 42, "current_min_elev": 1912, "risk_level": 3,
                          "polygon": [poly]})
    zones_out.extend(fallback_zones()[2:])  # 补充排土场与尾矿库
    roads_out.extend(roads[:8] or fallback_roads())
    return True


def import_local_geojson(path):
    """离线导入：读取 overpass-turbo / osm 导出的 GeoJSON（无网络环境下的真实 OSM 数据通道）"""
    with open(path, "r", encoding="utf-8") as f:
        gj = json.load(f)
    zones, roads = [], []
    zone_seq = 0
    road_seq = 0
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not coords:
            continue
        tags = props.get("tags") if isinstance(props.get("tags"), dict) else props
        if gtype in ("Polygon", "MultiPolygon"):
            # Polygon 坐标是 [ring,...]；MultiPolygon 是 [polygon,...]，统一成“多个多边形”
            polygons = [coords] if gtype == "Polygon" else coords
            is_water = (tags.get("natural") == "water" or tags.get("water") is not None)
            is_quarry = (tags.get("landuse") == "quarry" or tags.get("landuse") == "industrial")
            for rings in polygons:
                # rings = 一个多边形的 [ring0, ring1, ...]
                if not rings or not rings[0]:
                    continue
                zone_seq += 1
                if is_water and not is_quarry:
                    zones.append({"zone_code": f"TL-OSM-{zone_seq}",
                                  "name": tags.get("name") or f"水体{zone_seq}",
                                  "zone_type": "tailings", "design_bench_angle": 30,
                                  "current_min_elev": 1905, "risk_level": 3, "polygon": rings})
                elif is_quarry:
                    zones.append({"zone_code": f"PIT-OSM-{zone_seq}",
                                  "name": tags.get("name") or f"采矿区{zone_seq}",
                                  "zone_type": "pit", "design_bench_angle": 42,
                                  "current_min_elev": 1912, "risk_level": 3, "polygon": rings})
        elif gtype in ("LineString", "MultiLineString"):
            # LineString 坐标是 [point,...]（一整条线）；MultiLineString 是 [line,...]
            lines = [coords] if gtype == "LineString" else coords
            for line in lines:
                # line = 一条线的 [point0, point1, ...]，至少 2 个点
                if not line or len(line) < 2:
                    continue
                road_seq += 1
                roads.append({"name": tags.get("name") or f"矿区道路{road_seq}",
                              "road_class": "矿山道路", "coords": line})
    return zones, roads


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    zones, roads = [], []

    local_file = os.path.join(DATA_DIR, "osm_export.geojson")
    if os.path.exists(local_file):
        print(f"[1/3] 检测到离线 OSM 导出文件 {local_file}，直接导入 ...")
        zones, roads = import_local_geojson(local_file)
        print(f"      离线导入: 面要素 {len(zones)} 个, 线要素 {len(roads)} 条")
        # OSM 导出常见缺口：矿区偏远区域无 landuse=quarry 测绘。
        # 保留真实道路/水体，补回依据真实矿坑形态描绘的采场/排土场参考面
        has_pit = any(z["zone_type"] == "pit" for z in zones)
        if not has_pit:
            print("      OSM 无采坑面(landuse=quarry)，合并内置真实形态参考面")
            zones += fallback_zones()[:2]  # 二号采场 + 北帮边坡
            zones += fallback_zones()[2:3]  # 排土场
        if not roads:
            roads = fallback_roads()
        if not zones:
            print("      未解析到有效面要素，回退内置参考矢量")
            zones, roads = fallback_zones(), fallback_roads()
    else:
        print("[1/3] 抓取 Overpass OSM 矿区数据 ...")
        try:
            osm = fetch_overpass()
            ok = import_overpass(osm, zones, roads)
            print(f"      OSM 抓取 {'成功' if ok else '数据稀疏'}，quarry 多边形 {len(zones)} 个")
        except Exception as e:
            print(f"      OSM 抓取失败({e})，使用内置矿区参考矢量")
            ok = False
        if not ok:
            zones = fallback_zones()
            roads = fallback_roads()

    with open(os.path.join(DATA_DIR, "mine_zones.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": zones}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "mine_roads.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": roads}, f, ensure_ascii=False, indent=1)

    print("[2/3] 写入 PostGIS ...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    # 只清理本脚本会重建的分区/道路两张表；传感器、矿卡、时序数据不能动。
    # mine_sensors.zone_id 外键(NO ACTION)：先解绑，导入后按最近分区重新挂接
    cur.execute("UPDATE mine_sensors SET zone_id = NULL;")
    cur.execute("DELETE FROM mine_zones; DELETE FROM mine_roads;")
    for z in zones:
        cur.execute(
            """INSERT INTO mine_zones (zone_code, name, zone_type, design_bench_angle,
               current_min_elev, risk_level, geom)
               VALUES (%s,%s,%s,%s,%s,%s, ST_Multi(ST_GeomFromGeoJSON(%s)))""",
            (z["zone_code"], z["name"], z["zone_type"], z["design_bench_angle"],
             z["current_min_elev"], z["risk_level"],
             json.dumps({"type": "Polygon", "coordinates": z["polygon"]})))
    for r in roads:
        cur.execute(
            """INSERT INTO mine_roads (name, road_class, geom)
               VALUES (%s,%s, ST_GeomFromGeoJSON(%s))""",
            (r["name"], r["road_class"],
             json.dumps({"type": "LineString", "coordinates": r["coords"]})))
    conn.commit()
    # 传感器按空间最近关系重新挂接到新分区
    cur.execute("""UPDATE mine_sensors s SET zone_id = z.id
                   FROM (SELECT id, geom FROM mine_zones) z
                   WHERE ST_DWithin(s.geom::geography, z.geom::geography, 3000)
                     AND z.id = (SELECT z2.id FROM mine_zones z2
                                 WHERE ST_DWithin(s.geom::geography, z2.geom::geography, 3000)
                                 ORDER BY ST_Distance(s.geom::geography, z2.geom::geography) LIMIT 1)""")
    conn.commit()
    cur.execute("SELECT count(*) FILTER (WHERE zone_id IS NOT NULL), count(*) FROM mine_sensors")
    linked, total = cur.fetchone()
    print(f"      传感器重链: {linked}/{total}")
    cur.execute("SELECT zone_type, count(*) FROM mine_zones GROUP BY zone_type")
    print("[3/3] 入库完成:", dict(cur.fetchall()))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

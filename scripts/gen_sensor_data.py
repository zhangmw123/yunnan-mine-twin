"""
传感器数据生成脚本
- 沿二号采场北帮/东帮高陡台阶边缘布设 50 个监测点 (GNSS 32 + 测斜仪 8 + 渗压计 10)
- 参考国标 GB/T 51214《露天煤矿边坡监测技术规范》设定预警阈值
- 生成近 72 小时时序数据：正常点平稳随机游走，1 个红色告警点呈 S 型加速蠕变
- 写入 PostGIS: mine_sensors / sensor_timeseries / mine_vehicles
"""
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_config import DB_CONFIG

random.seed(42)
CENTER_LNG, CENTER_LAT = 102.562, 24.715
NOW = datetime.now().replace(minute=0, second=0, microsecond=0)


def m2deg(m):
    return m / (111320.0 * math.cos(math.radians(CENTER_LAT))), m / 110540.0


def point_on_ellipse(cx, cy, rx_m, ry_m, angle_deg, rotate_deg):
    dx, dy = m2deg(1.0)
    a = math.radians(angle_deg) + math.radians(rotate_deg)
    return [round(cx + rx_m * dx * math.cos(a), 6), round(cy + ry_m * dy * math.sin(a), 6)]


def gen_sensors():
    sensors = []
    # 北帮高陡边坡台阶（重点监测区，海拔 2005~2035m）
    for i in range(18):
        p = point_on_ellipse(CENTER_LNG - 0.0012, CENTER_LAT + 0.0006, 470, 320, 40 + i * 6, 0.35)
        elev = 2005 + (i % 6) * 6 + random.uniform(-1, 1)
        sensors.append({"code": f"GNSS-N-{i+1:02d}", "name": f"二号采场北帮 {int(elev)}m 台阶 GNSS 站",
                        "type": "gnss", "elev": elev, "pos": p})
    # 东帮台阶
    for i in range(14):
        p = point_on_ellipse(CENTER_LNG - 0.0012, CENTER_LAT + 0.0006, 470, 320, -60 + i * 10, 0.35)
        elev = 1980 + (i % 5) * 7 + random.uniform(-1, 1)
        sensors.append({"code": f"GNSS-E-{i+1:02d}", "name": f"二号采场东帮 {int(elev)}m 台阶 GNSS 站",
                        "type": "gnss", "elev": elev, "pos": p})
    # 深部测斜仪
    for i in range(8):
        p = point_on_ellipse(CENTER_LNG - 0.0012, CENTER_LAT + 0.0006, 440, 300, 25 + i * 17, 0.35)
        sensors.append({"code": f"INCL-{i+1:02d}", "name": f"北帮深部测斜仪 {i+1}号孔",
                        "type": "inclinometer", "elev": 2010 + i * 4, "pos": p})
    # 渗压计（尾矿坝 + 采坑内）
    for i in range(6):
        p = point_on_ellipse(CENTER_LNG + 0.0010, CENTER_LAT - 0.0040, 500, 290, i * 55 + 10, 0.5)
        sensors.append({"code": f"PIEZO-T-{i+1:02d}", "name": f"大凹尾矿坝渗压计 T{i+1}",
                        "type": "piezometer", "elev": 1912 + i * 3, "pos": p})
    for i in range(4):
        p = point_on_ellipse(CENTER_LNG - 0.0012, CENTER_LAT + 0.0006, 380, 250, 100 + i * 40, 0.35)
        sensors.append({"code": f"PIEZO-P-{i+1:02d}", "name": f"采坑内疏干渗压计 P{i+1}",
                        "type": "piezometer", "elev": 1930 + i * 5, "pos": p})
    return sensors


def s_curve(t_frac, peak):
    """S 型加速蠕变曲线 (Logistic)"""
    return peak / (1 + math.exp(-10 * (t_frac - 0.62)))


def gen_timeseries(code, is_alarm):
    rows = []
    disp, rate = 18.0, 0.4
    for h in range(72, -1, -1):
        ts = NOW - timedelta(hours=h)
        # 72h 内有一场强降雨（第 40~52 小时）
        rain = max(0.0, random.gauss(14, 4)) if 40 <= (72 - h) <= 52 else max(0.0, random.gauss(0.5, 0.4))
        if is_alarm:
            frac = (72 - h) / 72.0
            rate = round(0.4 + s_curve(frac, 12.2) + random.uniform(-0.25, 0.25), 2)
            disp += rate
        else:
            rate = round(max(0.05, rate + random.uniform(-0.08, 0.08)), 2)
            disp += rate * random.uniform(0.8, 1.2)
        rows.append((code, ts, rate, round(disp, 1), round(rain, 1)))
    return rows


def main():
    sensors = gen_sensors()
    # 指定 GNSS-N-08 为红色加速蠕变告警点
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT id, zone_type FROM mine_zones")
    zone_map = {zt: zid for zid, zt in cur.fetchall()}

    ts_rows = []
    for s in sensors:
        is_alarm = s["code"] == "GNSS-N-08"
        last = gen_timeseries(s["code"], is_alarm)[-1]
        rate, disp = last[2], last[3]
        kpa = round(random.uniform(180, 320), 1) if s["type"] == "piezometer" else 0.0
        if is_alarm:
            status = 3
        elif rate >= 5.0:
            status = 2
        elif rate >= 3.0:
            status = 1
        else:
            status = 0
        zone_id = zone_map.get("tailings") if s["type"] == "piezometer" and "尾矿" in s["name"] else zone_map.get("pit")
        cur.execute(
            """INSERT INTO mine_sensors (sensor_code, name, sensor_type, zone_id, elevation_m,
               disp_rate_mm_d, total_disp_mm, water_pressure_kpa, alert_status, geom)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s,%s),4326))""",
            (s["code"], s["name"], s["type"], zone_id, s["elev"], rate, disp, kpa, status,
             s["pos"][0], s["pos"][1], s["elev"]))
        ts_rows.extend(gen_timeseries(s["code"], is_alarm))

    cur.executemany(
        "INSERT INTO sensor_timeseries (sensor_code, recorded_at, disp_rate_mm_d, total_disp_mm, rainfall_mm) VALUES (%s,%s,%s,%s,%s)",
        ts_rows)

    # 矿卡（沿环坑运输主线行驶，位置由后端 WebSocket 驱动）
    drivers = ["张建国", "李卫东", "王志强", "赵有田", "杨春林", "段永康"]
    for i in range(6):
        cur.execute(
            """INSERT INTO mine_vehicles (vehicle_code, driver_name, speed_kmh, load_status, elevation_m, geom)
               VALUES (%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s,1950),4326))""",
            (f"TRUCK-YN-{101+i}", drivers[i], round(random.uniform(15, 30), 1),
             random.choice(["满载磷矿石(95t)", "空载返回", "满载剥离物(88t)"]),
             round(random.uniform(1940, 2010), 1), CENTER_LNG, CENTER_LAT))

    conn.commit()
    cur.execute("SELECT alert_status, count(*) FROM mine_sensors GROUP BY alert_status ORDER BY alert_status")
    print(f"✅ 传感器 {len(sensors)} 个入库，时序 {len(ts_rows)} 条，矿卡 6 台")
    print("   告警分布(0正常/1关注/2预警/3告警):", dict(cur.fetchall()))
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()

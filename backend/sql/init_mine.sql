CREATE EXTENSION IF NOT EXISTS postgis;

-- 1. 矿区功能分区表 (采场、排土场、尾矿库、选矿厂办公区)
CREATE TABLE IF NOT EXISTS mine_zones (
    id SERIAL PRIMARY KEY,
    zone_code VARCHAR(32) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,           -- 如：昆阳磷矿二号露天采场、大凹尾矿库
    zone_type VARCHAR(32) NOT NULL,       -- 'pit'(采场) / 'tailings'(尾矿库) / 'dump'(排土场)
    design_bench_angle DOUBLE PRECISION,  -- 设计台阶坡面角(度)
    current_min_elev DOUBLE PRECISION,    -- 当前最低开采标高(m)
    risk_level INTEGER DEFAULT 1,         -- 1:低风险 2:中风险 3:高风险 4:极高危
    geom GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX idx_mine_zones_geom ON mine_zones USING GIST (geom);

-- 2. 边坡与尾矿坝物联网传感器点位表 (三维坐标 PointZ，含真实海拔高程)
CREATE TABLE IF NOT EXISTS mine_sensors (
    id SERIAL PRIMARY KEY,
    sensor_code VARCHAR(32) UNIQUE NOT NULL, -- 如：GNSS-N-01, RADAR-01, PIEZO-T-03
    name VARCHAR(128) NOT NULL,
    sensor_type VARCHAR(32) NOT NULL,        -- 'gnss'(表面位移) / 'inclinometer'(深部测斜) / 'piezometer'(渗压计)
    zone_id INTEGER REFERENCES mine_zones(id),
    elevation_m DOUBLE PRECISION NOT NULL,   -- 传感器安装海拔高度(m)
    disp_rate_mm_d DOUBLE PRECISION DEFAULT 0.2, -- 当前位移速率(mm/d)
    total_disp_mm DOUBLE PRECISION DEFAULT 5.0,  -- 累计位移量(mm)
    water_pressure_kpa DOUBLE PRECISION DEFAULT 0.0, -- 渗压计孔隙水压力(kPa)
    threshold_orange DOUBLE PRECISION DEFAULT 5.0,   -- 橙色预警阈值(mm/d)
    threshold_red DOUBLE PRECISION DEFAULT 8.0,      -- 红色滑坡阈值(mm/d)
    alert_status INTEGER DEFAULT 0,          -- 0:正常 1:蓝色关注 2:橙色预警 3:红色告警
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    geom GEOMETRY(PointZ, 4326)              -- 带 Z 值高程的三维点
);
CREATE INDEX idx_mine_sensors_geom ON mine_sensors USING GIST (geom);

-- 3. 传感器历史时序监测记录表 (用于绘制 ECharts S型蠕变曲线)
CREATE TABLE IF NOT EXISTS sensor_timeseries (
    id BIGSERIAL PRIMARY KEY,
    sensor_code VARCHAR(32) NOT NULL,
    recorded_at TIMESTAMP NOT NULL,
    disp_rate_mm_d DOUBLE PRECISION,
    total_disp_mm DOUBLE PRECISION,
    rainfall_mm DOUBLE PRECISION DEFAULT 0.0
);
CREATE INDEX idx_sensor_time ON sensor_timeseries (sensor_code, recorded_at DESC);

-- 4. 矿山作业车辆与人员实时位置表
CREATE TABLE IF NOT EXISTS mine_vehicles (
    id SERIAL PRIMARY KEY,
    vehicle_code VARCHAR(32) UNIQUE NOT NULL, -- 如：TRUCK-YN-101 (百吨级自卸矿卡)
    driver_name VARCHAR(64),
    vehicle_type VARCHAR(32) DEFAULT 'mining_truck',
    speed_kmh DOUBLE PRECISION DEFAULT 25.0,
    load_status VARCHAR(32) DEFAULT '满载磷矿石(95t)',
    elevation_m DOUBLE PRECISION DEFAULT 1950.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    geom GEOMETRY(PointZ, 4326)
);
CREATE INDEX idx_mine_vehicles_geom ON mine_vehicles USING GIST (geom);

-- 5. 矿区内部运输道路表 (由 Overpass OSM / 参考矢量导入)
CREATE TABLE IF NOT EXISTS mine_roads (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128),
    road_class VARCHAR(32) DEFAULT '矿山道路',
    geom GEOMETRY(LineString, 4326)
);
CREATE INDEX idx_mine_roads_geom ON mine_roads USING GIST (geom);

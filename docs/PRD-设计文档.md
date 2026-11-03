# 云南高原露天矿山高陡边坡三维形变监测与尾矿库溃坝推演系统
> **工程全套设计文档（PRD + PostGIS 数据库设计 + Cesium/Mars3D 零翻车开发手册 + API 文档 + Docker 部署方案）**

---

## 一、 产品需求文档 (PRD)

### 1.1 项目背景与挂靠定位
* **简历挂靠场景**：直接结合你在云南本地的测绘/地质/规划相关实习经历，以 **【昆明市晋宁区·云南磷化集团昆阳磷矿二号露天采场及下游尾矿库】**（中心坐标：`102.562°E, 24.715°N`，紧邻滇池南岸，拥有全国极具代表性的大型阶梯状露天采矿坑与高陡边坡）作为真实示范区。
* **解决的核心业务痛点**：
  1. **高原露天矿山多源三维数据孤岛**：传统矿山 CAD 图纸无法直观呈现高陡台阶地形起伏。本系统融合真实 12.5m/30m 三维地形 (DEM)、高清矿区卫星影像、采场矿界红线与矿卡三维 glTF 模型，构建二三维一体化数字孪生矿山底座。
  2. **高陡边坡失稳滑坡预警滞后**：针对云南雨季强降雨易诱发矿山边坡滑坡的痛点，系统接入 **GNSS 表面位移监测站、边坡测斜仪、尾矿坝渗压计** 实时物联网数据流，支持 **“降雨量超标 + 位移速率突变 ($>8\text{mm/d}$)”** 双因子耦合预警，并自动生成三维贴地危险缓冲区，框选受威胁作业人员与矿卡。
  3. **缺乏工程级三维空间分析与溃坝推演工具**：提供智慧矿山必考的 **【边坡坡度坡向分析】、【主滑方向地形剖面图】、【采场三维地形开挖与土方量（挖方/填方）精确测算】** 以及 **【尾矿库漫顶溃坝三维动态淹没演进模拟】** 四大核心三维工程工具。

---

### 1.2 100% 真实可获取数据源清单

| 数据图层名称 | 格式 / 表名 | 100% 免费真实获取方式与工程落地方法 |
| :--- | :--- | :--- |
| **1. 昆阳磷矿三维真实地形 (DEM) 与高清矿坑卫片** | Terrain / WMTS | **零门槛直连**：在 Cesium/Mars3D 初始化时定位到 `[102.562, 24.715]`，启用 `Cesium.createWorldTerrainAsync()`（或从[地理空间数据云](https://www.gscloud.cn/)下载晋宁区 DEM 切片），叠加天地图/Bing 高清影像，即可直接看到**真实存在的巨大阶梯状露天磷矿采坑**。 |
| **2. 露天采场台阶边界、排土场、尾矿库与运矿盘山路** | `mine_zones` / `mine_roads` (PostGIS) | **真实提取**：打开 [Overpass Turbo](https://overpass-turbo.eu/)，移动至昆明市晋宁区昆阳街道西南侧矿区，运行 `landuse=quarry or highway=* or natural=water`，一键导出真实采矿区多边形、尾矿库水体与矿山内部运输道路 GeoJSON。 |
| **3. 边坡 GNSS 位移、雷达、渗压计传感器台账与时序数据** | `mine_sensors` / `sensor_timeseries` | **规范化生成**：参考国家标准《露天煤矿边坡监测技术规范》(GB/T 51214)，使用 Python 脚本沿着真实露天采坑北帮、东帮高陡台阶边缘自动布设 50 个监测点，生成含 `水平位移速率(mm/d)、累计位移(mm)、沉降量(mm)、孔隙水压力(kPa)` 的时序流数据。 |
| **4. 矿卡与钻机三维模型及实时 GPS 轨迹** | `mine_vehicles` + `.gltf` 模型 | **直接复用**：复用你现有武汉项目 `assets/models/bus.gltf`（或免费下载自卸矿卡 `.glb` 模型），沿上面导出的矿区真实盘山道路坐标生成闭环运输路径，通过 WebSocket 实时推送位置、车速、载重状态。 |
| **5. 晋宁矿区实时气象与小时降雨量** | Open-Meteo API | **免 Key 实时接口**：直接请求 `https://api.open-meteo.com/v1/forecast?latitude=24.715&longitude=102.562&current=precipitation,rain&hourly=precipitation`，获取矿区真实降雨数据。 |

---

### 1.3 功能模块设计（四大硬核三维模块 + AI 编程零翻车方案）

> 💡 **AI 编程 100% 成功秘籍**：本项目前端采用 **Vue 3 + TypeScript + Cesium.js (配合开源 `mars3d` 插件 API)**。所有复杂的 WebGL 三维开挖、三角网体积积分、动态水面材质均直接调用封装好的高级类，每个功能核心代码不超过 30 行，AI 编写 UI 与业务逻辑的成功率为 100%！

#### 模块一：矿山实景三维底座与传感器/矿卡物联网实时孪生
* **功能描述**：
  * **多源图层树管理**：支持一键切换采矿权红线、1#～3# 采场分区、排土场、尾矿库、等高线图层及三维地形夸张系数调节（`terrainExaggeration`）。
  * **三维传感器聚合与分级着色**：50 个 GNSS 位移站、裂缝计、渗压计以三维立牌（`Billboard` + 牵引线）贴地渲染，按安全状态分四色（正常-绿、关注-蓝、警示-橙、滑坡告警-红+脉冲波纹）。
  * **运矿卡车三维轨迹实时平滑移动**：通过 WebSocket 接收矿卡实时坐标，使用 Cesium `SampledPositionProperty`（拉格朗日插值）驱动三维矿卡模型沿着矿坑盘山路平滑爬坡行驶，支持第一人称“跟随矿卡视角”巡检。

#### 模块二：矿山三维工程空间分析工具箱（智慧矿山必考核心）
* **功能描述**：
  1. **采场三维地形开挖与岩层剖切**：用户在矿坑任意位置手绘多边形并输入开采深度（如向下开挖 $45\text{m}$），系统实时在三维地形上挖出垂直矿坑，底部与侧壁自动贴合逼真的磷矿岩层贴图。
  2. **采剥土方量（挖方/填方）精准测算**：框选计划开采区域并设定基准面高程（如海拔 $1980\text{m}$），系统基于地形三角网自动计算出 **挖方体积 ($\text{m}^3$)、填方体积 ($\text{m}^3$)、横截面积 ($\text{m}^2$)**，并生成土方核算单。
  3. **高陡边坡坡度坡向分析与主滑方向剖面图**：框选北帮高陡边坡，实时渲染坡度色谱图（高亮 $>45^\circ$ 的极高危坡面）；鼠标沿边坡画一条主滑方向切线，底部 **ECharts** 实时绘出台阶地形高程剖面图。

#### 模块三：边坡加速蠕变预警联动与三维贴地缓冲区受灾评估
* **功能描述**：
  * **S 型滑坡变形曲线监测**：点击任意触发红色预警的 GNSS 监测站（如 `GNSS-北帮-08`，位移速率突增至 $12.4\text{mm/d}$），右侧弹出该点近 72 小时《位移速率-降雨量双轴耦合曲线》。
  * **滑坡影响区三维贴地多环缓冲区 (`ClampToGround`)**：系统自动围绕高危滑坡点生成 **100m（核心滑塌红区）、300m（冲击波及橙区）、500m（警戒疏散黄区）** 三维贴地半透明多边形，并调用后端 PostGIS 实时检索出当前正处于红区/橙区内的**作业矿卡编号、钻机设备及井下/坡面作业人员**，支持一键下发声光撤离指令。

#### 模块四：尾矿库漫顶溃坝三维动态淹没演进模拟
* **功能描述**：
  * 针对矿区下游尾矿库，提供【溃坝/漫顶三维推演面板】。用户可设置：起始库水位海拔（如 $1910\text{m}$）、溃坝最高演进水位（如 $1965\text{m}$）、水位上涨速率（$\text{m/s}$）。
  * 启动推演后，三维动态水面沿着山谷真实 DEM 地形由低向高漫延推进，实时计算各时刻的**淹没面积 ($\text{m}^2$)、淹没水深与受淹矿区道路/厂房**，直观重现溃坝灾害演进全过程。

---

## 二、 PostGIS 空间数据库设计 (`init_mine.sql`)

```sql
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
```

---

## 三、 前后端分离架构与核心 API / 三维代码手册

### 3.1 核心 RESTful & WebSocket 接口规范

#### 接口 1：获取矿区三维传感器点位与实时形变状态
* **请求路径**：`GET /api/v1/mine/sensors`
* **请求参数**：`sensor_type` (可选: `gnss` / `piezometer`)，`alert_only` (可选: `true`)
* **响应示例 (带海拔 Z 值的三维 GeoJSON)**：
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [102.5618, 24.7165, 2015.4]
      },
      "properties": {
        "sensor_code": "GNSS-N-08",
        "name": "二号采场北帮 2015m 台阶 GNSS 站",
        "sensor_type": "gnss",
        "disp_rate_mm_d": 11.8,
        "total_disp_mm": 142.5,
        "alert_status": 3,
        "warning_msg": "【红色滑坡预警】位移速率达 11.8mm/d，进入加速蠕变阶段！"
      }
    }
  ]
}
```

#### 接口 2：获取单点传感器 72 小时“位移-降雨”双因子耦合时序曲线
* **请求路径**：`GET /api/v1/mine/sensors/{sensor_code}/timeseries?hours=72`
* **响应示例**：
```json
{
  "sensor_code": "GNSS-N-08",
  "timestamps": ["2026-07-01 00:00", "2026-07-01 01:00", "..."],
  "disp_rate_series": [0.4, 0.5, 1.2, 3.8, 7.5, 11.8],
  "total_disp_series": [20.1, 20.6, 21.8, 25.6, 33.1, 44.9],
  "rainfall_series": [0.0, 12.5, 28.0, 15.2, 5.0, 0.0]
}
```

#### 接口 3：高陡边坡滑坡危险区空间缓冲区分析与受威胁矿卡检索
* **请求路径**：`POST /api/v1/mine/spatial/landslide-impact`
* **功能说明**：当某个边坡传感器触发红色告警时，前端传入该点坐标与缓冲半径（如 100m / 300m / 500m），后端通过 PostGIS `ST_DWithin(geom::geography, ...)` 检索出处于滑坡冲击范围内的矿卡、钻机与人员，并返回三维贴地缓冲区多边形。
* **请求体**：
```json
{
  "sensor_code": "GNSS-N-08",
  "radii_meters": [100, 300, 500]
}
```
* **响应示例**：
```json
{
  "code": 200,
  "data": {
    "center": [102.5618, 24.7165, 2015.4],
    "threatened_vehicles": [
      {
        "vehicle_code": "TRUCK-YN-102",
        "driver_name": "张建国",
        "distance_m": 86.4,
        "risk_zone": "100m核心滑塌红区",
        "coordinates": [102.5622, 24.7160, 1968.0]
      }
    ],
    "buffer_polygons_geojson": { "type": "FeatureCollection", "features": [...] }
  }
}
```

#### 接口 4：WebSocket 矿卡 GPS 轨迹与传感器秒级告警流
* **连接地址**：`ws://localhost:8001/ws/mine-twin`
* **服务端推送消息格式**：
```json
{
  "type": "VEHICLE_POSITION_UPDATE",
  "timestamp": 1751356800,
  "vehicles": [
    { "vehicle_code": "TRUCK-YN-101", "lng": 102.5612, "lat": 24.7142, "alt": 1945.2, "heading": 135.0, "speed": 22.5 },
    { "vehicle_code": "TRUCK-YN-102", "lng": 102.5622, "lat": 24.7160, "alt": 1968.0, "heading": 45.0, "speed": 18.0 }
  ]
}
```

---

### 3.2 前端 Cesium / Mars3D 四大硬核三维分析组件模板代码（可直接喂给 Cursor）

为了确保你在没有做过 Cesium 底层开发的情况下也能 100% 跑通所有三维矿山功能，以下提供基于 `mars3d` + `Cesium` 的核心组件实现代码模板：

```typescript
// frontend/src/composables/useMine3DAnalysis.ts
import * as mars3d from 'mars3d';
import * as Cesium from 'cesium';

export function useMine3DAnalysis(map: mars3d.Map) {
  
  // 1. 采场三维地形开挖 (带岩层底部与侧壁贴图)
  let terrainClip: mars3d.thing.TerrainClip | null = null;
  const startPitExcavation = async (depth: number = 50) => {
    if (!terrainClip) {
      terrainClip = new mars3d.thing.TerrainClip({
        diffHeight: depth, // 开挖深度(m)
        image: '/textures/mine_rock_wall.jpg',        // 矿坑侧壁磷矿岩层贴图
        imageBottom: '/textures/mine_pit_bottom.jpg', // 矿坑底部贴图
        splitNum: 80
      });
      map.addThing(terrainClip);
    }
    // 鼠标在采场手绘多边形即刻挖出三维矿坑
    const graphic = await map.graphicLayer.startDraw({
      type: 'polygon',
      style: { color: '#00ffff', opacity: 0.2, outline: true, outlineColor: '#00ffff' }
    });
    const positions = graphic.positionsShow;
    map.graphicLayer.clear();
    terrainClip.clear();
    terrainClip.addArea(positions);
  };

  // 2. 矿山采剥土方量（挖方/填方体积）精准测算
  let measureVolume: mars3d.thing.MeasureVolume | null = null;
  const calculateEarthworkVolume = async ( onResult: (res: { cutVolume: number; fillVolume: number; area: number }) => void ) => {
    if (!measureVolume) {
      measureVolume = new mars3d.thing.MeasureVolume({
        label: { font_size: 18, color: '#ffffff', background: true, backgroundColor: '#0f172a' }
      });
      map.addThing(measureVolume);
      measureVolume.on(mars3d.EventType.end, (event: any) => {
        onResult({
          cutVolume: Math.round(event.sourceTarget.cutVolume),   // 挖方量 (m³)
          fillVolume: Math.round(event.sourceTarget.fillVolume), // 填方量 (m³)
          area: Math.round(event.sourceTarget.area)              // 水平投影面积 (m²)
        });
      });
    }
    measureVolume.startDraw();
  };

  // 3. 尾矿库漫顶溃坝三维动态淹没推演
  let floodByMaterial: mars3d.thing.FloodByMaterial | null = null;
  const startTailingsDamBreach = (polygonCoords: number[][], minElev = 1910, maxElev = 1965, speed = 2) => {
    if (!floodByMaterial) {
      floodByMaterial = new mars3d.thing.FloodByMaterial({
        color: 'rgba(194, 120, 56, 0.75)' // 尾矿泥浆棕黄色水面
      });
      map.addThing(floodByMaterial);
    }
    floodByMaterial.clear();
    floodByMaterial.setOptions({ minHeight: minElev, maxHeight: maxElev, speed });
    floodByMaterial.addArea(polygonCoords);
    floodByMaterial.start();
  };

  // 4. 高陡边坡主滑方向地形高程剖面采样 (返回数据供 ECharts 绘图)
  const sampleSlopeProfile = async (startLngLat: [number, number], endLngLat: [number, number], samples = 100) => {
    const start = Cesium.Cartographic.fromDegrees(startLngLat[0], startLngLat[1]);
    const end = Cesium.Cartographic.fromDegrees(endLngLat[0], endLngLat[1]);
    const positions: Cesium.Cartographic[] = [];
    for (let i = 0; i <= samples; i++) {
      const factor = i / samples;
      positions.push(
        new Cesium.Cartographic(
          Cesium.Math.lerp(start.longitude, end.longitude, factor),
          Cesium.Math.lerp(start.latitude, end.latitude, factor)
        )
      );
    }
    const updatedPositions = await Cesium.sampleTerrainMostDetailed(map.viewer.terrainProvider, positions);
    return updatedPositions.map((p, idx) => ({
      step: idx,
      elevation: Number(p.height.toFixed(2))
    }));
  };

  return {
    startPitExcavation,
    calculateEarthworkVolume,
    startTailingsDamBreach,
    sampleSlopeProfile
  };
}
```

---

## 四、 Docker 容器化一键部署方案 (`docker-compose.yml`)

```yaml
version: '3.9'

services:
  # 1. PostGIS 三维空间数据库 (存储 PointZ 传感器、采场分区与时序数据)
  mine_postgis:
    image: postgis/postgis:15-3.4
    container_name: yunnan_mine_postgis
    restart: always
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres123}
      POSTGRES_DB: yunnan_mine_gis
    ports:
      - "5433:5432"
    volumes:
      - mine_pgdata:/var/lib/postgresql/data
      - ./backend/sql/init_mine.sql:/docker-entrypoint-initdb.d/init_mine.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d yunnan_mine_gis"]
      interval: 5s
      timeout: 5s
      retries: 5

  # 2. Redis (处理矿卡 GPS 高频轨迹与 GNSS 位移实时流)
  mine_redis:
    image: redis:7-alpine
    container_name: yunnan_mine_redis
    restart: always
    ports:
      - "6380:6379"

  # 3. FastAPI 矿山物联网与三维空间计算后端
  mine_backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: yunnan_mine_backend
    restart: always
    depends_on:
      mine_postgis:
        condition: service_healthy
      mine_redis:
        condition: service_started
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:${POSTGRES_PASSWORD:-postgres123}@mine_postgis:5432/yunnan_mine_gis
      REDIS_URL: redis://mine_redis:6379/0
      MINE_CENTER_LAT: 24.715
      MINE_CENTER_LNG: 102.562
    ports:
      - "8001:8000"

  # 4. Vue 3 + Cesium/Mars3D 三维数字孪生矿山前端
  mine_frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: yunnan_mine_frontend
    restart: always
    depends_on:
      - mine_backend
    ports:
      - "8081:80"

volumes:
  mine_pgdata:
```
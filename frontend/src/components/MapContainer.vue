<template>
  <div class="map-wrap">
    <div id="mars3d-container" class="mars3d-container"></div>
    <div class="map-legend">
      <span v-for="(name, i) in statusNames" :key="i" class="legend-item">
        <i :style="{ background: colors[i] }"></i>{{ name }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import * as mars3d from 'mars3d'
import * as Cesium from 'mars3d-cesium'
import { mine, STATUS_COLORS as colors, STATUS_NAMES as statusNames } from '../store'
import { apiGet, connectTwinWs } from '../api'
import { TerrariumTerrainProvider } from '../terrain/TerrariumTerrainProvider'

const MINE_LNG = 102.562
const MINE_LAT = 24.715
const TERRAIN_PROBE_LEVEL = 14
const ARCGIS_TERRAIN_URL =
  'https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer'

// 分区配色：按 zone_type 分色，之前所有分区共用一套 pit 样式，
// 且 GeoJsonLayer 的 symbol 解析失败会退回默认白色实心块
const ZONE_STYLE: Record<string, { fill: string; opacity: number; line: string }> = {
  pit: { fill: '#ff8c42', opacity: 0.22, line: '#ff8c42' },
  tailings: { fill: '#c27838', opacity: 0.26, line: '#d98a45' },
  dump: { fill: '#b0b0b0', opacity: 0.18, line: '#cfcfcf' }
}

async function initMap() {
  const map = new mars3d.Map('mars3d-container', {
    scene: {
      center: { lat: 24.6985, lng: 102.562, alt: 4500, heading: 358, pitch: -46 },
      sceneMode: 3,
      showSun: true,
      showMoon: false,
      fog: true,
      globe: { depthTestAgainstTerrain: true, enableLighting: true },
      skyBox: true,
      stars: true
    },
    basemaps: [
      {
        name: '高清卫星影像',
        icon: 'https://data.mars3d.cn/img/thumbnail/basemap/tdt_dx.png',
        type: 'xyz',
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        maximumLevel: 18,
        show: true
      },
      {
        name: 'OpenStreetMap',
        icon: 'https://data.mars3d.cn/img/thumbnail/basemap/osm.png',
        type: 'xyz',
        url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        maximumLevel: 18
      }
    ],
    control: { homeButton: true, sceneModePicker: true, baseLayerPicker: false, animation: false, timeline: false, compass: { bottom: '380px' } }
  })

  mine.map = map
  mine.viewer = map.viewer

  const scene = map.viewer.scene
  const globe = scene.globe

  // —— 底图优先：先用椭球体，保证影像底图 100% 出得来 ——
  // 之前直接把自定义地形提供器挂上去，一旦地形瓦片加载异常，整个地表都不渲染，
  // 表现就是「连底图都没有」。改为：影像先出图，地形探测通过后再叠加。
  map.viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider()

  // 固定为当地正午的太阳高度角：Cesium 默认跟随真实时间，夜间场景整体发黑，
  // 且没有地形明暗交界，视觉上会误判成「平面图」
  map.viewer.clock.currentTime = Cesium.JulianDate.fromIso8601('2026-11-01T04:00:00Z')
  map.viewer.clock.shouldAnimate = false
  globe.enableLighting = true
  // 低空视角下 groundAtmosphere 会在地表蒙一层蓝雾，看起来像"没有底图"，关闭
  globe.showGroundAtmosphere = false
  // 地形瓦片未到位的区域不能露成纯黑洞（远看像画面缺口）：给一个接近植被/裸岩的底色，
  // 加载完成后会被影像覆盖，视觉上过渡自然
  globe.baseColor = Cesium.Color.fromCssColorString('#2b3630')
  // 低空机位（2000~3000m）若用默认 MSSE=2，每个像素都要更高层级瓦片，请求量爆炸、
  // tilesLoaded 永不收敛，未到位的区域就整片发黑（尾矿库机位实测全黑 40s+）。
  // 放宽到 16：低空仍能拿到 ~15 级影像，肉眼几乎无差别，但瓦片数量下降一个量级。
  globe.maximumScreenSpaceError = 16

  // —— 模型照明增强 ——
  // PBR 金属材质矿卡只靠默认 SunLight(强度2.0) 时背光面发灰发暗。
  // 保持太阳方向不变（与锁定的 04:00Z 时钟一致），提高光源强度；
  // 地形已由贴图自发光主导，该强度不会过曝。
  if (scene.light && 'intensity' in scene.light) (scene.light as any).intensity = 2.8

  // 地形夸张：必须与相机高度协同。矿区海拔约 1950~2100m，夸张 2 倍后地表被抬到 4000m 以上，
  // 相机若仍停在 3600m 就会直接钻进山体里，画面只剩一个巨大山坡。
  const EXAGGERATION = 1.0
  if ('verticalExaggeration' in scene) scene.verticalExaggeration = EXAGGERATION
  else (globe as any).terrainExaggeration = EXAGGERATION

  // 相机对准昆阳磷矿二号采场（高度需高于夸张后的地表）
  map.setCameraView({ lat: 24.6985, lng: 102.562, alt: 4500, heading: 358, pitch: -46 })



  // —— 异步叠加真实地形 ——
  // 顺序：Cesium 官方 ArcGIS 全球地形（免 Key、有 CORS、速度快）→ 自研 Terrarium 兜底 → 保持椭球。
  ;(async () => {
    try {
      const arcgis = await Cesium.ArcGISTiledElevationTerrainProvider.fromUrl(ARCGIS_TERRAIN_URL)
      map.viewer.terrainProvider = arcgis
      mine.terrainOk = true
      mine.terrainSource = 'ArcGIS WorldElevation3D'
      return
    } catch {
      /* 继续尝试备用源 */
    }
    try {
      const tp: any = new TerrariumTerrainProvider()
      const carto = Cesium.Cartographic.fromDegrees(MINE_LNG, MINE_LAT)
      const xy = tp.tilingScheme.positionToTileXY(carto, TERRAIN_PROBE_LEVEL)
      const rect = tp.tilingScheme.tileXYToRectangle(xy.x, xy.y, TERRAIN_PROBE_LEVEL)
      const data: any = await tp.requestTileGeometry(xy.x, xy.y, TERRAIN_PROBE_LEVEL)
      const h = data ? data.interpolateHeight(rect, carto.longitude, carto.latitude) : 0
      if (h > 800) {
        map.viewer.terrainProvider = tp
        mine.terrainOk = true
        mine.terrainSource = 'AWS Terrarium'
      }
    } catch {
      mine.terrainOk = false // 保持椭球，底图不受影响
    }
  })()

  // 矿区分区与道路（手动构建，按类型分色，避免 GeoJsonLayer 符号解析失败渲染成白块）
  mine.layers.zones = new mars3d.layer.GraphicLayer()
  map.addLayer(mine.layers.zones)

  mine.layers.roads = new mars3d.layer.GraphicLayer()
  map.addLayer(mine.layers.roads)

  // 传感器图层（注意：GraphicLayer 在 layer 命名空间下，graphic 命名空间里只有单个图元类）
  mine.layers.sensors = new mars3d.layer.GraphicLayer({ allowDrillPick: true })
  map.addLayer(mine.layers.sensors)

  // 矿卡模型图层
  mine.layers.vehicles = new mars3d.layer.GraphicLayer()
  map.addLayer(mine.layers.vehicles)

  // 缓冲区分析图层
  mine.layers.buffer = new mars3d.layer.GraphicLayer()
  map.addLayer(mine.layers.buffer)

  await loadZones()
  await loadRoads()
  await loadSensors()
  connectTwinWs(onWsMessage)
  setInterval(loadSensors, 15000)
}

/** 矿区分区：按 zone_type 分色填充 + 描边 */
async function loadZones() {
  const fc = await apiGet('/api/v1/mine/zones')
  const layer: any = mine.layers.zones
  if (!layer || !fc?.features) return
  layer.clear()
  for (const f of fc.features) {
    const p = f.properties || {}
    const st = ZONE_STYLE[p.zone_type] || ZONE_STYLE.pit
    const g = f.geometry
    const polys = g.type === 'MultiPolygon' ? g.coordinates : [g.coordinates]
    for (const poly of polys) {
      for (const ring of poly) {
        layer.addGraphic(new mars3d.graphic.PolygonEntity({
          positions: ring.map((c: number[]) => Cesium.Cartesian3.fromDegrees(c[0], c[1], 0)),
          style: {
            color: st.fill, opacity: st.opacity,
            outline: true, outlineColor: st.line, outlineWidth: 2,
            clampToGround: true
          },
          attr: p,
          popup: `${p.name}<br/>类型: ${p.zone_type}<br/>风险等级: ${p.risk_level ?? '-'}`
        }))
      }
    }
  }
}

/** 矿山道路 */
async function loadRoads() {
  const fc = await apiGet('/api/v1/mine/roads')
  const layer: any = mine.layers.roads
  if (!layer || !fc?.features) return
  layer.clear()
  for (const f of fc.features) {
    const p = f.properties || {}
    const g = f.geometry
    const lines = g.type === 'MultiLineString' ? g.coordinates : [g.coordinates]
    for (const line of lines) {
      layer.addGraphic(new mars3d.graphic.PolylineEntity({
        positions: line.map((c: number[]) => Cesium.Cartesian3.fromDegrees(c[0], c[1], 0)),
        style: { color: '#ffe066', width: 3, clampToGround: true },
        attr: p,
        popup: `${p.name}（${p.road_class}）`
      }))
    }
  }
}

async function loadSensors() {
  const fc = await apiGet('/api/v1/mine/sensors')
  const layer: any = mine.layers.sensors
  if (!layer || !fc.features) return
  layer.clear()
  for (const f of fc.features) {
    const [lng, lat, alt] = f.geometry.coordinates
    const p = f.properties
    const color = colors[p.alert_status]
    // 用 Entity + clampToGround：地形夸张后地表被整体抬高，
    // 绝对高程的点会被埋进山体里（表现为"监测点全消失"），贴地渲染才稳定
    const pt = new mars3d.graphic.PointEntity({
      position: [lng, lat, alt],
      style: {
        color, pixelSize: p.alert_status >= 2 ? 14 : 10,
        outlineWidth: 2, outlineColor: '#ffffff', clampToGround: true
      },
      attr: p
    })
    pt.bindPopup(
      `<div class="mine-popup"><b>${p.name}</b><br/>编号: ${p.sensor_code}<br/>` +
      `位移速率: <b style="color:${color}">${p.disp_rate_mm_d} mm/d</b><br/>` +
      `累计位移: ${p.total_disp_mm} mm<br/>${p.warning_msg || '状态正常'}</div>`)
    pt.on(mars3d.EventType.click, () => {
      mine.selectedSensor = p.sensor_code
      mine.showChart = true
    })
    layer.addGraphic(pt)

    if (p.alert_status >= 2) {
      layer.addGraphic(new mars3d.graphic.LabelEntity({
        position: [lng, lat, alt],
        style: {
          text: p.sensor_code, font_size: 13, color,
          background: true, backgroundColor: 'rgba(15,23,42,0.85)',
          pixelOffsetY: -24, clampToGround: true,
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 30000)
        },
        attr: p
      }))
    }
  }
  refreshStats()
}

function refreshStats() {
  apiGet('/api/v1/mine/overview').then((r) => Object.assign(mine.stats, r))
}

/**
 * 矿卡贴地直接使用 Cesium 原生 clampToGround（HeightReference.CLAMP_TO_GROUND）：
 * 只给经纬度、不提供高程，由 Cesium 按当前渲染地形（含 LOD 流式加载与地形夸张，
 * 模型默认 enableVerticalExaggeration=true）自动贴合地表。
 * 不要手动用 sampleHeight 给已夸张高度，否则会与 enableVerticalExaggeration 双重错位。
 */
interface VehicleTarget {
  lng: number
  lat: number
  heading: number
  graphic: any
  lastLng: number | null
  lastLat: number | null
  lastHeading: number | null
}
const vehicleTargets = new Map<string, VehicleTarget>()
let vehicleFrameListener: Cesium.Event.RemoveCallback | null = null

function ensureVehicleFrameLoop() {
  if (vehicleFrameListener || !mine.viewer) return
  const globe = mine.viewer.scene.globe
  const carto = new Cesium.Cartographic()
  const hpr = new Cesium.HeadingPitchRoll()
  vehicleFrameListener = mine.viewer.scene.preUpdate.addEventListener(() => {
    // truckFreeze 是"硬冻结"：连插值一起停，交给外部（截图文案）直接摆位；
    // 注意不能用它来"定格运行中的车" —— 那样车会停在实体创建时的 2000m 兜底高度，
    // 想定格又不悬空，只冻结 WS 目标坐标（truckPaused）即可，本循环继续把车落回地面。
    if (mine.truckFreeze) return
    for (const [code, t] of vehicleTargets) {
      // 高程必须是【夸张后】的地表高度：globe.getHeight 返回的正是渲染面高度。
      // 模型侧已设 enableVerticalExaggeration=false，否则会二次放大被顶到高空。
      carto.longitude = Cesium.Math.toRadians(t.lng)
      carto.latitude = Cesium.Math.toRadians(t.lat)
      carto.height = 0
      const h = globe.getHeight(carto)
      // 抬高 2m：模型原点在地面，恰好等于地表高度时会与地形深度冲突（z-fighting），
      // 表现为"车被地表吞掉/闪烁不可见"
      const alt = Number.isFinite(h) ? h + 2.0 : 2000
      const pos = Cesium.Cartesian3.fromDegrees(t.lng, t.lat, alt)
      t.graphic.position = pos
      if (t.lastHeading !== t.heading) {
        hpr.heading = Cesium.Math.toRadians(t.heading)
        hpr.pitch = 0
        hpr.roll = 0
        t.graphic.model.orientation = Cesium.Transforms.headingPitchRollQuaternion(pos, hpr)
        t.lastHeading = t.heading
      }
      // 跟车巡检：相机置于【车后 18m、车顶上方 7.5m】并朝向车头航向。
      // 早期版本把相机放在车辆自身坐标 +6.5m，等于贴在驾驶室内部，矿卡车体
      // 会占满下半屏（近平面穿模，画面是整块棕色），因此改为车后跟拍。
      // 不用 camera.lookAt（与 Mars3D 相机控制冲突会把 position 算成 NaN），
      // 复用这条每帧都在跑的 setCameraView 通道，跟随与插值天然同步。
      if (mine.followTruck === code) {
        const BACK = 22, UP = 8
        const hRad = Cesium.Math.toRadians(t.heading)
        // 沿航向正方向后退（实测该模型车头朝 -heading，故取 +sin/+cos）
        const dLat = (BACK * Math.cos(hRad)) / 111320
        const dLng = (BACK * Math.sin(hRad)) / (111320 * Math.cos(Cesium.Math.toRadians(t.lat)))
        mine.map.setCameraView({
          lng: t.lng + dLng, lat: t.lat + dLat, alt: alt + UP,
          heading: t.heading, pitch: -12
        }, { duration: 0 })
      }
    }
  })
}

function onWsMessage(msg: any) {
  if (msg.type === 'VEHICLE_POSITION_UPDATE') {
    ensureVehicleFrameLoop()
    for (const v of msg.vehicles) {
      let g: any = mine.vehicles[v.vehicle_code]
      if (!g) {
        // 用【原生 Cesium 实体】而不是 mars3d.graphic.ModelEntity：
        // 实测 mars3d 的模型包装层在本场景下不渲染（图元存在于图层却不出画），
        // 原生 entity + model 通道已验证可正常显示、可贴地、可跟随地形夸张。
        g = mine.viewer!.entities.add({
          position: Cesium.Cartesian3.fromDegrees(v.lng, v.lat, 2000),
          model: {
            uri: '/models/mining_truck.glb',
            scale: 1,
            minimumPixelSize: 18,
            // 关键：模型默认会再乘一次地形夸张系数(1.4)，叠加后会被顶到高空看不见
            enableVerticalExaggeration: false,
            // 金属度材质在只有方向光时发灰，这里提高环境光贡献
            imageBasedLightingFactor: new Cesium.Cartesian2(2.0, 1.0),
            lightColor: new Cesium.Color(1.25, 1.25, 1.25, 1.0)
          },
          description: `${v.vehicle_code}｜${v.driver_name}｜${v.load_status}`
        })
        mine.vehicles[v.vehicle_code] = g
        vehicleTargets.set(v.vehicle_code, {
          lng: v.lng, lat: v.lat, heading: v.heading, graphic: g,
          lastLng: null, lastLat: null, lastHeading: null
        })
      }
      const t = vehicleTargets.get(v.vehicle_code)!
      // 定格模式下只登记新车（保证实体已创建、可被截图脚本找到），
      // 已有车辆不刷新目标坐标 —— 插值循环也在 paused，车就原地不动
      if (mine.truckPaused) continue
      t.lng = v.lng
      t.lat = v.lat
      t.heading = v.heading
    }
  } else if (msg.type === 'SENSOR_ALERT') {
    // 同一个监测点只保留最新一条，否则 2 秒一条的告警会把左侧列表刷满
    const idx = mine.alerts.findIndex((a: any) => a.sensor_code === msg.sensor_code)
    const item = { ...msg, ts: Date.now() }
    if (idx >= 0) mine.alerts.splice(idx, 1)
    mine.alerts.unshift(item)
    if (mine.alerts.length > 30) mine.alerts.pop()
    refreshStats()
    loadSensors()
  } else if (msg.type === 'EVACUATE_COMMAND') {
    mine.alerts.unshift({ type: 'EVACUATE_COMMAND', message: msg.message })
  }
}

onMounted(initMap)
</script>

<style scoped>
.map-wrap { position: relative; width: 100%; height: 100%; }
.mars3d-container { width: 100%; height: 100%; overflow: hidden; }
/* 罗盘与 Mars3D logo 会压在三维画面上，演示/截图时一律隐藏 */
.mars3d-container :deep(.mars3d-compass) { display: none !important; }
.map-legend {
  position: absolute; left: 12px; bottom: 12px; z-index: 9;
  background: rgba(10, 18, 36, 0.85); border: 1px solid #23406b; border-radius: 6px;
  padding: 8px 12px; display: flex; gap: 14px; color: #cfe3ff; font-size: 12px;
}
.legend-item { display: flex; align-items: center; gap: 5px; }
.legend-item i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
</style>

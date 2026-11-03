<template>
  <div class="dashboard">
    <!-- 顶部标题栏 -->
    <header class="topbar">
      <div class="title">⛰ 云南高原露天矿山三维形变监测与尾矿库溃坝推演系统</div>
      <div class="subtitle">昆明市晋宁区·昆阳磷矿二号露天采场（102.562°E, 24.715°N）</div>
      <div class="top-right">
        <span class="pill" :class="mine.terrainOk ? 'ok' : 'warn'">{{ mine.terrainOk ? '真实地形已接入' : '地形加载中/不可达' }}</span>
        <span class="pill">监测点 {{ mine.stats.total_sensors }}</span>
        <span class="pill red">红色告警 {{ mine.stats.red_alerts }}</span>
        <span class="pill orange">橙色预警 {{ mine.stats.orange_alerts }}</span>
        <span class="pill">在线矿卡 {{ mine.stats.vehicles }}</span>
      </div>
    </header>

    <div class="body">
      <!-- 左侧：图层树 + 告警流 -->
      <aside class="left-col">
        <div class="panel">
          <div class="panel-title">🗂 图层管理与地形夸张</div>
          <div class="panel-body">
            <label v-for="l in layerList" :key="l.key" class="chk">
              <input type="checkbox" v-model="l.show" @change="toggleLayer(l.key, l.show)" />{{ l.name }}
            </label>
            <div class="slider-row">
              <span>地形夸张</span>
              <input type="range" min="1" max="4" step="0.2" v-model.number="exaggeration" @input="applyExaggeration" />
              <b>{{ exaggeration }}x</b>
            </div>
            <div class="slider-row">
              <span>地形分析</span>
              <select v-model="terrainMode" @change="applyTerrainMaterial" class="mini-select">
                <option value="none">关闭</option>
                <option value="contour">等高线（20m）</option>
                <option value="slope">坡度着色（&gt;45° 红色高亮）</option>
              </select>
            </div>
            <div v-if="terrainMode === 'slope'" class="slope-legend">
              <div class="slope-legend-title">边坡坡度分级 · 35m 网格</div>
              <div class="slope-legend-row">
                <i style="background:rgba(34,197,94,.85)"></i><span>&lt;15° 平缓</span>
                <i style="background:rgba(234,179,8,.85)"></i><span>15–30° 中陡</span>
              </div>
              <div class="slope-legend-row">
                <i style="background:rgba(249,115,22,.85)"></i><span>30–45° 陡坡</span>
                <i style="background:rgba(239,68,68,.9)"></i><span>&gt;45° 极高危</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel grow">
          <div class="panel-title">🚨 实时告警流（S 型蠕变监测）</div>
          <div class="panel-body alert-stream">
            <div v-if="!mine.alerts.length" class="empty">暂无告警，边坡运行平稳</div>
            <div v-for="(a, i) in mine.alerts" :key="i"
                 class="alert-item" :class="a.alert_status === 3 || a.type === 'EVACUATE_COMMAND' ? 'red' : 'orange'"
                 @click="a.sensor_code && (mine.selectedSensor = a.sensor_code, mine.showChart = true)">
              {{ a.message || a.name }}
            </div>
          </div>
        </div>
      </aside>

      <!-- 中央地图 -->
      <main class="center"><MapContainer /></main>

      <!-- 右侧：工程分析工具箱 + 溃坝推演 -->
      <aside class="right-col">
        <div class="panel">
          <div class="panel-title">⛏ 三维工程分析工具箱</div>
          <div class="panel-body tools">
            <div class="tool-row">
              <span>开挖深度</span>
              <input type="number" v-model.number="excavDepth" min="10" max="120" step="5" />
              <span>m</span>
            </div>
            <button class="btn" @click="startPitExcavation(excavDepth)">采场三维地形开挖</button>
            <button class="btn" @click="calculateEarthworkVolume(showVolume)">采剥土方量测算</button>
            <button class="btn ghost" @click="clearAnalysis">清除分析结果</button>
            <div v-if="volume" class="result-card">
              <div>挖方体积: <b>{{ volume.cut.toLocaleString() }}</b> m³</div>
              <div>填方体积: <b>{{ volume.fill.toLocaleString() }}</b> m³</div>
              <div>水平投影面积: <b>{{ volume.area.toLocaleString() }}</b> m²</div>
            </div>
            <button class="btn" @click="drawAndProfile">主滑方向地形剖面图</button>
            <div class="tool-row">
              <span>跟车巡检</span>
              <select v-model="followTruckCode" class="mini-select">
                <option :value="''">关闭</option>
                <option v-for="(g, code) in mine.vehicles" :key="code" :value="code">{{ code }} 驾驶视角</option>
              </select>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-title">🧭 滑坡影响区缓冲区评估</div>
          <div class="panel-body tools">
            <select v-model="impactSensor">
              <option value="GNSS-N-08">GNSS-N-08（红色告警点）</option>
              <option v-for="s in orangeSensors" :key="s" :value="s">{{ s }}</option>
            </select>
            <button class="btn" @click="runLandslideImpact">生成 100/300/500m 贴地缓冲区</button>
            <div v-if="impact" class="result-card">
              <div>受威胁矿卡: <b>{{ impact.threatened_count }}</b> 台</div>
              <div v-for="v in impact.threatened_vehicles" :key="v.vehicle_code" class="threat-item">
                {{ v.vehicle_code }}·{{ v.driver_name }} 距离 {{ v.distance_m }}m → {{ v.risk_zone }}
              </div>
            </div>
            <button class="btn warn" :disabled="!impact" @click="evacuate">📢 一键声光撤离指令</button>
            <button class="btn ghost" @click="clearBuffer">清除缓冲区</button>
          </div>
        </div>

        <div class="panel grow">
          <div class="panel-title">🌊 尾矿库漫顶溃坝推演</div>
          <div class="panel-body tools">
            <div class="tool-row"><span>起始水位</span><input type="number" v-model.number="breach.start" />m</div>
            <div class="tool-row"><span>最高水位</span><input type="number" v-model.number="breach.max" />m</div>
            <div class="tool-row"><span>上涨速率</span><input type="number" v-model.number="breach.speed" step="0.1" />m/min</div>
            <button class="btn" @click="runDamBreach">▶ 启动溃坝推演</button>
            <button class="btn ghost" @click="stopDamBreach(); stopDamTicker()">■ 停止并清除</button>
            <div v-if="breachInfo" class="result-card">
              <div>{{ breachInfo.tailings_name }}（{{ breachInfo.tailings_area_km2 }} km²）</div>
              <div>预计演进时长: <b>{{ breachInfo.estimated_duration_min }}</b> 分钟</div>
              <!-- 推演中逐帧刷新：水位读自 DamBreachWater.level，面积按库容近似曲线估算 -->
              <div v-if="damLive.running">
                <div>当前水位: <b>{{ damLive.level.toFixed(1) }}</b> m</div>
                <div>最大水深: <b>{{ damLive.depth.toFixed(1) }}</b> m</div>
                <div>动态淹没面积: <b>{{ damLive.area.toFixed(3) }}</b> km²</div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <!-- 底部图表抽屉 -->
    <div class="chart-drawer" :class="{ open: mine.showChart }">
      <div class="chart-header">
        <span>📈 {{ chartSensor }} 近 72 小时「位移速率-降雨量」双因子耦合曲线</span>
        <button class="btn ghost" @click="mine.showChart = false">收起 ✕</button>
      </div>
      <div ref="chartEl" class="chart-box"></div>
      <div ref="profileEl" class="chart-box" v-show="profileData.length">
        <span class="chart-label">主滑方向地形高程剖面</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import * as echarts from 'echarts'
import * as mars3d from 'mars3d'
import * as Cesium from 'mars3d-cesium'
import MapContainer from '../components/MapContainer.vue'
import { mine } from '../store'
import { apiGet, apiPost } from '../api'
import {
  startPitExcavation, calculateEarthworkVolume, startDamBreach, stopDamBreach,
  sampleSlopeProfile, drawProfileLine, toggleTerrainMaterial
} from '../composables/useMine3DAnalysis'

const layerList = reactive([
  { key: 'zones', name: '矿区功能分区', show: true },
  { key: 'roads', name: '矿山运输道路', show: true },
  { key: 'sensors', name: '监测传感器', show: true },
  { key: 'vehicles', name: '运矿矿卡', show: true }
])

const exaggeration = ref(1.0)
const excavDepth = ref(45)
const volume = ref<{ cut: number; fill: number; area: number } | null>(null)
const impactSensor = ref('GNSS-N-08')
const impact = ref<any>(null)
// 默认水位按库区实测地形取值：库底约 1989m，抬到 2015m 才能看到水体漫出库区；
// 上涨速率按 m/min 计 —— 30m 涨幅 / 0.3 m/min ≈ 100 分钟，接近真实尾矿库溃坝演进量级
const breach = reactive({ start: 1985, max: 2015, speed: 0.3 })
const breachInfo = ref<any>(null)
// 溃坝推演实时数字：水位直接读自水面实体的 currentLevel，
// 面积用矿区山谷库容近似曲线（面积随涨幅 1.6 次幂增长，A0=0.012 → Amax≈0.185 km²）
const damLive = reactive({ running: false, level: 0, depth: 0, area: 0 })
let damTicker: ReturnType<typeof setInterval> | null = null
// 等高线/坡度着色与跟车巡检
const terrainMode = ref<'none' | 'contour' | 'slope'>('none')
const followTruckCode = ref('')
const chartSensor = ref('GNSS-N-08')
const chartEl = ref<HTMLElement>()
const profileEl = ref<HTMLElement>()
const profileData = ref<any[]>([])
let chart: echarts.ECharts | null = null
let profileChart: echarts.ECharts | null = null
let rawProfile: { step: number; elevation: number; dist: number }[] = []

const orangeSensors = computed(() =>
  mine.alerts.filter((a) => a.sensor_code && a.sensor_code !== 'GNSS-N-08').map((a) => a.sensor_code))

function toggleLayer(key: string, show: boolean) {
  const layer = mine.layers[key]
  if (layer) layer.show = show
}

function applyExaggeration() {
  const viewer = mine.viewer
  if (!viewer) return
  const scene = viewer.scene
  const old = Number((scene as any).verticalExaggeration ?? 1)
  const next = exaggeration.value
  if ('verticalExaggeration' in scene) (scene as any).verticalExaggeration = next
  else (scene.globe as any).terrainExaggeration = next

  // 相机随夸张联动抬升：地形整体被抬高 terrainTop*(next-old)，
  // 相机不动就会被山体吞掉（表现为画面变成一个巨大的土坡）
  const TERRAIN_TOP = 2100
  const cam = viewer.camera
  const carto = Cesium.Cartographic.fromCartesian(cam.position)
  const hNew = carto.height + TERRAIN_TOP * (next - old)
  cam.setView({
    destination: Cesium.Cartesian3.fromRadians(carto.longitude, carto.latitude, hNew),
    orientation: { heading: 0, pitch: cam.pitch, roll: 0 }
  })
}

function showVolume(r: { cut: number; fill: number; area: number }) {
  volume.value = r
}

function clearAnalysis() {
  const map = mine.map
  if (!map) return
  const tc: any = mine.things.terrainClip
  if (tc) tc.clear()
  const mv: any = mine.things.measure
  if (mv) { try { mv.clear() } catch { /* noop */ } }
  volume.value = null
  profileData.value = []
}

async function drawAndProfile() {
  drawProfileLine(async (pts) => {
    if (pts.length < 2) return
    rawProfile = await sampleSlopeProfile(pts[0], pts[pts.length - 1])
    profileData.value = rawProfile
    mine.showChart = true
    await nextTick()
    setTimeout(renderProfile, 450)
  })
}

function renderProfile() {
  if (!profileEl.value) return
  profileChart ||= echarts.init(profileEl.value)
  profileChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', formatter: (p: any) => `里程 ${p[0].value[0]} m<br/>高程 ${p[0].value[1]} m` },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'value', name: '里程(m)', axisLabel: { color: '#9fb8e0' } },
    yAxis: { type: 'value', name: '高程(m)', scale: true, axisLabel: { color: '#9fb8e0' } },
    series: [{
      type: 'line', showSymbol: false, smooth: true,
      data: rawProfile.map((p) => [p.dist, p.elevation]),
      areaStyle: { color: 'rgba(64,158,255,0.25)' },
      lineStyle: { color: '#409eff', width: 2 }
    }]
  })
}

watch(() => mine.selectedSensor, async (code) => {
  if (!code) return
  chartSensor.value = code
  const ts = await apiGet(`/api/v1/mine/sensors/${code}/timeseries?hours=72`)
  renderChart(ts)
}, { immediate: false })

async function renderChart(ts: any) {
  mine.showChart = true
  await nextTick()
  setTimeout(() => {
    if (!chartEl.value) return
    chart ||= echarts.init(chartEl.value)
  chart.setOption({
    backgroundColor: 'transparent',
    legend: { data: ['位移速率(mm/d)', '累计位移(mm)', '降雨量(mm)'], textStyle: { color: '#cfe3ff' }, top: 4 },
    tooltip: { trigger: 'axis' },
    grid: { left: 55, right: 55, top: 40, bottom: 35 },
    xAxis: { type: 'category', data: ts.timestamps, axisLabel: { color: '#9fb8e0' } },
    yAxis: [
      { type: 'value', name: '位移(mm)', scale: true, axisLabel: { color: '#9fb8e0' } },
      { type: 'value', name: '降雨(mm/h)', axisLabel: { color: '#9fb8e0' }, splitLine: { show: false } }
    ],
    series: [
      { name: '位移速率(mm/d)', type: 'line', data: ts.disp_rate_series, smooth: true, lineStyle: { color: '#e74c3c', width: 2 } },
      { name: '累计位移(mm)', type: 'line', data: ts.total_disp_series, smooth: true, lineStyle: { color: '#e67e22', width: 2 }, areaStyle: { color: 'rgba(230,126,34,0.15)' } },
      { name: '降雨量(mm)', type: 'bar', yAxisIndex: 1, data: ts.rainfall_series, itemStyle: { color: 'rgba(52,152,219,0.55)' } }
    ]
  })
  }, 450)
}

async function runLandslideImpact() {
  const r = await apiPost('/api/v1/mine/spatial/landslide-impact', {
    sensor_code: impactSensor.value, radii_meters: [100, 300, 500]
  })
  if (r.code !== 200) return
  impact.value = r.data
  const layer: any = mine.layers.buffer
  layer.clear()
  const ringStyle: Record<number, { fill: string; line: string }> = {
    500: { fill: 'rgba(241,196,15,0.18)', line: '#f1c40f' },
    300: { fill: 'rgba(230,126,34,0.24)', line: '#e67e22' },
    100: { fill: 'rgba(231,76,60,0.32)', line: '#e74c3c' }
  }
  const fc = r.data.buffer_polygons_geojson
  if (fc?.features?.length) {
    for (const f of fc.features) {
      const radius = f.properties?.radius_m ?? 100
      const st = ringStyle[radius] || ringStyle[100]
      const geom = f.geometry
      const rings = geom.type === 'MultiPolygon' ? geom.coordinates.map((p: any) => p[0]) : [geom.coordinates[0]]
      for (const ring of rings) {
        layer.addGraphic(new mars3d.graphic.PolygonEntity({
          positions: flatToPositions(ring),
          style: {
            color: st.fill, clampToGround: true, outline: true,
            outlineColor: st.line, outlineWidth: 2
          }
        }))
      }
    }
  }
  layer.addGraphic(new mars3d.graphic.PointPrimitive({
    position: toCartesian(r.data.center),
    style: { color: '#e74c3c', pixelSize: 16, outlineWidth: 3, outlineColor: '#fff' }
  }))
  mine.map.flyToPoint(toCartesian(r.data.center), { radius: 1800, pitch: -45 })
}

function toCartesian(p: number[]): any {
  return Cesium.Cartesian3.fromDegrees(p[0], p[1], p[2] ?? 0)
}

function flatToPositions(coords: number[][]): any[] {
  return coords.map((c) => Cesium.Cartesian3.fromDegrees(c[0], c[1], 0))
}

function clearBuffer() {
  ;(mine.layers.buffer as any)?.clear()
  impact.value = null
}

function evacuate() {
  mine.wsSend?.('EVACUATE')
}

async function runDamBreach() {
  const r = await apiPost('/api/v1/mine/spatial/dam-breach', {
    start_elev_m: breach.start, max_elev_m: breach.max, rise_speed: breach.speed
  })
  if (r.code !== 200) return
  breachInfo.value = r.data
  // 几何可能是 Polygon 也可能是 MultiPolygon，且坐标偶有嵌套数组，
  // 统一拍平后过滤非有限值，避免把 NaN 传进相机导致整个场景 renderError
  const g = r.data.polygon_geojson
  const flat: number[][] = (g.type === 'MultiPolygon' ? g.coordinates[0][0] : g.coordinates[0])
    .map((c: any) => [Number(c[0]), Number(c[1])])
    .filter((c: number[]) => Number.isFinite(c[0]) && Number.isFinite(c[1]))
  if (flat.length < 3) return
  const cx = flat.reduce((s, p) => s + p[0], 0) / flat.length
  const cy = flat.reduce((s, p) => s + p[1], 0) / flat.length
  startDamBreach(flat, breach.start, breach.max, breach.speed)
  // 机位：站在库区正南约 2.5km、椭球高 3600m、下俯 50°。
  //  - 高度不能再压低：2500m 俯视时地形瓦片请求量随高度降低急剧上升，实测 24s 仍有
  //    11 块瓦片在飞、整片发黑只剩水面；3600m 约 15s 收敛。
  //  - 俯角也不能太缓：-32° 时视线落点在 5km 外，库区会掉到画面下边缘之外；
  //    -50° 时画面下沿约 1.7km、中心约 3km，库区水面正好落在画面下方三分之一。
  mine.map.setCameraView({ lng: cx, lat: cy - 0.0225, alt: 3600, heading: 0, pitch: -50 }, { duration: 1.2 })
  startDamTicker()
}

/** 溃坝推演中的面板跳字：200ms 读一次水面实体当前水位，面积按库容近似曲线估算 */
function startDamTicker() {
  stopDamTicker()
  damLive.running = true
  damTicker = setInterval(() => {
    const water: any = mine.things.flood
    const level = Number(water?.level)
    if (!Number.isFinite(level)) return
    // 防御：地形瓦片未就绪时 getHeight 可能返回 undefined，这里统一夹取到有效区间
    const frac = Math.min(1, Math.max(0, (level - breach.start) / Math.max(0.1, breach.max - breach.start)))
    damLive.level = level
    damLive.depth = Math.max(0, level - breach.start)
    damLive.area = 0.012 + (0.185 - 0.012) * Math.pow(frac, 1.6)
  }, 200)
}

function stopDamTicker() {
  if (damTicker) { clearInterval(damTicker); damTicker = null }
  damLive.running = false
}

function applyTerrainMaterial() {
  toggleTerrainMaterial(terrainMode.value)
}

watch(followTruckCode, (code) => {
  mine.followTruck = code || null
})

onUnmounted(stopDamTicker)

/**
 * 截图/演示模式：通过 URL hash 自动触发功能，便于生成 README 配图。
 * 同时监听 hashchange —— SPA 只变 hash 不会重新挂载组件，
 * 手动在地址栏切换 #shot=xxx 也能即时重放对应场景。
 */
function runShotScenario() {
  const hash = location.hash.replace('#', '')
  if (hash === 'shot=impact') {
    setTimeout(() => { runLandslideImpact() }, 12000)
  } else if (hash === 'shot=dam') {
    setTimeout(() => { runDamBreach() }, 12000)
  } else if (hash === 'shot=sensor') {
    // 默认 selectedSensor 已是 GNSS-N-08，直接赋值不会触发 watch，
    // 先置空再置值，确保耦合曲线被拉取并展开
    setTimeout(() => {
      mine.selectedSensor = ''
      setTimeout(() => { mine.selectedSensor = 'GNSS-N-08' }, 200)
    }, 12000)
  } else if (hash === 'shot=truck') {
    // 矿卡特写（演示模式）：
    // 车辆位置由 WS 每秒推送、每次重启都不同，按"第一台车"动态对焦会导致
    // 每次截图机位漂移（有时车在画面外）。这里改成固定取景中心：
    // 定格后把车摆到固定的取景点上，机位也随之固定 —— 稳定、可复现。
    // 取景点取自实测矿卡轨迹上的一点（盘山道路面，非农田），保证画面落在真实运输道路上。
    const VIEW_LNG = 102.5642
    const VIEW_LAT = 24.71134
    setTimeout(() => {
      const C = Cesium
      const first = Object.values(mine.vehicles)[0] as any
      if (!first) return
      const setCam = (h: number) => mine.viewer.camera.setView({
        destination: C.Cartesian3.fromDegrees(VIEW_LNG, VIEW_LAT - 0.00063, h + 30),
        orientation: { heading: 0, pitch: C.Math.toRadians(-22), roll: 0 }
      })
      setCam(1988)   // 先粗定位，缩小视野以加快瓦片加载
      let tries = 0
      const timer = setInterval(() => {
        const h = mine.viewer.scene.globe.getHeight(C.Cartographic.fromDegrees(VIEW_LNG, VIEW_LAT))
        const ok = Number.isFinite(h) && h > 1800 && h < 2200
        if (!ok && tries++ < 120) return
        clearInterval(timer)
        const groundH = Number.isFinite(h) ? h : 1988.0
        // 硬冻结：停掉插值循环，之后手动摆位才不会被覆盖；只留一台车在取景点上
        mine.truckPaused = true
        mine.truckFreeze = true
        let kept = false
        for (const g of Object.values(mine.vehicles) as any[]) {
          if (!kept) {
            g.show = true
            g.position = C.Cartesian3.fromDegrees(VIEW_LNG, VIEW_LAT, groundH + 2)
            kept = true
          } else {
            g.show = false
          }
        }
        setCam(groundH)
        // 二次校正：首轮 getHeight 可能仍是粗精度地形（实测偏高 10~20m，车会浮空）。
        // 等 5s 让精细瓦片落地后再取一次高程，把车重新贴回地面。
        setTimeout(() => {
          const h2 = mine.viewer.scene.globe.getHeight(C.Cartographic.fromDegrees(VIEW_LNG, VIEW_LAT))
          if (Number.isFinite(h2)) {
            first.position = C.Cartesian3.fromDegrees(VIEW_LNG, VIEW_LAT, h2 + 1.0)
            setCam(h2)
          }
        }, 5000)
      }, 500)
    }, 12000)
  } else if (hash === 'shot=contour') {
    setTimeout(() => { terrainMode.value = 'contour'; applyTerrainMaterial() }, 12000)
  } else if (hash === 'shot=slope') {
    // 坡度分级依赖 DEM 采样，必须等地形瓦片就绪，否则 getHeight 全空、网格一个都画不出
    setTimeout(() => {
      terrainMode.value = 'slope'
      // 先把镜头压到采场上方（网格覆盖区中心 102.562, 24.7145），
      // 视野决定瓦片级别，级别不够时 12 级采样会把台阶抹平、坡度全变绿
      mine.map.setCameraView({ lng: 102.5615, lat: 24.7105, alt: 3500, heading: 2, pitch: -58 })
      let tries = 0
      const timer = setInterval(() => {
        const h = mine.viewer?.scene?.globe?.getHeight(Cesium.Cartographic.fromDegrees(102.562, 24.715))
        if ((Number.isFinite(h) && h! > 1800) || tries++ > 100) {
          clearInterval(timer)
          applyTerrainMaterial()
        }
      }, 500)
    }, 12000)
  } else if (hash === 'shot=follow') {
    // 跟车巡检：等矿卡实体建好后切到第一台车的驾驶视角
    setTimeout(() => {
      const codes = Object.keys(mine.vehicles)
      if (codes.length) followTruckCode.value = codes[0]
    }, 14000)
  }
}

onMounted(() => {
  runShotScenario()
  window.addEventListener('hashchange', runShotScenario)
})
</script>

<style scoped src="./dashboard.css"></style>

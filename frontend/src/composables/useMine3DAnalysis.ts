/** 三维矿山工程分析工具箱（开挖 / 土方 / 剖面 / 溃坝 / 等高线与坡度着色） */
import * as mars3d from 'mars3d'
import * as Cesium from 'mars3d-cesium'
import { mine } from '../store'
import { DamBreachWater } from '../analysis/DamBreachWater'

/**
 * 高陡边坡坡度分级图（PRD 模块二：框选北帮，渲染坡度色谱，>45° 极高危坡面高亮）
 *
 * 为什么不用 Cesium 的 SlopeRamp 材质：该材质的着色依赖 czm_slope()，而 czm_slope
 * 需要地形瓦片带顶点法线；ArcGIS WorldElevation3D 不生成法线，实测材质能挂上去
 * 但整片地表不变化（采样坐标为 NaN）。这里改为直接按 DEM 做真实坡度计算。
 *
 * 时序要点（自动截图/切场景时最容易翻车的两处）：
 * ① 必须先等 globe.tilesLoaded——相机刚飞过去时高精度瓦片还在路上，getHeight 全是
 *    undefined，格子会整片漏画；
 * ② 高程采样用 sampleTerrain(terrainProvider, 12, pts) 固定 12 级批量取——600 个点
 *    基本落在同一两张 12 级瓦片里，一次网络请求就齐，比 sampleTerrainMostDetailed
 *    快且不会超时；getHeight 仅作兜底。
 */
export async function renderSlopeGrid(): Promise<number> {
  const viewer = mine.viewer
  if (!viewer) return 0
  clearSlopeGrid()

  // 1. 等当前视野地形瓦片加载稳定（上限 3s，防止截图场景被卡死）
  await new Promise<void>((resolve) => {
    let waited = 0
    const timer = setInterval(() => {
      waited += 200
      if (viewer.scene.globe.tilesLoaded || waited >= 3000) {
        clearInterval(timer)
        resolve()
      }
    }, 200)
  })

  // 2. 覆盖采场与北帮的核心范围（约 1.2km x 0.9km，格子分辨率看得清台阶）
  const minLon = 102.556, maxLon = 102.568
  const minLat = 24.710, maxLat = 24.719
  // 网格间距 ~35m：采场台阶单级高约 15m，间距超过 45m 会把台阶平均成 20° 左右、
  // 出不了陡坡色；但也不能一味加密 —— 2000+ 个贴地多边形会把渲染拖到卡死
  // （实测 56×40 时截图进程被系统 SIGTERM），32×24 是细节与性能的平衡点
  const cols = 32, rows = 24
  const dLon = (maxLon - minLon) / cols
  const dLat = (maxLat - minLat) / rows

  // 独立 DataSource，清理时整体 remove 即可
  const ds = new Cesium.CustomDataSource('slope-grid')
  viewer.dataSources.add(ds)
  mine.layers.slopeGridDS = ds

  // 构造网格顶点 (cols+1) * (rows+1)
  const cartos: Cesium.Cartographic[] = []
  for (let r = 0; r <= rows; r++) {
    for (let c = 0; c <= cols; c++) {
      cartos.push(Cesium.Cartographic.fromDegrees(minLon + c * dLon, minLat + r * dLat))
    }
  }

  // 3. 高程采样：13 级优先（~19m，与网格匹配），拿到的有效点不足一半时降级到 11 级
  //    重采（瓦片少、更不容易被限流），仍不足再逐点 getHeight 兜底。
  //    —— 这一步必须保证"有真实起伏"，否则所有点都是同一个兜底高程，坡度全 0、
  //    网格会被 <4° 过滤得干干净净（表现为"切到坡度着色但画面没反应"）。
  const reset = () => cartos.forEach((pt) => { pt.height = undefined as any })
  const validCount = () => cartos.filter((pt) => Number.isFinite(pt.height)).length
  let valid = 0

  for (const level of [13, 11]) {
    reset()
    try {
      await Cesium.sampleTerrain(viewer.terrainProvider, level, cartos)
    } catch { /* 继续降级 */ }
    valid = validCount()
    if (valid >= cartos.length * 0.9) break
  }

  if (valid < cartos.length * 0.9) {
    for (const pt of cartos) {
      if (Number.isFinite(pt.height)) continue
      const h = viewer.scene.globe.getHeight(pt)
      if (Number.isFinite(h)) pt.height = h
    }
  }
  // 最后兜底：仍无高度的点用邻域均值，避免出现"0 坡度"的假平地
  for (let i = 0; i < cartos.length; i++) {
    if (Number.isFinite(cartos[i].height)) continue
    const nb = [cartos[i - 1], cartos[i + 1], cartos[i - cols - 1], cartos[i + cols + 1]]
      .filter((p) => p && Number.isFinite(p.height))
    cartos[i].height = nb.length ? nb.reduce((s, p) => s + p.height, 0) / nb.length : 1988.0
  }
  console.info('DBG slope sample', JSON.stringify({ total: cartos.length, valid }))

  // 4. 逐格中心差分求坡度，按国标四级着色，贴地渲染（ClassificationType.TERRAIN
  //    保证 100% 贴合三维表面，不悬空不穿模）
  const dxMeters = dLon * 111320 * Math.cos(Cesium.Math.toRadians(24.715))
  const dyMeters = dLat * 110574

  let count = 0
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const idx = r * (cols + 1) + c
      const h00 = cartos[idx].height
      const h10 = cartos[idx + 1].height
      const h01 = cartos[idx + (cols + 1)].height
      const dzdx = (h10 - h00) / dxMeters
      const dzdy = (h01 - h00) / dyMeters
      const slopeDeg = Cesium.Math.toDegrees(Math.atan(Math.sqrt(dzdx * dzdx + dzdy * dzdy)))

      // <4° 的平地/水面不画，露出底图影像，画面更干净
      if (slopeDeg < 4.0) continue

      // 四级着色：<15°绿 / 15-28°黄 / 28-40°橙 / >40° 极高危红
      let colorHex = 'rgba(34, 197, 94, 0.35)'
      if (slopeDeg >= 40) colorHex = 'rgba(239, 68, 68, 0.68)'
      else if (slopeDeg >= 28) colorHex = 'rgba(249, 115, 22, 0.55)'
      else if (slopeDeg >= 15) colorHex = 'rgba(234, 179, 8, 0.45)'

      const lon1 = minLon + c * dLon
      const lat1 = minLat + r * dLat
      ds.entities.add({
        polygon: {
          hierarchy: Cesium.Cartesian3.fromDegreesArray([
            lon1, lat1,
            lon1 + dLon, lat1,
            lon1 + dLon, lat1 + dLat,
            lon1, lat1 + dLat
          ]),
          material: Cesium.Color.fromCssColorString(colorHex),
          classificationType: Cesium.ClassificationType.TERRAIN
        }
      })
      count++
    }
  }
  return count
}

export function clearSlopeGrid() {
  // 新版：整体移除 CustomDataSource
  const ds: any = mine.layers.slopeGridDS
  if (ds && mine.viewer && !mine.viewer.isDestroyed()) {
    try { mine.viewer.dataSources.remove(ds, true) } catch { /* 已销毁 */ }
  }
  delete mine.layers.slopeGridDS
  // 兼容旧版 mars3d 图层（若存在）
  const layer: any = mine.layers.slopeGrid
  if (layer) {
    layer.clear()
    mine.map.removeLayer(layer, true)
    delete mine.layers.slopeGrid
  }
  if (mine.viewer?.scene?.globe) mine.viewer.scene.globe.enableLighting = false
}

/**
 * 地形材质切换：等高线（GPU 球面材质）
 */
export function toggleTerrainMaterial(mode: 'none' | 'contour' | 'slope') {
  const globe = mine.viewer?.scene?.globe
  if (!globe) return
  if (mode === 'none') {
    globe.material = undefined
    clearSlopeGrid()
    return
  }
  if (mode === 'slope') {
    globe.material = undefined
    renderSlopeGrid()
    return
  }
  clearSlopeGrid()
  const material = Cesium.Material.fromType('ElevationContour')
  material.uniforms.spacing = 20.0
  material.uniforms.width = 1.5
  material.uniforms.color = Cesium.Color.fromCssColorString('#facc15')
  globe.material = material
}


export function startPitExcavation(depth: number = 50) {
  const map = mine.map
  if (!map) return
  if (!mine.things.terrainClip) {
    const tc = new mars3d.thing.TerrainClip({
      diffHeight: depth,
      image: '//data.mars3d.cn/textures/poly-stone.jpg',
      imageBottom: '//data.mars3d.cn/textures/divider-h1.png',
      splitNum: 80
    })
    map.addThing(tc)
    mine.things.terrainClip = tc
  }
  const tc: any = mine.things.terrainClip
  tc.options.diffHeight = depth
  map.graphicLayer.startDraw({
    type: 'polygon',
    style: { color: '#00ffff', opacity: 0.2, outline: true, outlineColor: '#00ffff' }
  }).then((graphic: any) => {
    const positions = graphic.positionsShow
    map.graphicLayer.clear()
    tc.clear()
    tc.addArea(positions)
  })
}

export function calculateEarthworkVolume(onResult: (r: { cut: number; fill: number; area: number }) => void) {
  const map = mine.map
  if (!map) return
  // mars3d 3.11 没有 thing.MeasureVolume，土方量由 thing.Measure 的 volume() 方法提供
  let m: any = mine.things.measure
  if (!m) {
    m = new mars3d.thing.Measure({
      label: { font_size: 16, color: '#ffffff', background: true, backgroundColor: 'rgba(15,23,42,0.9)' }
    })
    map.addThing(m)
    m.on(mars3d.EventType.end, () => {
      const g = m.graphics?.[m.graphics.length - 1]
      const r = g?.measured ?? {}
      onResult({
        cut: Math.round(r.digVolume ?? r.cutVolume ?? 0),
        fill: Math.round(r.fillVolume ?? 0),
        area: Math.round(r.area ?? 0)
      })
    })
    mine.things.measure = m
  }
  m.volume({
    showDigVolume: true,
    showFillVolume: true,
    showArea: true,
    exact: true,
    style: { color: '#00e5ff', opacity: 0.35, outline: true, outlineColor: '#00e5ff' }
  })
}

export function startDamBreach(polygonCoords: number[][], minElev = 1910, maxElev = 1965, speed = 2) {
  const map = mine.map
  if (!map || !map.viewer) return
  // 若已在推演，先清理旧水面
  stopDamBreach()
  const rise = Math.max(1, maxElev - minElev)
  // UI 的 speed 为抬升速率(m/s)，换算为演进时长并夹取到可观察区间
  const durationSec = Math.min(120, Math.max(6, rise / Math.max(0.1, speed)))
  const water = new DamBreachWater(map.viewer, {
    ring: polygonCoords,
    startElev: minElev,
    maxElev,
    durationSec
  })
  water.start()
  mine.things.flood = water as unknown as mars3d.thing.FloodByMaterial
}

export function stopDamBreach() {
  const water = mine.things.flood as unknown as DamBreachWater | null
  if (water && typeof (water as DamBreachWater).stop === 'function') {
    ;(water as DamBreachWater).stop()
  }
  mine.things.flood = null
}

/** 主滑方向地形高程剖面采样（供 ECharts 绘图） */
export async function sampleSlopeProfile(
  startLL: [number, number],
  endLL: [number, number],
  samples = 120
): Promise<{ step: number; elevation: number; dist: number }[]> {
  const map = mine.map
  if (!map) return []
  const toRad = Cesium.Math.toRadians
  const start = Cesium.Cartographic.fromDegrees(startLL[0], startLL[1])
  const end = Cesium.Cartographic.fromDegrees(endLL[0], endLL[1])
  const positions: Cesium.Cartographic[] = []
  for (let i = 0; i <= samples; i++) {
    const f = i / samples
    positions.push(new Cesium.Cartographic(
      Cesium.Math.lerp(start.longitude, end.longitude, f),
      Cesium.Math.lerp(start.latitude, end.latitude, f)
    ))
  }
  const updated = await Cesium.sampleTerrainMostDetailed(
    map.viewer.terrainProvider, positions)
  const a = startLL, b = endLL
  const totalM = Math.hypot((b[0] - a[0]) * 111320 * Math.cos(toRad(a[1])), (b[1] - a[1]) * 110540)
  return updated.map((p, idx) => ({
    step: idx,
    dist: Math.round((idx / samples) * totalM),
    elevation: Number(p.height.toFixed(2))
  }))
}

/** 沿边坡画一条剖面线 */
export function drawProfileLine(onDone: (positions: [number, number][]) => void) {
  const map = mine.map
  if (!map) return
  map.graphicLayer.startDraw({ type: 'polyline', style: { color: '#ffdd57', width: 4 } })
    .then((graphic: any) => {
      const pts: [number, number][] = graphic.positionsShow.map((p: any) => {
        const c = Cesium.Cartographic.fromCartesian(p)
        return [Cesium.Math.toDegrees(c.longitude), Cesium.Math.toDegrees(c.latitude)]
      })
      map.graphicLayer.clear()
      onDone(pts)
    })
}

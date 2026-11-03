/**
 * 溃坝演进水面（Entity + CallbackProperty 实现）
 *
 * 为什么不用 Primitive + Water 材质：
 *   1) mars3d 3.11.8 的 FloodByMaterial 依赖修改版 Cesium 的内部回调
 *      （GlobeSurfaceTileProvider._initByMars3D），当前 mars3d-cesium 1.146 构建里缺失，
 *      marsOptions 恒为 undefined，addThing 直接抛 TypeError；
 *   2) 自己拼 Primitive + EllipsoidSurfaceAppearance + Water fabric 时，
 *      在部分 GPU/ANGLE 环境下会走到 per-instance attribute 路径并抛
 *      "Vertex texture fetch support is required..."，整场景 renderError 停摆。
 *   3) Entity 走 Cesium 常规渲染路径，且 height 可用 CallbackProperty 逐帧驱动，
 *      不需要每一帧重建几何，既稳定又省开销。
 *
 * 视觉：库区半透明水体，水位按 easeOutCubic 抬升，配合轮廓线强调淹没边界。
 */
import * as Cesium from 'mars3d-cesium'

export interface DamBreachOptions {
  /** 库区多边形环（经纬度，首尾可不闭合） */
  ring: number[][]
  /** 起始水位（海拔 m） */
  startElev: number
  /** 最高水位（海拔 m） */
  maxElev: number
  /** 演进总时长（秒） */
  durationSec: number
  /** 基础水色 */
  baseColor?: Cesium.Color
}

export class DamBreachWater {
  private viewer: Cesium.Viewer
  private entity: Cesium.Entity | null = null
  private outline: Cesium.Entity | null = null
  private startTime = 0
  private opts: DamBreachOptions
  private currentLevel = 0
  private running = false
  private elapsed = 0

  constructor(viewer: Cesium.Viewer, opts: DamBreachOptions) {
    this.viewer = viewer
    this.opts = opts
    this.currentLevel = opts.startElev
  }

  get level(): number {
    return this.currentLevel
  }

  /** 当前水位（供 UI 读取） */
  private computeLevel(): number {
    const frac = Math.min(1, this.elapsed / Math.max(1, this.opts.durationSec))
    // easeOutCubic：溃坝初期洪峰快速下泄，后期趋缓
    const eased = 1 - Math.pow(1 - frac, 3)
    return this.opts.startElev + (this.opts.maxElev - this.opts.startElev) * eased
  }

  start(): void {
    if (this.running) return
    this.running = true
    this.startTime = performance.now()
    this.elapsed = 0
    this.currentLevel = this.opts.startElev

    const positions = this.opts.ring.map((p) => Cesium.Cartesian3.fromDegrees(p[0], p[1]))
    const hierarchy = new Cesium.PolygonHierarchy(positions)
    const color = (this.opts.baseColor ?? Cesium.Color.fromCssColorString('#2f7fd0')).withAlpha(0.55)

    this.entity = this.viewer.entities.add({
      name: 'dam-breach-water',
      polygon: {
        hierarchy,
        // 关键：高度由 CallbackProperty 每帧计算，几何不重建
        height: new Cesium.CallbackProperty(() => this.currentLevel, false),
        // 必须显式包成 ColorMaterialProperty，直接传 Color 时部分构建会退化
        // 成无材质白面（截图里表现为刺眼白块）
        material: new Cesium.ColorMaterialProperty(color),
        perPositionHeight: false,
        arcType: Cesium.ArcType.GEODESIC
      }
    })

    // 淹没边界：单独用 polyline 描边（polygon 的 outlineWidth 在 Windows/ANGLE 下不生效）
    const ringClosed = this.opts.ring.slice()
    const first = ringClosed[0], last = ringClosed[ringClosed.length - 1]
    if (first && last && (first[0] !== last[0] || first[1] !== last[1])) ringClosed.push(first)
    this.outline = this.viewer.entities.add({
      name: 'dam-breach-outline',
      polyline: {
        // 顶点高度跟随当前水位，逐帧重投影（环只有几十个点，开销可忽略）
        positions: new Cesium.CallbackProperty(
          () => ringClosed.map((p) => Cesium.Cartesian3.fromDegrees(p[0], p[1], this.currentLevel)),
          false),
        width: 2.5,
        material: new Cesium.ColorMaterialProperty(
          Cesium.Color.fromCssColorString('#7fd8ff').withAlpha(0.95)),
        arcType: Cesium.ArcType.GEODESIC
      }
    })

    this.viewer.scene.preUpdate.addEventListener(this.tick)
  }

  private tick = (): void => {
    if (!this.running) return
    this.elapsed = (performance.now() - this.startTime) / 1000
    this.currentLevel = this.computeLevel()
  }

  stop(): void {
    this.running = false
    this.viewer.scene.preUpdate.removeEventListener(this.tick)
    if (this.entity) {
      this.viewer.entities.remove(this.entity)
      this.entity = null
    }
    if (this.outline) {
      this.viewer.entities.remove(this.outline)
      this.outline = null
    }
  }
}

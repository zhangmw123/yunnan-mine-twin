/**
 * AWS Terrarium 地形瓦片提供器（免 Key 真实地形）
 * 数据源: s3.amazonaws.com/elevation-tiles-prod/terrarium (Amazon Terrain Tiles, 公开免鉴权)
 * 解码: elevation = R*256 + G + B/256 - 32768
 *
 * 重要：Terrarium 瓦片是标准 Web Mercator XYZ 瓦片（EPSG:3857），
 * 必须使用 WebMercatorTilingScheme 且 z = level（不能偏移），
 * 否则地形与影像投影不一致、地貌整体错位甚至瓦片全部加载失败。
 */
import * as Cesium from 'mars3d-cesium'

const TILE_URL = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
const HEIGHTMAP_WIDTH = 65
const MAX_LEVEL = 14

const tileCache = new Map<string, Promise<Float32Array | null>>()
const canvas = typeof document !== 'undefined' ? document.createElement('canvas') : null
if (canvas) {
  canvas.width = 256
  canvas.height = 256
}

async function fetchTile(z: number, x: number, y: number, attempt = 0): Promise<Float32Array | null> {
  const key = `${z}/${x}/${y}`
  const hit = tileCache.get(key)
  if (hit) return hit

  const load = async (n: number): Promise<Float32Array | null> => {
    try {
      const url = TILE_URL.replace('{z}', String(z)).replace('{x}', String(x)).replace('{y}', String(y))
      const resp = await fetch(url, { mode: 'cors' })
      if (!resp.ok) throw new Error(String(resp.status))
      const bmp = await createImageBitmap(await resp.blob())
      const ctx = canvas!.getContext('2d', { willReadFrequently: true })!
      ctx.clearRect(0, 0, 256, 256)
      ctx.drawImage(bmp, 0, 0)
      const data = ctx.getImageData(0, 0, 256, 256).data
      const buf = new Float32Array(HEIGHTMAP_WIDTH * HEIGHTMAP_WIDTH)
      for (let row = 0; row < HEIGHTMAP_WIDTH; row++) {
        const py = Math.min(255, Math.round((row / (HEIGHTMAP_WIDTH - 1)) * 255))
        for (let col = 0; col < HEIGHTMAP_WIDTH; col++) {
          const px = Math.min(255, Math.round((col / (HEIGHTMAP_WIDTH - 1)) * 255))
          const i = (py * 256 + px) * 4
          buf[row * HEIGHTMAP_WIDTH + col] = data[i] * 256 + data[i + 1] + data[i + 2] / 256 - 32768
        }
      }
      return buf
    } catch {
      if (n < 2) {
        await new Promise((r) => setTimeout(r, 600 * (n + 1)))
        return load(n + 1)
      }
      return null
    }
  }

  const p = load(attempt)
  tileCache.set(key, p)
  return p
}

export class TerrariumTerrainProvider {
  tilingScheme = new Cesium.WebMercatorTilingScheme()
  ready = true
  readyPromise = Promise.resolve(true)
  errorEvent = new Cesium.Event()
  credit = new Cesium.Credit('Terrain: AWS Open Data / Mapzen')
  hasWaterMask = false
  hasVertexNormals = false
  availability: any = undefined
  requestWaterMask = false
  requestVertexNormals = false

  async requestTileGeometry(x: number, y: number, level: number): Promise<any> {
    const buf = await fetchTile(level, x, y)
    // 取不到瓦片时返回「零高度」占位数据，绝不返回 undefined：
    // Cesium 渲染管线在部分路径下遇到空地形数据会抛 rendering error 并停止整帧渲染
    const data = buf ?? new Float32Array(HEIGHTMAP_WIDTH * HEIGHTMAP_WIDTH)
    return new Cesium.HeightmapTerrainData({
      buffer: data,
      width: HEIGHTMAP_WIDTH,
      height: HEIGHTMAP_WIDTH,
      childTileMask: level >= MAX_LEVEL || !buf ? 0 : 15
    })
  }

  getLevelMaximumGeometricError(level: number): number {
    const levelZero =
      Cesium.TerrainProvider.getEstimatedLevelZeroGeometricErrorForAHeightmap(
        Cesium.Ellipsoid.WGS84.maximumRadius, HEIGHTMAP_WIDTH, this.tilingScheme.getNumberOfXTilesAtLevel(0))
    return levelZero / (1 << level)
  }

  getTileDataAvailable(x: number, y: number, level: number): boolean {
    return level <= MAX_LEVEL
  }
}

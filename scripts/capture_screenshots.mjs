/**
 * 正式功能截图（有头模式，真 GPU 渲染）：
 *   node scripts/capture_screenshots.mjs
 * 前置: npm i playwright && npx playwright install chromium，且前后端服务已启动
 * 说明: SwiftShader 无头渲染 Cesium 会黑屏/无光照，必须 headless:false 用真显卡。
 *       运行时会弹出浏览器窗口，脚本结束自动关闭。
 *       OUT_DIR 可通过环境变量覆盖输出目录；ONLY=01,05 可只重拍指定几张。
 */
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const OUT = (process.env.OUT_DIR || path.resolve(__dirname, '../docs/screenshots')) + path.sep
const BASE = process.env.BASE_URL || 'http://localhost:5174'
const ONLY = (process.env.ONLY || '').split(',').filter(Boolean)

const browser = await chromium.launch({
  headless: false,
  args: ['--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--window-size=1936,1170']
})
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
page.setDefaultTimeout(180000)

const want = (k) => !ONLY.length || ONLY.includes(k)

/**
 * 关键：goto 到同一 URL 只有 hash 不同时浏览器不会重新加载文档，
 * onMounted 里的 hash 分支永远不会执行 —— 必须先回 about:blank 强制新文档。
 */
async function shot(hash, file, waitMs, extra) {
  await page.goto('about:blank')
  await page.goto(BASE + '/' + hash, { waitUntil: 'load' })
  // 等 Cesium 场景 + 影像瓦片稳定：先等固定时长，再等瓦片队列清空
  await page.waitForTimeout(waitMs)
  await page.waitForFunction(() => {
    const tq = window.__mine?.map?.viewer?.scene?.globe?.tilesLoaded
    return typeof tq === 'undefined' ? true : tq
  }, { timeout: 60000 }).catch(() => {})
  if (extra) { await extra(); await page.waitForTimeout(12000) }
  await page.screenshot({ path: OUT + file, timeout: 120000 })
  console.log('saved', file)
}

// 影像瓦片走公网 ArcGIS，首次冷启动要 60~90s 才能铺满整个视野
const LOAD_WAIT = 75000
const SCENE_WAIT = 70000   // hash 场景在 12s 后触发，再留 58s 给接口请求、渲染与瓦片加载

if (want('01')) await shot('', '01-总体态势.png', LOAD_WAIT)
if (want('02')) await shot('#shot=impact', '02-滑坡缓冲区.png', SCENE_WAIT)
if (want('03')) await shot('#shot=dam', '03-溃坝推演.png', SCENE_WAIT)
if (want('04')) await shot('#shot=sensor', '04-位移降雨耦合曲线.png', SCENE_WAIT)

// 05 矿卡近景：走前端 #shot=truck 场景 —— 先定格全部矿卡（WS 不再落盘、插值暂停），
// 再由前端读取车辆真实坐标、把相机架到车头前上方 18m。车不动，机位不会落空。
if (want('06')) await shot('#shot=contour', '06-等高线分析.png', SCENE_WAIT)
if (want('07')) await shot('#shot=slope', '07-坡度着色.png', SCENE_WAIT)
if (want('08')) await shot('#shot=follow', '08-跟随矿卡视角.png', SCENE_WAIT)

if (want('05')) {
  await shot('#shot=truck', '05-矿卡近景.png', 80000)
}

await browser.close()
console.log('done ->', OUT)

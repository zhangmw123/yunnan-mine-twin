/**
 * 演示视频录制：有头 Chromium（真 GPU）+ Playwright recordVideo，产出 docs/demo/*.webm
 *   node scripts/record_demo.mjs
 * 之后用 playwright 自带 ffmpeg 转 1080p H.264（见 scripts/README-demo.md 或 README §1）。
 *
 * 为什么不用无头：SwiftShader 软渲染下 Cesium 场景发黑、无光照，拍出来是废片。
 */
import { chromium } from 'playwright'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = process.env.BASE_URL || 'http://localhost:5174'
const OUT = process.env.OUT_DIR || path.resolve(__dirname, '../.runtime/demo')
// 录制分辨率：默认 1600×900。1920×1080 下单次 6 分钟录制到后半程（溃坝段）会因显存
// 吃紧出现瓦片被逐出且不回补，画面整片发黑；1600×900 像素少 30%，实测更稳。
// 需要 1080p 时：REC_W=1920 REC_H=1080 node scripts/record_demo.mjs
const W = +(process.env.REC_W || 1600), H = +(process.env.REC_H || 900)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await chromium.launch({
  headless: false,
  args: ['--ignore-gpu-blocklist', '--enable-gpu-rasterization', `--window-size=${W + 16},${H + 90}`]
})
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 1,
  recordVideo: { dir: OUT, size: { width: W, height: H } }
})
const p = await ctx.newPage()
p.setDefaultTimeout(180000)
const T0 = Date.now()  // 录屏起点，用于片头裁剪

// ---------- 页面内演示层：虚拟鼠标 / 点击水波 / 字幕 / 标题卡 ----------
await p.addInitScript(() => {
  const ready = (fn) => (document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', fn) : fn())
  ready(() => {
    if (window.__demo2) return
    const style = document.createElement('style')
    style.textContent = `
      #d2-cursor{position:fixed;z-index:99998;left:0;top:0;pointer-events:none;filter:drop-shadow(0 2px 6px rgba(0,0,0,.65))}
      #d2-ripple{position:fixed;z-index:99997;pointer-events:none;border:3px solid rgba(76,201,240,.95);border-radius:50%;opacity:0}
      #d2-ripple.go{animation:d2Ripple .55s ease-out}
      @keyframes d2Ripple{0%{opacity:.95;transform:scale(.3)}100%{opacity:0;transform:scale(1.7)}}
      #d2-caption{position:fixed;z-index:99999;left:50%;bottom:56px;transform:translateX(-50%) translateY(14px);
        max-width:1280px;padding:13px 30px;background:rgba(3,15,28,.9);border:1px solid rgba(76,201,240,.4);
        border-left:3px solid #4cc9f0;border-radius:10px;color:#e8f6ff;font:600 24px/1.5 "Microsoft YaHei",sans-serif;
        letter-spacing:.5px;box-shadow:0 10px 44px rgba(0,0,0,.55),0 0 26px rgba(76,201,240,.12);
        opacity:0;transition:opacity .4s,transform .4s;pointer-events:none;text-align:center}
      #d2-caption.show{opacity:1;transform:translateX(-50%) translateY(0)}
      #d2-caption b{color:#4cc9f0}
      #d2-card{position:fixed;inset:0;z-index:100000;display:flex;flex-direction:column;align-items:center;justify-content:center;
        background:radial-gradient(1200px 700px at 50% 44%,rgba(12,44,72,.62),rgba(2,9,16,.975) 72%),rgba(2,9,16,.975);
        opacity:0;transition:opacity .7s;pointer-events:none;text-align:center;color:#eaf7ff;font-family:"Microsoft YaHei",sans-serif}
      #d2-card.show{opacity:1}
      #d2-card h1{font-size:54px;margin:0 0 16px;letter-spacing:3px;text-shadow:0 0 34px rgba(76,201,240,.45)}
      #d2-card .sub{font-size:21px;color:#8fc7e0;margin:0 0 30px;letter-spacing:1px}
      #d2-card .foot{font-size:18px;color:#5d8ba6;letter-spacing:2px}
      #d2-card ul{list-style:none;margin:0;padding:0;font-size:23px;line-height:2.15;color:#d9efff;text-align:left}
      #d2-card ul b{color:#4cc9f0;font-weight:700}
      #d2-card .badge{margin-top:32px;font-size:17px;color:#5d8ba6;letter-spacing:2px}
    `
    document.head.appendChild(style)

    const cur = document.createElement('div')
    cur.id = 'd2-cursor'
    cur.innerHTML = `<svg width="30" height="34" viewBox="0 0 30 34"><path d="M4 2 L4 27 L11.5 20.5 L16.5 31 L21.5 28.5 L16.5 18.5 L26 18 Z" fill="#eaf7ff" stroke="#0a2230" stroke-width="1.6"/></svg>`
    cur.style.transform = `translate(${window.innerWidth / 2}px,${window.innerHeight / 2}px)`
    document.body.appendChild(cur)

    const rip = document.createElement('div'); rip.id = 'd2-ripple'; document.body.appendChild(rip)
    const cap = document.createElement('div'); cap.id = 'd2-caption'; document.body.appendChild(cap)
    const card = document.createElement('div'); card.id = 'd2-card'; document.body.appendChild(card)

    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

    window.__demo2 = {
      async move(x, y, ms = 650) {
        const m = cur.style.transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/)
        const x0 = m ? +m[1] : window.innerWidth / 2
        const y0 = m ? +m[2] : window.innerHeight / 2
        const t0 = performance.now()
        return new Promise((res) => {
          const step = (now) => {
            const k = ease(Math.min(1, (now - t0) / ms))
            cur.style.transform = `translate(${x0 + (x - x0) * k}px,${y0 + (y - y0) * k}px)`
            performance.now() - t0 < ms ? requestAnimationFrame(step) : res()
          }
          requestAnimationFrame(step)
        })
      },
      ripple(x, y) {
        rip.style.left = x - 26 + 'px'; rip.style.top = y - 26 + 'px'
        rip.style.width = rip.style.height = '52px'
        rip.classList.remove('go'); void rip.offsetWidth; rip.classList.add('go')
      },
      say(html, ms = 4200) {
        cap.innerHTML = html
        cap.classList.add('show')
        return sleep(ms).then(() => { cap.classList.remove('show'); return sleep(400) })
      },
      hold() { cap.classList.add('show') },
      drop() { cap.classList.remove('show') },
      async title(o, ms = 5000) {
        card.innerHTML = o.html
        card.classList.add('show')
        await sleep(ms)
        card.classList.remove('show')
        await sleep(800)
      }
    }
  })
})

await p.goto(BASE, { waitUntil: 'load', timeout: 120000 })

// 应用就绪：地图实例 + 真实地形 + 矿卡已建
await p.waitForFunction(() => {
  const m = window.__mine
  return !!(m && m.map && m.terrainOk && Object.keys(m.vehicles || {}).length > 0)
}, { timeout: 180000 })
// 影像瓦片铺满（冷启动 60~90s）
await p.waitForFunction(() => window.__mine?.map?.viewer?.scene?.globe?.tilesLoaded === true, { timeout: 180000 }).catch(() => {})
await sleep(6000)

// ---------- 辅助 ----------
const demo = (name, ...args) => p.evaluate(([n, ...a]) => window.__demo2[n](...a), [name, ...args])

/** 平滑飞行：用 Cesium 原生 flyTo，destination 为绝对椭球高 */
async function flyTo(lng, lat, alt, heading, pitch, duration = 4) {
  await p.evaluate(({ lng, lat, alt, heading, pitch, duration }) => {
    const C = window.Cesium
    window.__mine.viewer.camera.flyTo({
      destination: C.Cartesian3.fromDegrees(lng, lat, alt),
      orientation: { heading: C.Math.toRadians(heading), pitch: C.Math.toRadians(pitch), roll: 0 },
      duration,
      easingFunction: C.EasingFunction.QUADRATIC_IN_OUT
    })
  }, { lng, lat, alt, heading, pitch, duration })
  await sleep(duration * 1000 + 600)
  await settle()
}

/** 等当前视野的瓦片铺完 —— 不等的话前景会出现没贴图的黑色地块（录制时最扎眼的问题） */
async function settle(maxMs = 12000) {
  const t0 = Date.now()
  while (Date.now() - t0 < maxMs) {
    const ok = await p.evaluate(() => {
      const g = window.__mine?.map?.viewer?.scene?.globe
      return !!g && g.tilesLoaded === true
    }).catch(() => false)
    if (ok) { await sleep(300); return }
    await sleep(350)
  }
  await sleep(1200)
}

async function clickEl(sel, text, note) {
  const loc = text ? p.locator(sel, { hasText: text }).first() : p.locator(sel).first()
  const box = await loc.boundingBox()
  if (!box) throw new Error('not found: ' + sel + ' ' + (text || ''))
  const x = box.x + box.width / 2, y = box.y + box.height / 2
  await demo('move', x, y, 620)
  await demo('ripple', x, y)
  await sleep(160)
  await loc.click()
  await sleep(500)
  if (note) console.log('clicked:', note)
  return box
}

/** 直接改原生控件值并派发事件（避开下拉展开的动画，画面更干净） */
async function setControl(sel, value, evt = 'change') {
  await p.evaluate(({ sel, value, evt }) => {
    const el = document.querySelector(sel)
    if (!el) throw new Error('no control ' + sel)
    el.value = String(value)
    el.dispatchEvent(new Event(evt, { bubbles: true }))
  }, { sel, value, evt })
  await sleep(400)
}

// ---------- 预热（会被片头裁掉）：先降低地形屏幕误差阈值并逐机位预加载，
// 否则低空机位瓦片永远收敛不了、画面里会露出没贴图的黑色地块 ----------
await p.evaluate(() => { window.__mine.viewer.scene.globe.maximumScreenSpaceError = 16 })

async function warmAt(lng, lat, alt, heading, pitch) {
  await p.evaluate(({ lng, lat, alt, heading, pitch }) => {
    const C = window.Cesium
    window.__mine.viewer.camera.setView({
      destination: C.Cartesian3.fromDegrees(lng, lat, alt),
      orientation: { heading: C.Math.toRadians(heading), pitch: C.Math.toRadians(pitch), roll: 0 }
    })
  }, { lng, lat, alt, heading, pitch })
  await settle(26000)
}

const WARM = [
  [102.5605, 24.6965, 5200, 358, -40],
  [102.5605, 24.7005, 4000, 356, -44],
  [102.5612, 24.7065, 3300, 350, -34],
  [102.5612, 24.7090, 3400, 2, -46],
  [102.5614, 24.7135, 3100, 0, -32],
  [102.5467, 24.6955, 2500, 0, -42],
  [102.5467, 24.7035, 3600, 0, -32]
]
for (const w of WARM) { await warmAt(...w); console.log('warmed', w.join(',')) }

// 跟车视角是贴地 6.5m，瓦片需求最高 —— 先让相机跟着车跑一段把沿途瓦片拉进缓存
const setFollow = (on) => p.evaluate((on) => {
  const sel = [...document.querySelectorAll('select.mini-select')].find((s) =>
    [...s.options].some((o) => /驾驶视角/.test(o.textContent)))
  const opt = [...sel.options].find((o) => /驾驶视角/.test(o.textContent))
  sel.value = on ? opt.value : ''
  sel.dispatchEvent(new Event('change', { bubbles: true }))
  // 双保险：直接改运行时状态。实测只靠下拉框的 change 事件偶尔不生效，
  // 相机会一直绑在车上，把后面的片头与 S1 全拍成贴地跟车画面。
  if (window.__mine) window.__mine.followTruck = on ? opt.value : null
}, on)

await setFollow(true)
await sleep(22000)
await setFollow(false)
await sleep(1200)

// ---------- S0 开场 ----------
const DEMO_START_SEC = (Date.now() - T0) / 1000
console.log('DEMO_START_SEC=' + DEMO_START_SEC.toFixed(1))
await flyTo(102.5605, 24.6965, 5200, 358, -40, 0)
await demo('title', { html: `
  <h1>云南高原露天矿山三维形变监测</h1>
  <p class="sub">与尾矿库溃坝推演系统 &nbsp;·&nbsp; Kunyang Phosphate Mine Digital Twin</p>
  <div class="foot">Vue3 + Mars3D/Cesium &nbsp;·&nbsp; FastAPI + PostGIS &nbsp;·&nbsp; 真实地形 / 影像 / 气象</div>
` }, 5200)

// ---------- S1 三维底座 ----------
await flyTo(102.5605, 24.7005, 4000, 356, -44, 4)
await demo('say', '昆阳磷矿二号露天采场：<b>真实地形 + 亚米级影像</b>，零 Key 接入 ArcGIS WorldElevation3D', 4400)
await flyTo(102.5612, 24.7065, 3300, 350, -34, 3.5)
await demo('say', '<b>6 个功能分区 · 58 条真实运输道路 · 50 个监测点 · 6 台矿卡</b> 1Hz WebSocket 推流', 4400)

// ---------- S2 图层与地形夸张 ----------
await clickEl('.chk', '监测传感器', 'toggle sensors off')
await clickEl('.chk', '监测传感器', 'toggle sensors on')
await setControl('.slider-row input[type=range]', 2.4, 'input')
await demo('say', '图层树独立开关 · 地形夸张 <b>1x → 2.4x</b>，高陡边坡起伏一目了然', 3600)
await setControl('.slider-row input[type=range]', 1, 'input')
await sleep(600)

// ---------- S3 等高线 ----------
await flyTo(102.5612, 24.7090, 3400, 2, -46, 3.5)
await setControl('select.mini-select', 'contour')
await sleep(2200)
await demo('say', '<b>20m 等高线</b>：Cesium GPU 球面材质实时渲染，贴合采坑台阶', 4200)

// ---------- S4 坡度分级 ----------
await setControl('select.mini-select', 'slope')
// 等网格实体真正建好（DEM 采样 + 贴地多边形，通常 3~6s）
await p.waitForFunction(() => {
  const ds = window.__mine?.layers?.slopeGridDS
  return !!ds && ds.entities.values.length > 100
}, { timeout: 60000 }).catch(() => {})
await sleep(2500)
await demo('say', '边坡<b>坡度分级</b>：DEM 网格差分求坡度，绿 / 黄 / 橙 / 红四级贴地色块', 4600)
await sleep(800)
await setControl('select.mini-select', 'none')
await sleep(900)

// ---------- S5 滑坡预警联动 ----------
await flyTo(102.5614, 24.7135, 3100, 0, -32, 3.5)
await demo('say', '红色告警：GNSS-N-08 位移速率 <b>12mm/d</b>，进入加速蠕变阶段', 3600)
await clickEl('.btn', '生成 100/300/500m', 'buffer')
await p.waitForFunction(() => !!document.querySelector('.result-card .threat-item, .result-card'), { timeout: 60000 }).catch(() => {})
await sleep(1800)
await demo('say', '<b>ST_Buffer 三环贴地缓冲区</b> + ST_DWithin 检索区内矿卡并分级', 4200)
await clickEl('.btn.warn', '', 'evacuate')
await sleep(1500)
await demo('say', '一键下发<b>声光撤离指令</b>，WebSocket 广播到现场终端', 3400)

// ---------- S6 位移-降雨耦合曲线 ----------
await p.evaluate(() => { window.__mine.selectedSensor = null })
await sleep(300)
await p.evaluate(() => { window.__mine.selectedSensor = 'GNSS-N-08' })
await sleep(3800)
await demo('say', '<b>72 小时「位移速率 — 降雨量」双因子耦合曲线</b>，降雨滞后响应清晰可辨', 4400)
await clickEl('.chart-header .btn', '', 'close chart')
await sleep(900)

// ---------- S7 溃坝推演 ----------
// 机位不在这里设：点「启动溃坝推演」时 runDamBreach 会自己把相机带到库区南侧
// 3600m / 俯角 -50° 的机位（2500m 会因瓦片请求爆量整片发黑）。这里只负责等它收敛。
await clickEl('.btn', '启动溃坝推演', 'dam breach')
await demo('say', '尾矿库溃坝推演：水位按<b>实测库底 1989m</b> 标定，30m 涨幅 ≈ 100 分钟演进', 4800)
await settle(22000)
await demo('say', '淹没面沿山谷地形逐米抬升，面板实时跳字：<b>水位 / 水深 / 淹没面积</b>', 4800)
await sleep(1500)

// ---------- S8 跟车巡检 ----------
await setFollow(true)
await sleep(4600)
await demo('say', '<b>跟车巡检</b>：相机绑定车头位置与航向，车后 22m 跟拍巡查盘山道路', 4400)
await setFollow(false)
await sleep(600)

// ---------- S9 结尾 ----------
await flyTo(102.5605, 24.7000, 4400, 358, -42, 3.5)
await demo('say', '从<b>感知 → 空间计算 → 三维分析 → 推演</b>的完整链路，全部可复现', 3600)
await demo('title', { html: `
  <h1 style="font-size:42px">工程亮点</h1>
  <ul>
    <li><b>真实底座</b>：ArcGIS 地形 + 亚米影像 + Open-Meteo 实况，自研 Terrarium 源兜底</li>
    <li><b>空间计算</b>：PostGIS ST_Buffer / ST_DWithin，50 点位 72h 时序落库</li>
    <li><b>三维分析</b>：地形开挖 · 土方量算 · 剖面 · 20m 等高线 · DEM 坡度分级</li>
    <li><b>溃坝推演</b>：CallbackProperty 驱动水面，库容曲线实时估算面积与水深</li>
  </ul>
  <div class="badge">YUNNAN MINE DIGITAL TWIN &nbsp;·&nbsp; 2026</div>
` }, 5600)

await sleep(800)
await ctx.close()
const video = await p.video()
console.log('VIDEO:', video ? await video.path() : '(none)')
await browser.close()

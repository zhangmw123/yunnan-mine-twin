/** 后端 API 封装 */
import { mine } from './store'

const BASE = ''

export async function apiGet(path: string) {
  const resp = await fetch(BASE + path)
  return resp.json()
}

export async function apiPost(path: string, body: any) {
  const resp = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  return resp.json()
}

export function connectTwinWs(onMessage: (data: any) => void) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/mine-twin`)
  // 暴露发送句柄，「一键声光撤离」等指令依赖它；此前漏了赋值导致按钮点击无反应
  mine.wsSend = (msg: string) => {
    try { ws.send(msg) } catch { /* socket 未就绪 */ }
  }
  ws.onopen = () => {
    mine.wsConnected = true
  }
  ws.onmessage = (ev) => {
    try { onMessage(JSON.parse(ev.data)) } catch { /* ignore */ }
  }
  ws.onclose = () => {
    mine.wsConnected = false
    setTimeout(() => connectTwinWs(onMessage), 3000)
  }
  return ws
}

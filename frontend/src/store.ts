/** 全局共享状态：地图实例与图层句柄（面板组件与地图组件解耦） */
import { reactive } from 'vue'

export const mine = reactive({
  map: null as any,
  viewer: null as any,
  terrainOk: false,
  terrainSource: '' as string,
  wsConnected: false,
  layers: {} as Record<string, any>,
  things: {} as Record<string, any>,
  selectedSensor: null as string | null,
  showChart: false,
  alerts: [] as any[],
  vehicles: {} as Record<string, any>,
  stats: { total_sensors: 0, red_alerts: 0, orange_alerts: 0, vehicles: 0, zones: 0 },
  wsSend: null as ((msg: string) => void) | null,
  /** 截图/演示模式：定格矿卡（跳过 WS 位置更新），车不动随便拍 */
  truckPaused: false,
  /** 硬冻结：连插值帧循环一起停，允许外部直接给矿卡赋予固定坐标（用于稳定取景） */
  truckFreeze: false,
  /** 跟车巡检：填 vehicle_code 即每帧把相机绑到该车驾驶视角，null 结束跟随 */
  followTruck: null as string | null
})

export const STATUS_COLORS = ['#2ecc71', '#3498db', '#e67e22', '#e74c3c']
export const STATUS_NAMES = ['正常', '蓝色关注', '橙色预警', '红色告警']

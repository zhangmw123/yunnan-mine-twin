# 演示视频

- 文件：`yunnan-mine-twin-demo.mp4`（1600×900 / H.264 / 25fps / 无音轨 / 4 分 25 秒）
- 章节：开场标题 → 三维底座 → 图层次序与地形夸张 → 20m 等高线 → 边坡坡度分级 → 滑坡三环缓冲与撤离 → 位移-降雨耦合曲线 → 尾矿库溃坝推演 → 全局远景 → 工程亮点

> 跟车巡检段未收入视频：该机位相机贴地约 8m，低空视野的地形瓦片在长时间录制中会被逐出且不回补，
> 拍出来背景是黑的（车辆本体正常）。功能本身可用，截图见 `docs/screenshots/05-矿卡近景.png`。

## 怎么重新录制

```bash
# 前置：前后端已启动（8001 / 5174），且已安装 playwright + chromium
node scripts/record_demo.mjs            # 产出 .runtime/demo/*.webm（约 7 分钟，含预热）
REC_W=1920 REC_H=1080 node scripts/record_demo.mjs   # 需要 1080p 时
```

脚本先用 `camera.setView` 把 7 个机位逐个预加载（这段会被裁掉），再开始正式演示。

**为什么必须预热**：低空机位下 ArcGIS 地形瓦片请求难以收敛，未加载区域会渲染成黑色地块。

## 转码与裁剪

Playwright 录的是 VP9 webm（体积大、浏览器兼容性一般），转成 H.264 MP4：

```bash
FF=~/.workbuddy/binaries/python/versions/3.13.12/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v9.0.2.exe
"$FF" -ss <片头卡起点> -i .runtime/demo/page@xxxx.webm \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -movflags +faststart \
  docs/demo/yunnan-mine-twin-demo.mp4
```

**`-ss` 不要直接用日志里的 `DEMO_START_SEC`**：录屏容器从 context 创建就开始计时，比脚本里取 `T0` 的时刻早若干秒，
实测两者差 6~16s，直接用会把片头标题卡切掉、正片开头残留一段贴地跟车画面。先抽帧定位：

```bash
"$FF" -ss 135 -t 60 -i .runtime/demo/page@xxxx.webm \
  -vf "fps=1/3,scale=320:-1,drawtext=text='%{pts\:hms}':x=4:y=4:fontsize=16:fontcolor=yellow:box=1:boxcolor=black,tile=6x4" \
  -frames:v 1 scan.jpg
```

看拼贴里深色全屏标题卡出现在第几格，用该时间戳减 1~2s 作为 `-ss`。

若某一段拍废（如跟车），用 `trim + concat` 剔除，避免整片重录：

```bash
"$FF" -y -i raw.mp4 -filter_complex \
  "[0:v]trim=0:248.4,setpts=PTS-STARTPTS[a];[0:v]trim=264,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]" \
  -map "[v]" -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p -movflags +faststart out.mp4
```

## 已知的坑（都已在代码/脚本里修掉）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 低空机位整片发黑，只剩水面/矢量线 | MSSE 默认 2，每像素索取过高层级瓦片，请求越等越多 | `globe.maximumScreenSpaceError = 16`（已写进 `MapContainer.vue`） |
| 点「启动溃坝推演」后画面全黑 | `runDamBreach` 把相机强制拉到 2500m / 俯角 -42°，该高度瓦片 24s 仍有 11 块在飞 | 相机改为 3600m / 俯角 -50°（画面下沿约 1.7km、中心约 3km，库区正好入画） |
| 片头与 S1 全是贴地跟车画面 | 只靠下拉框 `change` 事件退出跟车偶尔不生效，相机一直绑在车上，把后续 `flyTo` 全盖掉 | 录制脚本同时置 `window.__mine.followTruck = null` |
| 跟车画面下半屏是整块棕色车体 | 相机放在车辆自身坐标 +6.5m，等于贴进驾驶室内部 | 改为车后 22m、车顶上方 8m、俯角 -12° 的跟拍机位 |

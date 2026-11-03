import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { viteStaticCopy } from 'vite-plugin-static-copy'

export default defineConfig({
  plugins: [
    vue(),
    viteStaticCopy({
      targets: [
        { src: 'node_modules/mars3d-cesium/Build/Cesium/Workers', dest: 'lib/Cesium' },
        { src: 'node_modules/mars3d-cesium/Build/Cesium/ThirdParty', dest: 'lib/Cesium' },
        { src: 'node_modules/mars3d-cesium/Build/Cesium/Assets', dest: 'lib/Cesium' },
        { src: 'node_modules/mars3d-cesium/Build/Cesium/Widgets', dest: 'lib/Cesium' }
      ]
    })
  ],
  server: {
    // 必须显式绑定：默认只监听 IPv6 的 ::1，预览代理/127.0.0.1 会连不上导致白屏
    host: '0.0.0.0',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8001', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8001', ws: true }
    }
  },
  build: {
    chunkSizeWarningLimit: 5000
  }
})

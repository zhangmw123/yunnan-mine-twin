import { createApp } from 'vue'
import App from './App.vue'
import 'mars3d-cesium/Build/Cesium/Widgets/widgets.css'
import 'mars3d/mars3d.css'
import './style.css'
import * as Cesium from 'mars3d-cesium'
import * as mars3d from 'mars3d'
import { mine } from './store'

;(window as any).Cesium = Cesium
;(window as any).mars3d = mars3d
;(window as any).__mine = mine

createApp(App).mount('#app')

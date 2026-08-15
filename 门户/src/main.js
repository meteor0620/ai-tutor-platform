import { createApp } from 'vue'
import naive from 'naive-ui'
import './style.css'
import App from './App.vue'

// 深色主题由 App.vue 顶层的 <n-config-provider> 接管（见 theme.js）
createApp(App).use(naive).mount('#app')

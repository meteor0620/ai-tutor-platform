import { createApp } from 'vue'
import ArcoVue from '@arco-design/web-vue'
import '@arco-design/web-vue/dist/arco.css'
import './style.css'
import App from './App.vue'

// 深色主题（Arco 组件库）+ 科技渐变背景保留在 style.css 的 body 上
document.body.setAttribute('arco-theme', 'dark')

createApp(App).use(ArcoVue).mount('#app')

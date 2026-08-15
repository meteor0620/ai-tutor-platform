<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { createWidget } from 'l2d-widget'

let widget = null
// 单模型 koharu（元气少女，本地路径，稳定不依赖 CDN）
// 注：l2d-widget 在同一页面二次加载 Live2D 会卡死，故全程只用一个模型
onMounted(() => {
  widget = createWidget({
    model: { path: '/live2d/koharu/assets/koharu.model.json' },
    position: 'bottom-left',
    size: 280,
    primaryColor: 'rgba(99,102,241,0.9)', // 靛蓝，与平台品牌一致
    tips: {
      typing: { param: 'PARAM_MOUTH_OPEN_Y', speed: 200 },
      welcomeMessage: ['你好呀，我是你的学习伙伴～', '有问题随时问我！'],
      messages: ['做题累了就歇一会儿吧～', '点击我可以问问题哦'],
      duration: 4000,
      interval: 8000,
    },
  })
})

onBeforeUnmount(() => {
  if (widget) {
    try { widget.destroy() } catch (e) {}
    widget = null
  }
})
</script>

<template>
  <div class="mascot-host"></div>
</template>

<style scoped>
.mascot-host {
  pointer-events: none;
  position: fixed;
  left: 0;
  bottom: 0;
  z-index: 99;
}
.mascot-host :deep(*) {
  pointer-events: auto;
}
</style>

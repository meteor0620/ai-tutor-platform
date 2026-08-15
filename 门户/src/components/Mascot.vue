<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { createWidget } from 'l2d-widget'

let widget = null
const HIDE_KEY = 'mascot_hidden' // 记忆用户是否手动隐藏过（localStorage）

onMounted(() => {
  if (localStorage.getItem(HIDE_KEY) === '1') return
  widget = createWidget({
    // 官方模型 CDN（黑猫/白猫看板娘，萌系科技感，符合平台调性）
    model: [
      { path: 'https://model.hacxy.cn/cat-black/model.json' },
      { path: 'https://model.hacxy.cn/cat-white/model.json' },
    ],
    dockedPosition: 'left', // 左下角悬浮，避开对话页右侧输入区
    tips: {
      typing: { param: 'PARAM_MOUTH_OPEN_Y', speed: 200 },
      welcomeMessage: ['你好呀，我是你的 AI 助教伙伴～', '有问题随时问我！'],
      messages: ['做题累了就歇一会儿吧～', '点击我可以说悄悄话哦'],
      duration: 4000,
      interval: 8000,
    },
    statusBar: { disabled: false },
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

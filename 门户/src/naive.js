import { createDiscreteApi } from 'naive-ui'
import { appTheme } from './theme'

// 全局 message / dialog：Arco `Message` 与原生 `confirm` 的替代
// 模块级调用 createDiscreteApi，组件内外都能直接用，不受 provider 树限制
export const { message, dialog } = createDiscreteApi(['message', 'dialog'], {
  configProviderProps: appTheme,
})

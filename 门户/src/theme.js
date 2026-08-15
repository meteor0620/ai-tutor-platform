import { darkTheme } from 'naive-ui'

// Soybean Admin 品牌靛蓝 + 平台现有深蓝紫玻璃拟态基调
// 让 Naive 组件面（按钮/卡片/弹窗/表格）与 style.css 的玻璃卡同调
export const themeOverrides = {
  common: {
    primaryColor: '#6366f1',
    primaryColorHover: '#818cf8',
    primaryColorPressed: '#4f46e5',
    primaryColorSuppl: '#6366f1',
    bodyColor: '#0b1120',
    cardColor: '#131a2e',
    modalColor: '#1a2238',
    popoverColor: '#1a2238',
    tableColor: 'transparent',
    textColorBase: '#f8fafc',
    borderRadius: '8px',
    borderColor: 'rgba(255,255,255,0.12)',
  },
  Card: { borderColor: 'rgba(255,255,255,0.12)' },
  DataTable: { thColor: 'rgba(255,255,255,0.05)', tdColor: 'transparent' },
  Modal: { color: '#1a2238' },
}

export const appTheme = { theme: darkTheme, themeOverrides }

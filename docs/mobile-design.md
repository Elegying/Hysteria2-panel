# 移动管理客户端设计说明

Android v0.4.0 使用 Flutter 实现，借鉴 Apple 的界面层级与交互原则。它没有调用仅适用于 Apple 平台的 Liquid Glass API，也不宣称复制其光学折射实现。

## 文档研究与实现

- [Materials](https://developer.apple.com/design/human-interface-guidelines/materials)：区分导航与内容层。导航、弹窗保留裁剪模糊与高光边缘，数据卡片默认实色；高对比度模式关闭模糊。
- [Meet Liquid Glass](https://developer.apple.com/videos/play/wwdc2025/219/)：避免玻璃层反复叠加。首页通过深色主卡突出服务状态，用真实在线节点比例构建进度环；没有添加虚构流量曲线。
- [新设计系统](https://developer.apple.com/videos/play/wwdc2025/356/)：根据功能组织操作，统一圆角与留白。先读状态和预算，再进行服务维护；四个主导航始终保持相同位置。
- [Motion](https://developer.apple.com/design/human-interface-guidelines/motion)：导航指示在 320 毫秒内移动，连续点击可立即改变目标；开启减少动画时直接切换，业务操作不等待动画完成。
- [Typography](https://developer.apple.com/design/human-interface-guidelines/typography) 与 [Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility)：使用平台字体、明确的文字层级，允许系统字号缩放；状态同时用文字和颜色表达。两倍字号时主卡优先留出文字空间，节点数量仍可在统计卡读取。

## 使用

首页查看服务状态、在线节点与流量预算，下拉可刷新。用户页管理账号，节点页点击卡片查看详情，设置页选择深浅外观与主题色。重启、停止和删除等操作继续保留原有确认流程。

80% 和 95% 的预算颜色仅为数据提示；节点是否停用仍由服务端策略决定。面板自身节点与没有配置预算的对接节点均保持原有规则。

## 验证范围

组件回归覆盖窄屏、两倍字号、深浅主题、高对比度、导航切换、刷新竞态与表单取消。使用脱敏测试数据进行截图和真机界面验收；这类截图只证明界面渲染和交互，不代表生产账号或网络链路实测。

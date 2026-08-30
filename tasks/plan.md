# Implementation Plan: v0.33.0 分机器自定义计费周期（历史记录）

> 本文件保存早期实施过程，不代表当前路线图。当前行为和维护入口见 [`docs/README.md`](../docs/README.md)。

## Architecture Decisions

- 复用 `origin_traffic_daily` 作为只增供应商账本；手工已用量用基线差值追加，避免重复统计。
- 继续使用现有预算 POST 路径，仅增加字段；旧数据库默认每月 1 日重置，保持兼容。
- 未归属清理使用固定来源专用方法和固定路由，不接受任意来源 ID。

## Task List

### Phase 1: 数据与算法

- [x] 添加旧库兼容迁移和周期边界计算测试。
- [x] 添加历史已用基线、再次编辑、跨周期及月末测试。
- [x] 实现预算模型和有界查询。

### Checkpoint: Foundation

- [x] `tests.test_node_operations.NodeBudgetTests` 全绿。

### Phase 2: 管理闭环

- [x] 添加预算表单验证、CSRF、审计和界面测试。
- [x] 添加未归属历史精确清理与幂等测试。
- [x] 实现受保护接口和易懂 UI。

### Checkpoint: End to End

- [x] HTTP 测试与真实浏览器桌面/移动验收通过。

### Phase 3: 交付

- [x] 更新 API、部署、README、变更日志和版本固定值。
- [x] 全量质量门和对抗审查无 P0–P2。
- [ ] 受保护 PR、不可变标签、Sigstore Release、六平台安装矩阵全绿。
- [ ] 生产滚动升级、定向清理和身份/真实数据面不变验收通过。

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| 保存基线后把旧流量重复追加 | 同事务保存全量账本水位，显示只取水位后的差值 |
| 31 日在短月漂移 | 每月独立按原始 `reset_day` 夹到月末，不把 28 日写回 |
| 删除误伤已归属统计 | 路由无动态来源参数，数据库方法固定只操作 `legacy-unattributed` |
| 恢复旧备份缺少新列 | 初始化加列迁移，兼容默认值保持自然月旧语义 |

## Open Questions

- 无；当前需求可在既有安全边界内完整实现。

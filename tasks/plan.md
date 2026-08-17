# 实施计划：v0.20.0 签名更新、模块化与健康探针

## Architecture Decisions

- 使用 GitHub Actions OIDC 临时身份与 Sigstore/Cosign keyless signing；不创建、不保存长期私钥。
- 先拆低耦合、可独立验证的现有边界，不搬动数据库和恢复事务核心。
- `/readyz` 只读取本地缓存状态与轻量数据库探针；公网探针不触发 systemctl 或 Hysteria 网络请求。
- `/metrics` 仅允许 loopback，避免为面板公网端口新增可枚举的运行细节。

## Task List

### Phase 1: 签名信任链

- [x] 新增签名失败/成功测试和正式签名合同。
- [x] 实现固定工作流身份、Sigstore bundle 下载及执行前验证。
- [x] 增加 Release OIDC 签名工作流、发布文档和 CI 校验。

### Checkpoint: Supply chain

- [x] Release 工作流定义真实 Cosign 正向验签与单字节篡改反例；将在首次发布时由 GitHub OIDC 环境执行。
- [x] 定向更新器与安装器合同测试通过。

### Phase 2: 模块边界

- [x] 抽取包内版本、Web 静态资源、运维控制和更新器。
- [x] 保持顶层兼容导入，更新安装器固定来源与 SHA-256。
- [x] 更新 CI 编译、lint、安全扫描范围。

### Checkpoint: Modularization

- [x] 模块可在 Python 3.8 语法下导入。
- [x] 既有定向测试无行为变化。

### Phase 3: 健康与指标

- [x] 增加运行状态聚合器和流量同步观测。
- [x] 增加 `/readyz` 与 loopback-only `/metrics`。
- [x] 将监督线程状态接入健康聚合器。

### Checkpoint: Complete

- [x] 全量测试、编译、Ruff、Bandit、Bash、ShellCheck 和 diff 检查通过。
- [x] 完成安全/架构对抗复审并记录首次签名升级边界。

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Sigstore 或 GitHub OIDC 不可用 | 暂时无法产出可在线更新的 Release | 更新器安全拒绝；恢复后重跑签名工作流 |
| 首次升级仍由旧版无签名更新器发起 | 信任链未真正建立 | 首次在服务器 `/tmp` 临时下载 Cosign、bundle 与安装器完成验签后升级；不在本地保存文件 |
| 拆模块破坏导入或安装 | 服务启动失败 | 顶层 re-export、安装器哈希合同、py_compile 与全量回归 |
| 探针被滥用造成 subprocess/网络放大 | DoS | `/readyz` 不调用外部命令；`/metrics` 仅 loopback |

## Open Questions

- 无；发布、推送和生产部署不属于本轮默认授权。首次从无签名旧版升级需在服务器临时验签，但不在本地保存任何签名文件。

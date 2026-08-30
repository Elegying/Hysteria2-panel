# Hysteria2-panel 文档中心

这里集中列出项目的操作手册、接口契约、架构决策和历史证据。第一次使用请按“用户文档”阅读；开发和审计材料不应替代当前操作手册。

## 用户文档

| 文档 | 适合什么时候看 |
|---|---|
| [安装与升级](INSTALLATION.md) | 准备服务器、配置 DNS/端口、安装、重复运行或在线升级 |
| [使用指南](USER_GUIDE.md) | 管理用户、流量、节点、UDP `443` 与出站策略 |
| [备份与迁移](BACKUP_AND_MIGRATION.md) | 下载备份、恢复、迁移面板或配置 WebDAV |
| [运维手册](OPERATIONS.md) | 日常巡检、读取指标、定位故障与安全回滚 |
| [术语表](TERMINOLOGY.md) | 快速理解控制面、数据面、spool、摘流等术语 |

## 开发与维护

| 文档 | 内容 |
|---|---|
| [架构说明](ARCHITECTURE.md) | 组件、认证流、流量账本、节点身份和故障边界 |
| [HTTP 接口契约](API.md) | Hysteria 回调、签名节点协议与管理路由 |
| [发布与回滚](DEPLOYMENT.md) | 正式 Release、发布门禁、多节点滚动升级和中断恢复 |
| [稳定化与发布质量](STABILIZATION.md) | 允许的变更范围、必过检查和发布判定 |
| [贡献指南](../CONTRIBUTING.md) | 开发流程、验证要求和提交说明 |
| [安全政策](../SECURITY.md) | 私密报告漏洞和支持版本 |
| [变更日志](../CHANGELOG.md) | 每个正式版本的用户可见变化 |

## 架构决策记录（ADR）

ADR 记录“为什么这样设计”，不是操作教程。编号重复的两份 ADR-014 分别讨论控制周期截止时间和运行时出站切换；文件名是稳定引用。

- [ADR-001：本机 HTTP 认证回调与标准库面板](decisions/ADR-001-local-auth-panel.md)
- [ADR-002：可选 HTTP 面板与 UDP 优化](decisions/ADR-002-panel-http-and-udp-tuning.md)
- [ADR-003：持久流量、连接限额与受限服务控制](decisions/ADR-003-usage-policy-and-service-control.md)
- [ADR-004：可迁移用户身份与原子恢复](decisions/ADR-004-portable-backup-restore.md)
- [ADR-005：登录保护与双层 BBR 优化](decisions/ADR-005-http-login-network-hardening.md)
- [ADR-006：网页出站策略与防滥用边界](decisions/ADR-006-web-egress-abuse-control.md)
- [ADR-007：固定来源在线更新](decisions/ADR-007-fixed-source-online-update.md)
- [ADR-008：工作线程监督与升级回滚](decisions/ADR-008-runtime-supervision-upgrade-rollback.md)
- [ADR-009：可观测更新与受限运维](decisions/ADR-009-observable-update-and-admin-operations.md)
- [ADR-010：WEB 策略下允许公网 SSH](decisions/ADR-010-public-ssh-egress.md)
- [ADR-011：单账号 UDP `443` 双入口授权](decisions/ADR-011-per-user-udp-443-entrypoint.md)
- [ADR-012：受管防火墙端口开放](decisions/ADR-012-managed-firewall-port-opening.md)
- [ADR-013：无密钥签名、模块边界与就绪检查](decisions/ADR-013-keyless-update-modules-readiness.md)
- [ADR-014：有界控制周期](decisions/ADR-014-bounded-control-cycle.md)
- [ADR-014：运行时出站策略切换](decisions/ADR-014-runtime-egress-policy-switch.md)
- [ADR-015：可跨重启恢复的升级事务](decisions/ADR-015-crash-consistent-installer-upgrades.md)
- [ADR-016：默认 HTTPS 与更新目标固定](decisions/ADR-016-https-default-and-update-target-pinning.md)
- [ADR-017：简化节点对接](decisions/ADR-017-streamlined-node-onboarding.md)
- [ADR-018：分机器流量归属](decisions/ADR-018-per-machine-usage-attribution.md)
- [ADR-019：节点生命周期与异地备份](decisions/ADR-019-node-operations-and-offsite-backup.md)

## 设计规格

规格记录功能设计时的约束和验收条件。它们按当时版本冻结，当前行为应以代码、测试、用户文档和接口契约为准。

- [v0.10.0 安全加固](specs/2026-08-11-v0.10.0-hardening.md)
- [v0.11.0 出站策略](specs/2026-08-11-v0.11.0-egress-policy.md)
- [v0.13.0 生产审查](specs/2026-08-12-v0.13.0-production-audit.md)
- [v0.14.0 运维能力](specs/2026-08-12-v0.14.0-operations.md)
- [v0.19.0 用户二维码](specs/2026-08-16-v0.19.0-user-qr-code.md)
- [v0.20.0 签名更新、模块化与健康检查](specs/2026-08-17-v0.20.0-signed-update-modular-health.md)
- [面板 ACME HTTPS](specs/2026-08-27-panel-acme-https.md)
- [节点对接第一阶段](specs/2026-08-28-node-onboarding-phase-1.md)
- [节点控制第二阶段](specs/2026-08-28-node-control-phase-2.md)
- [分布式控制第三阶段](specs/2026-08-28-distributed-control-phase-3.md)
- [数据面第四阶段](specs/2026-08-28-data-plane-phase-4.md)
- [DNS 准入第五阶段](specs/2026-08-28-dns-admission-phase-5.md)
- [v0.32.0 节点运营](specs/2026-08-29-v0.32.0-node-operations.md)
- [v0.33.0 自定义预算周期](specs/2026-08-29-v0.33.0-custom-budget-cycles.md)

## 审查与视觉证据

这些文件是某个时间点的审计记录，不代表最新版本的长期承诺。

- [v0.11.0 多维审查](reviews/2026-08-11-v0.11.0-multidirectional-review.md)
- [v0.13.0 生产审计](reviews/2026-08-12-v0.13.0-production-audit.md)
- [v0.14.1 生产验证](reviews/2026-08-12-v0.14.1-production-validation.md)
- [v0.21.1 最终生产审计](reviews/2026-08-22-v0.21.1-final-production-audit.md)
- [v0.35.0 稳定化审计](reviews/2026-08-30-v0.35.0-stabilization-audit.md)
- [全站界面专业化审查](UI_AUDIT_2026-08-30.md)
- [界面设计验收记录](../design-qa.md)
- [当前界面截图](screenshots/)

## 历史任务记录

根目录 `tasks/` 保存早期实施计划与完成清单，便于追溯，不应作为当前待办或用户文档：

- [早期总体计划](../tasks/plan.md)
- [早期总体清单](../tasks/todo.md)
- [二维码功能计划](../tasks/user-qr-code-plan.md)
- [二维码功能清单](../tasks/user-qr-code-todo.md)

## 文档维护约定

- 用户行为变化：更新对应用户文档和 `CHANGELOG.md`；
- HTTP 或签名协议变化：更新 `API.md` 并增加兼容性测试；
- 重要架构取舍：新增 ADR，不重写旧决策的历史背景；
- 正式发布流程变化：更新 `DEPLOYMENT.md` 和相关工作流测试；
- 历史审计中的结论不要静默改成“当前状态”，应新增带日期的审计记录。

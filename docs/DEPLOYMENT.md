# 多节点发布与回滚

正式发布只从 GitHub Release 获取 `install.sh` 与 `install.sh.sigstore.json`，并按 README 的固定 Cosign SHA-256、OIDC issuer 和精确 workflow/tag identity 完成验签。不要从 `main` 直接以 root 执行脚本。

## 发布批次

多节点采用 `max-unavailable=1`：任何时刻只升级一台，当前节点全部验收通过后才进入下一台。建议先选低流量节点作为 canary，并保留至少一台未升级节点用于对照和回退。

每台节点升级前记录：

- 当前版本、节点域名、主 UDP 端口、面板端口、证书指纹和 `EGRESS_POLICY`；
- `systemctl is-active` 对面板、主 Hysteria、TCP 探测及启用时的 UDP/TCP `443` 服务结果；
- `/healthz`、`/readyz`、主/`443` 监听和最近一次自动备份目录；
- 备份分区可用空间，以及没有 `.upgrade-active`、恢复事务或出站切换事务。

升级后必须再次核对上述状态，并用既有分享链接完成 Hysteria 握手与网页数据面测试。发现任一身份、端口、流量结算、服务、监听或数据面异常时，立即停止后续批次；保留现场和 `/var/backups/hysteria2-panel/<时间戳>/`，不要同时升级其他节点。

## 中断恢复

安装器只在备份清单和 `.upgrade-active` 已持久化后覆盖程序。进程被强制终止或主机重启时，`hysteria2-panel-upgrade-recover.service` 会在面板前恢复文件并排队启动旧服务，随后独立健康复核任务验证旧入口并删除标记。标记仍存在即表示恢复没有完成，不得继续升级；先检查 recovery/verify unit 日志与备份清单。

普通失败会在当前安装器进程内回滚。自动恢复仍失败时保持节点隔离，按 README 的整体回滚说明处理，不要只替换数据库或单个 unit。

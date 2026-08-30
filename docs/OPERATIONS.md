# 运维手册

本页用于日常巡检、故障定位和安全回滚。多节点正式发布请同时遵循[发布与回滚](DEPLOYMENT.md)。

## 快速巡检

先看服务状态：

```bash
systemctl status \
  hysteria2-panel \
  hysteria2-panel-server \
  hysteria2-panel-server-443 \
  hysteria2-panel-tcp-probe \
  hysteria2-panel-tcp-probe-443
```

再看面板健康。根据实际面板协议选择其中一组：

```bash
curl http://127.0.0.1:19998/healthz
curl http://127.0.0.1:19998/readyz
curl http://127.0.0.1:19998/metrics
```

```bash
curl --insecure https://127.0.0.1:19998/healthz
curl --insecure https://127.0.0.1:19998/readyz
curl --insecure https://127.0.0.1:19998/metrics
```

`/healthz` 只表示 HTTP 进程存活；`/readyz` 还会检查数据库、内部认证、流量采集线程和最近一次统计同步。生产可用性应以 `/readyz`、真实端口和客户端握手共同判断。

## 常用服务

| systemd 单元 | 作用 |
|---|---|
| `hysteria2-panel.service` | 管理面板、认证回调、统计与后台任务 |
| `hysteria2-panel-server.service` | Hysteria 主 UDP 入口 |
| `hysteria2-panel-server-443.service` | 账号专属 UDP `443` 入口 |
| `hysteria2-panel-tcp-probe.service` | 主端口 TCP 兼容探测 |
| `hysteria2-panel-tcp-probe-443.service` | TCP `443` 兼容探测 |
| `hysteria2-panel-update.service` | 固定来源的在线更新任务 |
| `hysteria2-panel-restore.service` | 一次性恢复任务 |
| `hysteria2-panel-cert-renew.timer` | 面板 Let’s Encrypt 证书检查 |
| `hysteria2-panel-offsite-backup.timer` | 每日异地备份调度 |

查看当天关键日志：

```bash
journalctl \
  -u hysteria2-panel \
  -u hysteria2-panel-server \
  -u hysteria2-panel-server-443 \
  -u hysteria2-panel-update \
  -u hysteria2-panel-restore \
  --since today
```

## 数据节点指标

在数据节点本机读取：

```bash
curl http://127.0.0.1:19996/healthz
curl http://127.0.0.1:19996/metrics
```

指标不包含节点名、用户名、token 或来源 IP。建议至少告警：

- `hy2panel_node_control_ready == 0` 持续 2 分钟；
- `hy2panel_node_control_consecutive_failures >= 3`；
- 最近成功控制周期超过 90 秒；
- spool 文件数或字节数持续增长 10 分钟。

认证代理和控制循环分别受 systemd watchdog 监督。进程卡住时 systemd 会终止并自动重启，而不是只依赖进程是否存在。

## 理解重启后的短暂拒绝

面板启动后会清除上一个进程纪元的短期认证决定、设备预留和节点快照。所有协议就绪节点重新提交在线快照和流量 ACK 前，新认证可能短暂拒绝。

这是一项防止设备数或流量超额的安全关闭策略，不代表数据节点上的已有 Hysteria 会话被主动切断。如果某个已标记为协议就绪的节点长期离线，新认证会持续拒绝，直到该节点恢复或管理员撤销其协议参与状态。

## 关键路径

| 路径 | 内容 |
|---|---|
| `/opt/hysteria2-panel/` | 面板程序与项目专用 Hysteria 二进制 |
| `/etc/hysteria2-panel/` | Hysteria 配置、TLS 身份与运行环境 |
| `/etc/hysteria2-panel/acme/` | 面板 ACME 账户、续期配置与证书 lineage |
| `/etc/hysteria2-panel/offsite-backup.json` | 可选 WebDAV 凭据，仅允许 `root:root 0600` |
| `/var/lib/hysteria2-panel/panel.db` | 用户、流量、会话和审计数据 |
| `/var/lib/hysteria2-panel/offsite-backup-status.json` | 面板可读的脱敏异地备份状态 |
| `/var/backups/hysteria2-panel/` | 覆盖部署和恢复前的自动备份 |
| `/etc/sysctl.d/99-hysteria2-panel.conf` | 面板本机节点网络参数 |
| `/etc/sysctl.d/99-hysteria2-panel-node.conf` | 数据节点受管网络参数 |
| `/etc/sudoers.d/hysteria2-panel` | 固定服务控制、重启、恢复和更新白名单 |

不要把单个文件当成完整身份。可恢复的 Hysteria 身份至少包含数据库、HMAC 环境、证书和私钥；SQLite 还可能存在 WAL/SHM 与持久事务标记。

## 常见故障定位

### 面板存活，但未就绪

1. 请求 `/readyz`；
2. 查看 `hysteria2-panel` 日志；
3. 检查数据库权限和完整性；
4. 检查认证、统计端点与后台线程；
5. 确认没有未完成的升级或恢复事务。

### TCP 探测正常，但客户端连不上

TCP 探测只接受连接后立即关闭，不验证 UDP/QUIC。继续检查：

- 云安全组是否放行 UDP；
- Hysteria UDP 监听是否存在；
- 域名是否解析到正确节点；
- 用户是否启用、是否超出流量或客户端实例数；
- UDP `443` 是否为该账号授权；
- 客户端证书指纹是否仍与节点一致。

### 流量暂时不增长

先区分“没有新流量”和“节点 ACK 不新鲜”。检查主入口与 `443` 的统计端点、中央控制周期和节点 spool。不要删除 spool；它用于在中央暂时不可达时持久保存未确认流量，并在恢复后幂等重放。

### 更新或恢复中断

安装、在线更新、恢复和证书续期共用维护锁。看到事务标记时，不要重复运行任务或手工删除标记。开机前置/后置恢复单元会继续完成或回滚；先保留日志、备份目录和标记，再判断下一步。

## 回滚原则

升级前备份包含应用、配置、数据库快照、项目 systemd 单元、启用状态、sudoers、sysctl 和 tmpfiles。普通失败会由安装器自动恢复并复核旧入口。

如果自动回滚仍失败：

1. 停止继续升级其他节点；
2. 保留当前文件、事务标记和最近的备份目录；
3. 导出相关 systemd 状态与 journal；
4. 在维护窗口中按完整备份恢复，不要只复制 `panel.db`；
5. 恢复后执行 `daemon-reload`；
6. 重新验证面板、认证、统计、主端口、UDP `443`、TCP 探测和旧 URI 握手。

无法确认服务全部停止、数据库完整且身份文件一致时，不要覆盖生产文件。

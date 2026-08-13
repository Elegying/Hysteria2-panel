# ADR-003：持久流量、连接限额与受限服务控制

## 状态

已接受，2026-08-10。

## 背景

面板需要执行用户总流量配额、默认三设备限制、历史流量重置、连接 URI 重复分享和 Hysteria 服务启停。Hysteria 官方统计保存在进程内存中，`/online` 返回每个认证 ID 的 Hysteria 客户端实例数；旧版数据库只保留不可逆的认证密钥 HMAC 指纹。面板进程以非 root 用户运行，不能直接管理 systemd 服务。

## 决策

- 定期调用官方 `/traffic?clear=1` 原子取得用户流量增量，并分别累计到 SQLite 的 `tx_bytes` 与 `rx_bytes`。
- 已从 Hysteria 清零、但尚未成功写入 SQLite 的增量使用 `0600` 本地待处理日志和批次 ID 持久化；数据库提交与日志删除之间重启时，批次 ID 防止重复累计。
- 升级最终切换先停止认证入口，在有界窗口内持续为 `/online` 身份调用 `/kick`，再清账并停止旧 Hysteria；`/kick` 只在该身份下一次产生流量时生效，所以完全空闲的会话无需等待 `/online` 归零。清账临界区延迟 HUP、INT、TERM，正常服务停止不会打断已清零增量的持久化。SIGKILL、内核崩溃或掉电仍无法由不提供事务 ID 的远端统计 API 达成严格 exactly-once，因此不作绝对保证。
- 在 HTTP 认证回调中同步最新流量，检查总流量与并发连接上限；达到上限时返回官方约定的 `{"ok": false, "id": ""}`。
- 把 `/online` 数量定义为“客户端实例/近似设备数”，不声称能识别物理硬件或 NAT 后设备。
- 新建或轮换密钥时保存随机种子，实际 token 由服务器 HMAC key 派生；数据库不保存 token 明文。旧用户不自动轮换，避免升级使现有客户端失效。
- 面板服务只通过 `/etc/sudoers.d/hysteria2-panel` 获得固定 argv 的项目命令，不允许通用 shell 或任意 `systemctl`：启动、停止、重启主 Hysteria 服务，以及异步启动固定恢复任务、固定更新任务和整机重启。恢复与更新命令的后续安全模型分别由 ADR-004、ADR-007 和 ADR-009 扩展。
- 检查更新仍只读取固定的 GitHub Release API，设置 3 秒超时和 16 KiB 响应上限；ADR-007 与 ADR-009 已在此只读检查之上增加固定正式标签、固定安装器和 root oneshot 的受限在线安装流程。

## 备选方案

### 直接使用 Hysteria 内存累计值

重启会丢失配额状态，无法满足总流量限制和可靠重置，因此拒绝。

### 通过来源 IP 识别物理设备

多个设备可能共享 NAT，同一设备也可能切换网络，不能形成可靠硬件身份，因此拒绝。采用官方并发连接数并在界面明确说明。

### 在数据库保存明文 token

能简单实现分享，但数据库泄露会直接暴露全部代理凭据，因此拒绝。采用随机种子加服务器密钥派生。

### 给面板通用 root 或任意 systemctl 权限

会把 Web 面板漏洞扩大为主机控制权限，因此拒绝。只允许 sudoers 中列出的项目专用固定 argv；恢复、更新与重启入口仍不能携带浏览器提供的命令或路径。

## 后果

- 正常重启后流量与配额继续有效；受控升级会先清退在线连接并完成最终结算。远端清零与本地日志 fsync 之间遭遇 SIGKILL、内核崩溃或掉电时仍存在极窄的少计窗口。
- 达到流量上限会踢下现有连接并拒绝新认证；认证和在线统计短暂竞态通过待连接保留窗口收紧。
- 旧用户保持原链接可用，但必须由管理员明确轮换一次才能使用重复分享。
- 面板 systemd 单元不能设置会隐式启用 nosuid/`NoNewPrivileges` 的选项，包括 `NoNewPrivileges`、`PrivateDevices`、`ProtectKernelTunables`、`ProtectKernelModules`、`RestrictSUIDSGID`、`LockPersonality` 和 `RestrictAddressFamilies`，否则 sudo 的 setuid 提权会被禁止。Hysteria 服务保留全部保护；面板继续保留只读系统、私有临时目录、主目录与控制组保护、资源上限以及精确 sudoers 白名单。

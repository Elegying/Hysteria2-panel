# 主机日志与备份维护

本文是 root 管理员按需执行的主机维护方案，不会由网页自动开放任意防火墙或文件删除权限。先确认当前 SSH 端口、管理来源、恢复点和现有日志规则，再应用；不要覆盖其他管理员自定义的 jail 或日志接收规则。

## SSH 登录防护

Ubuntu/Debian 可安装 `fail2ban` 与 `python3-systemd`，使用 systemd 日志后端。下面 jail 只封禁 SSH 的 TCP 端口，不对整台主机执行 allports 封禁；如果 SSH 不在 22，请替换为实际监听端口。

```ini
# /etc/fail2ban/jail.d/90-hy2-sshd.local
[sshd]
enabled = true
backend = systemd
mode = normal
port = 22
protocol = tcp
banaction = nftables[type=multiport]
maxretry = 6
findtime = 10m
bantime = 1h
usedns = no
ignoreip = 127.0.0.1/8 ::1
```

在 `ignoreip` 加入已核实的管理来源地址，然后运行 `fail2ban-client -t`，通过后启用服务。保留现有 SSH 会话，另开会话确认还能登录。确认只启用预期的 `sshd` jail，并检查实际 nftables 规则只匹配 TCP SSH 端口；不要仅凭服务 active 判定规则正确。对接节点通过 HTTPS 与面板通讯，用户使用 Hysteria UDP 入口，不应匹配此规则。

不启用全端口 recidive，也不因日志报错放宽面板认证、TLS 或来源验证。

## 日志容量与重复写入

对于小磁盘主机，可通过 drop-in 给系统 journal 设定以下预算：

```ini
# /etc/systemd/journald.conf.d/90-hy2-retention.conf
[Journal]
SystemMaxUse=256M
SystemKeepFree=1G
SystemMaxFileSize=32M
RuntimeMaxUse=64M
MaxRetentionSec=7day
MaxFileSec=1day
Compress=yes
```

大小与时间条件先到者触发回收，并不保证必然保存满 7 天；空间预留也不限制其他程序写磁盘。变更后重启 journald，使用 `journalctl --rotate` 与 `journalctl --vacuum-size=256M --vacuum-time=7d` 回收归档。不得删除正在写入的 journal 文件。

若 Hysteria 的同一条事件既写 journal 又转发到本机 syslog，并且没有依赖 syslog 的远程采集，可在 rsyslog 默认规则之前添加：

```text
# /etc/rsyslog.d/10-hy2-no-duplicate.conf
if $programname == "hysteria" then stop
```

先核对实际 programname，运行 `rsyslogd -N1` 验证后重启 rsyslog。此过滤不删除 journal 中的错误，也不改变 Hysteria 日志级别；SSH 等其他系统事件照常保留。

保留发行版 rsyslog 的路径列表、权限及 postrotate，调整为 `daily`、`rotate 7`、`maxsize 16M`、`maxage 7`、`compress`、`nodelaycompress`。对 btmp 使用 `weekly`、`rotate 2`、`maxsize 4M`、`maxage 14` 和压缩。独立执行 drop-in 时应显式设置与主配置一致的 `su root adm`，保留 btmp 的 `create 0660 root utmp`。

用 `logrotate --debug /etc/logrotate.conf` 检查所有规则，没有重复路径后，让现有 logrotate.timer 每小时检查一次：

```ini
# /etc/systemd/system/logrotate.timer.d/90-hourly.conf
[Timer]
OnCalendar=
OnCalendar=hourly
AccuracySec=1min
Persistent=true
```

执行 daemon-reload 并重启 timer。轮转与系统任务使用同一状态锁；维护时使用 `--wait-for-state-lock` 或等已有任务完成，不要删除锁文件。`maxsize` 在轮转任务执行时检查，不是每字节写入的硬配额；突发写入仍可能暂时超出目标。不要直接截断活动日志。

## 本地备份保留

从 v0.39.28 起，安装器成功提交升级后，只清理 `/var/backups/hysteria2-panel` 中精确匹配自动命名、root 所有且权限为 0700 的普通目录。策略为最多 3 份、30 天、1 GiB 空间预算，同时始终保护最新两个恢复点和本次升级备份。保护副本超预算时告警，要求管理员迁移副本，不自动牺牲回滚能力。

该策略不匹配手工备份、恢复事务和管理员自定义目录。一次性程序更新留下的独立快照需按其来源另行清点；清理前验证新恢复点的数据库完整性、归档可读性及摘要，并保留至少两个可用恢复点。不要仅按目录名字中的版本判断其中程序版本——升级前快照保存的是升级前的程序。

对于历史大数据库，可通过 SQLite backup API 制作一致性副本，再只对副本执行 VACUUM，校验用户数、完整性及外键，并在校验通过后生成文件摘要。不要对正在服务的数据库随意执行独占压缩，也不要压缩已经受 manifest 保护的旧数据库后保留错误摘要。

本地日志/备份治理不要求配置异地存储；未配置 WebDAV 时保持 `not_configured`。

## 验收

维护前后比较用户身份与额度、Hysteria 进程 PID、健康接口、节点心跳和流量 ACK。检查 Fail2ban 的实际端口范围、新 SSH 登录、journal 新记录、rsyslog 与 logrotate 配置、磁盘余量及保留的恢复点。清理目录不得与尚未完成的升级、恢复或出站切换事务冲突。

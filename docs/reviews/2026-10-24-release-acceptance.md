# 2026-10-24 发布前验收与短时异常复审

本轮延续 [恢复与容量复审](2026-10-24-recovery-capacity.md)，按用户要求跳过长时间稳定性测试，执行当前工作树的安装、升级、回滚、接口故障与发布契约检查。基线仍为 v0.39.41 / `a66e2b28cb09e0ee7b62c5cb343c185dbf6f4ff7`，改动尚未发布。

## 确认问题及修复

实际部署中持有 SQLite `BEGIN IMMEDIATE` 写锁时，`authorize_local_participant()` 的租约事务约 5 秒后抛出 `sqlite3.OperationalError`。内部认证处理器没有捕获该异常，导致客户端收到连接断开，不能区分临时存储故障与网络异常。没有观察到绕过鉴权或错误放行。

现对认证数据库读取、租约提交抛出的 SQLite/存储错误返回 HTTP 503 与 `{"ok": false, "id": ""}`，日志记录异常但响应不暴露内部细节。正常凭据/配额拒绝仍保持 HTTP 200。回归覆盖主入口和 UDP 443、凭据读取与准入提交两个故障位置，以及故障解除后的正常响应；实际安装环境重现写锁后复测。

测试基础设施同时修正：容器屏蔽 `systemd-binfmt.service`，避免特权容器改写宿主模拟器注册；候选矩阵校验实际镜像架构、等待 systemd 初始化、允许容器中与项目无关的 degraded 状态，项目服务仍逐项验收。

## 验收方法与源码身份

当前工作树不能通过远端提交 URL 下载。测试使用固定归档，`release_lab_curl.sh` 仅把 `lab-candidate` 下的项目 Python 源码映射到归档；安装器源码、版本、SHA-256 检查、Hysteria/Cosign 下载与校验均保留。它不是正式 Release 分发或 Sigstore 签名验收，生产安装器未加入本地绕过开关。

amd64 在 WSL Ubuntu 24.04 的独立 Docker 容器中执行。ARM 最终验收使用配对 Mac 的独立 Colima ARM Linux 虚拟机，实际镜像架构必须为 arm64；QEMU 尝试因 systemd/netfilter 环境限制失败，不记作通过。专用 ARM VM 的普通容器网络缺少宿主 UDP 缓冲 sysctl，因此改用该实验 VM 的 host 网络并串行执行；先停止实验 bridge 容器并备份、清理该新建 VM 的 Docker 网络规则，未修改开发主机或生产节点防火墙。所有这些设置仅服务于一次性实验。

## 结果

### 六平台实际安装

| 系统 | 原生 amd64 | 原生 arm64（Mac 专用 Linux VM） |
| --- | --- | --- |
| Ubuntu 24.04 | 通过，257.685 秒 | 通过，240.821 秒 |
| Debian stable（固定镜像摘要） | 通过，337.558 秒 | 通过，252.989 秒 |
| Rocky Linux 9 | 通过，243.052 秒 | 通过，240.787 秒 |

每个平台均执行完整安装器 E2E，包括新装、服务恢复、升级失败回滚、备份恢复及认证检查。实际架构及固定基础镜像见 [amd64 结果](evidence/2026-10-24-release/amd64-matrix.json) 和 [arm64 结果](evidence/2026-10-24-release/arm64-matrix.json)。

依赖安装在 Debian 11/12/13、Ubuntu 20.04/22.04/24.04、Rocky 8/9 共八个环境通过，包括包管理锁和第三方 APT 源失效隔离。Debian 11 初次桥接网络下载超时，原样测试切换至隔离 WSL Docker host 网络后通过，未关闭软件源签名校验。见 [依赖结果](evidence/2026-10-24-release/dependencies.json)。

### 自动化与发布合同

| 检查 | 结果 |
| --- | --- |
| Python 3.8.20 | 1053 项，1040 通过、13 跳过，369.338 秒 |
| Python 3.12.3 | 1053 项，1040 通过、13 跳过，359.595 秒 |
| Python 3.13.17 | 1053 项，1040 通过、13 跳过，358.706 秒 |
| Python 3.13 SQLite ResourceWarning 硬检查 | 通过 |
| Flutter 3.47.2 | analyze 通过，146 项测试通过 |
| 真实 Chrome | 1380×900 / 375×812 页面渲染通过，36 组交互通过 |
| Ruff / Bandit / ShellCheck / Bash 语法 | 通过 |
| systemd 服务语义 | 通过，包括恢复前置失败阻断、恢复收尾及出站切换 |
| UFW / firewalld | 按 CI 独立网络 namespace 执行，通过 |
| 旧部署迁移与失败回滚 | 通过，用户身份和累计用量一致 |

Python 测试在 root 隔离运行上下文执行，环境跳过数比前次普通用户运行多 1；没有把跳过项计作通过。初轮三个 Git 清单测试遇到 WSL 文件属主保护，改为仅对子进程显式信任当前仓库路径后，三版本全量重跑通过，未修改全局 Git 信任配置。防火墙实验补装 polkit 后重新加载了实验容器的 D-Bus 配置，再按 CI network namespace 合同通过；未放宽安装器规则识别。

当前 GitHub 规则集只读核验：[Protect main](https://github.com/Elegying/Hysteria2-panel/rules/20781229)、[Protect release tags](https://github.com/Elegying/Hysteria2-panel/rules/20781230)、[Require PR for main](https://github.com/Elegying/Hysteria2-panel/rules/24794409) 均为 active。主分支要求 11 项命名状态检查，包括三版本 Python、浏览器、移动端、静态分析、防火墙、systemd、RHEL 包合同、完整安装及 CodeQL。这只证明门禁配置仍存在，不代表候选提交已经通过远端 CI。脱敏证据见 [rulesets.json](evidence/2026-10-24-release/rulesets.json)。

### 短时故障

| 故障 | 实测与恢复结果 |
| --- | --- |
| 4 MiB tmpfs 实际写满 | 明确触发 ENOSPC；源计数未清零，释放空间后累计从 330 精确恢复到 407 字节，重复采集不重记 |
| SQLite 实际竞争写锁 | 等待约 5 秒后失败；解除后累计从 407 精确恢复到 473 字节 |
| 真实 HTTP 统计端点 503 | 故障期间不误入账，恢复后累计精确为 561 字节 |
| 已安装统计端口丢包 | 13.586 秒后 readiness 为失败；拒绝新认证；恢复网络后 6.119 秒就绪 |
| 已安装认证租约写锁 | 5.008 秒后明确 HTTP 503；解除写锁后认证成功 |
| 故障后实际 QUIC | 主端口和 UDP 443 各校验 720,896 字节，内容一致 |
| 中央停机与节点补传 | 50 个持久批次重复提交 100 次，精确入账 170,000 字节，队列清空，无重复或漏记 |

前三项使用真实 tmpfs、SQLite 与回环 HTTP，服务代际 ID 为夹具；后四项连接实际安装的服务。不得把前者描述为整块生产磁盘或真实 Hysteria 进程断电。

原始结果：[存储故障](evidence/2026-10-24-release/storage-faults.json)、[实际服务故障](evidence/2026-10-24-release/service-faults.json)、[签名节点补传](evidence/2026-10-24-release/node-faults.json)、[候选源码身份](evidence/2026-10-24-release/candidate.json)。

## 范围与后续门禁

综合工程评分由 **89/100 提升至 91/100**，不是测试通过率或可用性承诺。沿用上轮五个维度：正确性与计量 19/20、安全与权限 18/20、恢复与运维 19/20、性能与容量证据 17/20、工程与可维护性 18/20。新增得分来自实际存储/网络故障下的明确拒绝与恢复，以及原生双架构六平台发布前验收；长期、多机和生产容量证据仍未补齐，性能分不变。

下一步先将候选改动提交 PR，运行绑定该提交的远端 CI/CodeQL；通过后按发布流程验证版本、签名和下载资产，再安排已授权的小范围发布。长期稳定性测试按本次要求跳过，不作为已完成项目。

实验容器已清理，Mac 专用 `hy2-release` VM 已停止，Docker context 恢复为 `default`。保留实验 VM、镜像缓存及临时原始日志供复查；仓库只保存脱敏摘要，不纳入带测试凭据的完整日志、归档或数据库。

本轮不包含长期稳定性、生产 canary、真实跨机公网故障或整机断电。节点补传测试使用合成身份、真实签名 HTTPS 与落盘 spool，不等同于完整远端节点部署。

这些结果属于发布前候选验收。正式发布仍需要候选提交进入受保护分支、版本与新标签绑定的远端 CI/CodeQL、发布 workflow 的 OIDC 签名及草稿资产重新下载验签。本轮不创建标签、不发布 Release，也不能复用旧提交的远端绿灯替代候选门禁。

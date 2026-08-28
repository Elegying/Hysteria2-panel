# Hysteria2-panel

一个轻量、无第三方 Python 依赖的 Hysteria 2 多用户管理面板。部署脚本下载并校验官方 Hysteria 二进制，通过官方 HTTP 认证回调动态管理用户，并通过官方流量统计 API 显示在线设备和流量。

- 上游：[apernet/hysteria](https://github.com/apernet/hysteria)
- Hysteria 服务端配置：[官方文档](https://v2.hysteria.network/docs/advanced/Full-Server-Config/)
- 流量统计 API：[官方文档](https://v2.hysteria.network/docs/advanced/Traffic-Stats-API/)
- 连接 URI：[官方文档](https://v2.hysteria.network/docs/developers/URI-Scheme/)

## 一键部署

部署目标需要 systemd、root 权限、Python 3.8 或更高版本，以及 `apt`、`dnf` 或 `yum` 中至少一个受支持的软件包管理器。当前兼容性按自动化证据分层：

- **定期完整 E2E**：Ubuntu 24.04 LTS、Debian stable 与 Rocky Linux 9 的 amd64/arm64；nightly 会在干净的 systemd 容器中执行完整安装、升级和异常中断恢复；
- **尽力支持**：其他 Debian/Ubuntu 版本，以及 AlmaLinux、CentOS Stream、Fedora 等兼容 `apt`/`dnf`/`yum` 的 systemd 发行版。它们共享安装器路径但没有逐版本、逐架构的完整 E2E 证明，生产部署前必须先在同版本 canary 验证；SELinux enforcing 主机还需单独验证策略和日志。

```bash
set -euo pipefail
version=0.28.4
workdir="$(mktemp -d)"
trap 'rm -rf -- "${workdir}"' EXIT
case "$(uname -m)" in
  x86_64|amd64)
    cosign_asset=cosign-linux-amd64
    cosign_sha256=4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71
    ;;
  aarch64|arm64)
    cosign_asset=cosign-linux-arm64
    cosign_sha256=c5d324e091826b0d7a78eb16fef316450b4eb9aaec045611c08ba06f5e73220a
    ;;
  *) echo "仅支持 Linux amd64/arm64" >&2; exit 1 ;;
esac
release_url="https://github.com/Elegying/Hysteria2-panel/releases/download/v${version}"
curl -fL --retry 3 "${release_url}/install.sh" -o "${workdir}/install.sh"
curl -fL --retry 3 "${release_url}/install.sh.sigstore.json" -o "${workdir}/install.sh.sigstore.json"
curl -fL --retry 3 \
  "https://github.com/sigstore/cosign/releases/download/v3.1.3/${cosign_asset}" \
  -o "${workdir}/cosign"
printf '%s  %s\n' "${cosign_sha256}" "${workdir}/cosign" | sha256sum --check --status
chmod 0755 "${workdir}/cosign"
"${workdir}/cosign" verify-blob "${workdir}/install.sh" \
  --bundle "${workdir}/install.sh.sigstore.json" \
  --certificate-identity \
  "https://github.com/Elegying/Hysteria2-panel/.github/workflows/release-signature.yml@refs/tags/v${version}" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
bash -n "${workdir}/install.sh"
sudo bash "${workdir}/install.sh"
```

这段引导只执行固定正式版本的 Release 资产：先用固定 SHA-256 校验 Cosign，再验证安装器的 GitHub Actions OIDC/Sigstore 身份和 shell 语法，任一校验失败都不会以 root 执行。升级到新版本时请先把 `version` 改成对应的正式标签。

安装程序会询问分享节点名称、公网 IP/域名、Hysteria UDP 端口、面板端口与协议、管理员账号和密码。全新安装时面板协议默认是 `https`，并要求填写独立的面板公网域名，例如 `panel.ssrvpn.vip`；只有显式选择 `http` 时才启用明文管理面。出站策略默认是 `full`。密码输入不回显，也不会写入仓库或配置文件。也可以使用 `NODE_NAME`、`PUBLIC_HOST`、`HYSTERIA_PORT`、`PANEL_PORT`、`PANEL_SCHEME`、`PANEL_PUBLIC_HOST`、`EGRESS_POLICY`、`ADMIN_USER` 和 `ADMIN_PASSWORD` 环境变量执行无人值守部署。

重复运行安装器会先检查备份分区余量，再暂停面板写入而保持旧 Hysteria 统计端点运行，结算流量并截断 SQLite WAL 后建立带 SHA-256 清单的一致性备份；备份与开机恢复事务持久化后才允许覆盖程序。升级进程被强制终止或主机中途重启时，systemd 会在面板启动前核验清单并恢复旧版本，校验不通过则保持事务标记并拒绝覆盖。最终切换前会在认证入口已停止时，于有界窗口内持续为在线身份设置 Hysteria 断开标记，再执行最后一次流量结算并停止旧 Hysteria。`/kick` 只在客户端下一次产生流量时生效，因此完全空闲的会话可能仍显示在 `/online`，并由服务停止统一关闭；统计查询或踢线失败仍会安全回滚。恢复、手工安装、在线更新和 ACME 续期共用维护锁，不允许两项维护交叉写入。随后自动沿用现有节点名、域名、全部端口、面板协议、出站策略、HMAC 签名密钥、统计密钥、管理员和 Hysteria TLS 身份。Hysteria 的 `server.crt`、`server.key`、用户 URI 和固定指纹不会被 ACME 读取或替换；面板 HTTPS 使用另一套 Let’s Encrypt 证书。只有显式传入新值时才修改对应参数；需要重置管理员时设置 `RESET_ADMIN=1`。升级任一步或最终健康检查失败时，安装器会自动恢复旧程序、配置、证书/私钥、systemd 单元、sudoers 和网络参数；数据库优先保留升级窗口内通过完整性校验的最新状态，仅在损坏时清除 WAL/SHM 后恢复升级前快照。只有全部服务和端口通过检查后才解除回滚保护。自动备份仅清理符合安装器时间戳命名的目录，最多保留 10 份且最长 90 天，手工或恢复备份不会被匹配。这样普通升级不会令已经分享的节点失效，也不会留下半完成部署。

面板发现新正式版本后会显示“立即更新”。点击后页面会显示排队、运行、成功或失败状态，并在面板进程因升级重启期间自动重试状态查询；只有固定更新任务已经成功结束且新进程的当前版本达到目标版本才会显示成功，不再把 systemd 任务已启动或新进程刚启动误报成升级完成。该操作只允许已登录管理员携带 CSRF token 启动固定的 `hysteria2-panel-update.service`，浏览器不能传入版本、下载地址或命令。root 更新任务读取并严格校验面板排队时固定的 `vX.Y.Z` 目标，不会因执行期间出现更新版本而改变实际安装版本；随后从该版本路径下载安装器，核对安装器内版本、Sigstore 身份、解释器头和 shell 语法，再以专用非交互模式升级。在线升级强制沿用当前节点与面板参数并保留管理员、数据库、HMAC、统计密钥、TLS 证书和私钥；全新服务器不能使用该内部模式。

默认端口：

| 用途 | 监听地址 | 默认端口 |
|---|---|---:|
| Hysteria 2 | 公网 UDP | `19999` |
| 账号专属 Hysteria 入口 | 公网 UDP | `443`（按账号开启） |
| TCP 连通性兼容探测 | 公网 TCP | `19999` 和 `443` |
| 管理面板 | 公网 HTTPS TCP（可显式选择 HTTP） | `19998` |
| ACME HTTP-01 校验 | 公网 TCP（仅签发/续期时临时监听） | `80` |
| 流量统计 API | `127.0.0.1` | `19997` |
| UDP 443 入口流量统计 API | `127.0.0.1` | `19995` |
| Hysteria 认证回调 | `127.0.0.1` | `19996` |

服务器使用带 IP/域名 SAN 的 10 年自签名证书保护 Hysteria 连接。面板生成的 Hysteria URI 同时包含 `insecure=1` 和证书 SHA-256 固定指纹。面板使用 HTTP 并不影响 Hysteria 数据通道的 TLS 和证书固定。

全新安装默认使用 HTTPS；显式选择 HTTP 时仍不会设置 Secure Cookie 或 HSTS，管理员密码、会话以及备份上传下载内容都会在网络中明文传输。安装器从系统软件源安装 Certbot（RHEL/Rocky/Alma/CentOS 在当前仓库缺包时通过包管理器启用 EPEL），使用 standalone HTTP-01 为 `PANEL_PUBLIC_HOST` 申请 Let’s Encrypt 证书，并启用 `hysteria2-panel-cert-renew.timer` 每天检查两次。首次签发和后续续期都要求该域名解析到当前服务器，公网 TCP `80` 持续可达且不能被其他本机服务占用。续期成功后只重启面板服务，不重启 Hysteria；失败时保留旧面板证书并写入 journal。升级会原样保留现有面板协议，不会把历史 HTTP 安装静默迁移到 HTTPS，也不会触碰 Hysteria 客户端 URI、证书或固定指纹。

面板证书采用版本目录加单一 `panel-tls-current` 链接切换，证书和私钥先完成域名及公钥配对校验再一起生效。`/etc/hysteria2-panel/panel.crt` 与 `panel.key` 只用于面板；Hysteria 永远继续使用独立的 `server.crt` 与 `server.key`。从旧版本的自签名 HTTPS 升级时必须人工运行一次安装器补填 `PANEL_PUBLIC_HOST`；在线自动更新会安全拒绝缺少该字段的旧 HTTPS 配置，避免静默继续复用节点证书。

部分网络设备会检查明文 HTTP 的 `Host` 并主动重置特定域名连接。安装器在节点域名与本机检测 IP 不同时会同时打印备用面板地址；确认该 IP 可从公网路由后，可用 `http://服务器IP:面板端口/` 登录，不需要修改 Hysteria 节点域名、证书或已分享 URI。面板会安静处理这类预期断连，避免服务日志被无意义的异常栈淹没。

> 安装器会先识别防火墙所有权：UFW 或 firewalld 中恰好一个启用时，以该管理器的查询结果为准并自动放行用户输入的 Hysteria 端口（TCP/UDP）、面板端口（TCP）、账号专属入口 `443`（TCP/UDP），以及 HTTPS 模式所需的 ACME TCP `80`。UFW 对冲突或无法证明无关的入站 deny/reject/limit 会停止；firewalld 目标 zone 存在 rich rule 时也会安全停止。写入后会再次复查全部目标规则与 zone，任何漂移或缺失都会撤销本次已添加规则。两者都未启用时才只读检查 nftables、IPv4 iptables 与 IPv6 ip6tables；无规则则保持不变，自定义入站策略或检查失败则停止。安装器不会主动启用防火墙；云平台安全组不在主机控制范围内，仍需人工放行。自动开放的面板端口对所有来源生效；生产环境应再在安全组中把该端口限制为固定管理 IP，但 TCP `80` 必须允许 Let’s Encrypt 公网校验。设计依据见 [ADR-012](docs/decisions/ADR-012-managed-firewall-port-opening.md)。

TCP `19999` 和 TCP `443` 使用同一个兼容探测程序：只接受连接后立即关闭，不读取或返回应用数据。它们用于兼容只会对节点地址执行 TCP 连通性测试的客户端，不代表 Hysteria UDP/QUIC 数据通道的真实健康状态；两个探测服务分别随对应的 Hysteria 服务启停。TCP `443` 探测成功也不代表账号已获准使用 UDP `443`。

## 多用户管理

登录面板后可以：

- 从“对接节点”生成短时一次性注册代码；新服务器注册后须由管理员逐字核对 Ed25519 公钥 SHA-256 指纹，验证通过后才能启用每分钟一次的签名心跳与中央控制协议；
- 对已验证且控制协议就绪的节点生成第二段数据面一键部署代码。授权绑定节点身份、来源 IP 和 Ed25519 签名，10 分钟内最多获取 3 次，安装 ACK 后立即失效。数据节点仅运行 Hysteria、回环认证代理、控制循环和 TCP 探针，不安装管理面板、用户数据库或 HMAC；安装不会修改 DNS、`vpn.ssrvpn.vip`、用户链接或证书指纹；
- 数据面安装成功后仍须人工完成直连灰度，再在面板单独记录“直连灰度已通过”。面板提供 DNS 准入/移除按钮与 API，用于记录管理员决策；它们不会修改外部 DNS，也不会自动把节点加入用户流量池；
- 创建、编辑、启用、禁用和删除用户，并设置客户端实例数与总流量限制（默认 `3` 个实例、`250 GiB`）；编辑用户可单独开放 UDP `443`，不会修改用户 token 或分享 URI；用户列表可按用户名搜索，并组合筛选启用状态、在线状态和 UDP `443` 授权，筛选后仍可按在线设备数或总流量排序；
- 在同一页查看全部用户，并通过用户名即时搜索；添加用户使用弹窗，不占用列表空间；
- 轮换用户认证密钥，一键复制可导入的连接 URI；每个用户节点还可按需弹出配置二维码，并保存为 PNG；
- 查看在线设备数、上传/下载流量、总流量进度和高流量前五用户；
- 重置单个用户或全部用户的累计流量；
- 查看服务状态、当前用户数、不活跃用户数、在线设备总数以及总上传/下载流量；
- 查看 CPU、内存、磁盘、运行时长、面板版本，并检查和在线安装正式更新；更新安装器会先核验固定 GitHub Actions 身份的 Sigstore 签名，签名缺失或不匹配时不会执行；系统资源模块提供带二次确认的整机重启入口；
- 在面板内启动、停止或重启项目专用 Hysteria 服务。
- 使用响应式桌面/手机布局；手机端用户表格会自动转为便于触控的卡片。
- 从顶部“数据迁移”弹窗一键下载完整备份，或在新服务器上传恢复用户、流量、签名密钥和 TLS 节点身份。

管理员登录按来源 IP 防破解：15 分钟内第 5 次密码错误会立即返回 HTTP `429` 并锁定该来源 15 分钟，锁定期间正确密码也不能登录；成功登录会清除该 IP 的失败记录。同一 IPv6 `/64` 前缀按一个来源统计，避免轮换接口地址绕过锁定。锁定状态保存在进程内存中，重启面板会清空；它用于阻挡普通单源爆破，不替代安全组来源限制或独立的主机级入侵防护。设计同时考虑了 [OWASP 对通用错误、登录限速和拒绝服务风险的建议](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)。

每个 HTTP 连接同时受 10 秒读写空闲超时和 30 秒请求总截止时间约束，慢速持续发送数据也不能永久占用工作线程。管理审计记录最多保留 90 天和最近 10,000 行，任一上限先到即清理；备份仍不包含审计日志。

分享 URI 的节点名称由安装参数 `NODE_NAME` 统一设置，不再随面板中的用户名称变化。

每个账号默认只能使用主 Hysteria UDP 端口（默认 `19999`）。在“编辑用户”中开启 UDP `443` 后，该账号可以继续使用原 URI，也可以在客户端复制原配置后仅把服务器端口从 `19999` 改为 `443`；面板不会自动把分享 URI 改成 `443`。未开启的账号在 UDP `443` 入口会认证失败。两个入口共用相同域名、证书、token、设备数和流量额度，在线实例数与流量会合并统计。

账号级端口授权由第二个 Hysteria 进程实现。Hysteria 单个服务端配置只有一个监听地址，HTTP 认证请求也不包含客户端连接的目标端口，因此单纯端口转发或一个监听器无法区分账号是否从 `443` 进入。第二进程只把认证回调切换为 `/auth/udp-443`，其余 TLS 和出站策略与主入口一致；设计依据见 [ADR-011](docs/decisions/ADR-011-per-user-udp-443-entrypoint.md)。

新建或轮换的用户密钥由随机种子和服务器 HMAC key 派生，因此面板可以重新生成分享 URI，但数据库仍不保存认证密钥明文。旧版本用户保持原连接有效；由于原密钥只有不可逆指纹，需明确轮换一次后才能使用分享按钮。禁用、删除或轮换用户时，面板会调用 Hysteria 流量 API 断开现有连接。

Hysteria 的 `/kick` 对同一用户名使用一次性断开标记。禁用、删除或流量超额的账号若同时有多个客户端实例，面板会在后台同步时继续批量请求清退，直到 `/online` 不再报告该账号；认证后端同时拒绝这些账号重新连接。由于断开标记会在客户端产生下一次流量时生效，完全空闲的连接可能要到再次传输或自行重连时才从在线统计消失。

“设备限制”依据 Hysteria 官方 `/online` API 返回的 Hysteria 客户端实例数执行，不是活动代理流数量。默认限制为 3 时，已有 3 个实例会继续使用；第 4 个实例的认证返回失败，不会踢掉最早在线的实例，直到已有实例离线后才能连接。面板还用 5 秒短期预留防止多个认证同时越过上限；在线统计或流量统计不可用时，新认证会失败关闭。

该接口不能识别物理硬件：同一个网关或热点客户端后面的多台终端可能只算 1 个实例，客户端重连或同时运行多个核心也可能产生多个实例。因此“3 台设备”应理解为“最多 3 个同时在线的 Hysteria 客户端实例”，不能作为硬件授权系统。标准 Hysteria 认证请求没有稳定硬件 ID；用来源 IP/端口代替会在 NAT、移动网络切换和重连时误判。只有配套受控客户端、逐设备凭据和服务端设备登记才能实现接近硬件授权的限制，但这会改变现有的一用户一链接兼容方式。面板在统计值大于配置上限时会把用户名标红并显示“客户端实例超限”，便于管理员处理降低限额后的存量连接或统计时序竞争。

> Hysteria TUN 只转发 TCP/UDP，不代理 ICMP。节点能正常访问网页但系统 `ping` 超时并不表示节点故障，服务端无法通过放行 UDP 端口改变这一协议边界。

## YouTube、网页与网络优化

一键部署会采用 Hysteria 官方的非 Brutal `bbr` 拥塞控制和 `standard` profile，并忽略客户端上报带宽，减少用户填错带宽造成的体验波动；同时根据 [Hysteria 性能指南](https://v2.hysteria.network/docs/advanced/Performance/) 把 Linux UDP 收发缓冲上限提高到至少 16 MiB、设置 Hysteria 服务 `Nice=-5` 和高文件描述符上限。若内核支持，还会为服务器访问 YouTube/CDN/网页源站时产生的 TCP 出站连接启用 `fq` + 内核 BBR；内核不支持时会安全跳过，不阻断部署。

Hysteria 自身的 QUIC BBR 与 Linux `net.ipv4.tcp_congestion_control` 是两层不同的优化：前者管理客户端到服务器的 UDP/QUIC 隧道，后者只影响服务器到以 TCP/HTTPS 提供内容的源站。项目不会自动估算线路带宽或启用 Brutal，也不会写入缺少官方依据的“万能 sysctl”。线路拥塞、跨境路由、丢包、客户端核心和源站限速仍会决定最终体验。

### BT/PT 与出站防滥用

默认 `EGRESS_POLICY=full` 使用 Hysteria 官方 ACL：先拒绝未指定、环回、私网、链路本地、CGNAT、IPv6 ULA、组播和保留目标，然后放行所有公网目标及端口。这保留完整的公网代理能力，同时阻断通过环回或内网地址访问节点及其内网服务。`full` 会允许 BT/PT、SMTP、游戏和非标准端口，也会增加扫描、爆破、垃圾邮件和版权投诉风险；管理员需要配置用户限额，并通过审计和禁用及时处置滥用。ACL 规则按官方的从上到下首条匹配语义执行：[Hysteria ACL 文档](https://v2.hysteria.network/docs/advanced/ACL/)。

如果需要限制为网页/视频用途，可在面板“服务控制”的服务端口卡片关闭 `FULL`，也可在部署时设置 `EGRESS_POLICY=web`。`web` 会在相同的本地/私网拒绝规则之后，仅允许公网目标的 SSH TCP `22`、管理面板 TCP 端口、TCP `80/443`、UDP `443`、TCP/UDP `53` 和 UDP `123`，最后拒绝其他目标与端口。面板开关是整台节点的全局策略，不是单账号设置；运行中切换会短暂重启两个 Hysteria 入口并中断现有连接，已停止的节点只更新配置并保持停止。

面板只允许管理员通过会话和 CSRF 保护的固定 `web/full` 路由启动两个参数固定的 root systemd 任务。root 任务在共用维护锁内同步更新 `panel.env`、主端口和 UDP `443` 配置；运行中的节点重启后复核服务，已停止的节点保持停止。任一步失败都会恢复三份旧文件和切换前服务状态。浏览器请求不能提供命令、文件路径、端口或任意 ACL 内容。

这是端口和目标地址策略，不是 DPI。BitTorrent 可以加密，也可以伪装到 `web` 允许的 `80/443` 或经外部中继传输，所以任何仅靠 Hysteria ACL 的方案都不能诚实保证 100% 识别所有 BT/PT。切换策略不会改变用户链接、认证密钥、证书或证书指纹。

## 跨服务器备份与恢复

面板的“用户数据迁移”模块可下载一个 ZIP，包含只保留代理用户数据的一致性 `panel.db` 快照、用户 token 派生所需的 HMAC 签名密钥、当前 TLS 证书和私钥，以及记录源节点域名、UDP 端口、节点名、证书指纹、证书有效期和各文件 SHA-256 的清单。当前格式会保留每个账号的 `443` 授权；从缺少该字段的旧备份恢复时默认关闭，必须由管理员重新开启。旧管理员密码哈希、面板会话和审计日志不会写入 ZIP。这个 ZIP 仍等同于全部节点登录凭据，尤其在 HTTP 面板模式下下载和上传都没有传输层加密，必须只在可信网络操作并离线保管。

恢复 ZIP 上传和预检期间，面板使用独立的非阻塞维护门：新的管理变更会立即返回 `503`，不会占满工作线程或在客户端超时后继续排队执行；健康检查、节点控制协议和已有数据面会话不因此改变。

推荐迁移顺序：

1. 在旧服务器下载备份，不要删除旧服务器；
2. 在新服务器用与旧节点完全相同的 `PUBLIC_HOST` 和 `HYSTERIA_PORT` 完成一键部署；
3. 先在云平台安全组放行新服务器对应 TCP/UDP 端口（受管主机 UFW/firewalld 由安装器处理），通过新服务器 IP 打开面板并上传 ZIP；不要提前把 DNS 指向尚未恢复用户身份的新服务器；
4. 恢复服务会再次独立校验、结算未落盘流量、自动备份新服务器当前身份，再以持久事务标记恢复代理用户/流量/签名密钥/证书。启动前的 `restore-recover` 阶段只负责把文件收口为完整的新身份或完整的回滚身份；服务启动后的 `restore-resume` 阶段连续复核 systemd、HTTP、统计和 TCP 健康后才删除标记。进程退出或主机重启会从标记继续，失败 ZIP 会隔离保存且不会堵塞下一次上传；
5. 确认新面板用户数、证书指纹和服务状态正确后再切换 DNS，用已有客户端旧配置完成 Hysteria 握手和网页/视频测试；
6. 至少保留旧服务器一个 DNS TTL 回退窗口，确认稳定后再停用。

恢复不会覆盖新服务器当前的面板管理员账号、统计 API secret、面板端口、协议或出站策略。全部旧面板会话都会失效。代理用户会由备份整体替换，因此新服务器恢复前临时创建的代理用户会被移除。

为保证旧连接 URI 不变，恢复会拒绝源域名或 UDP 端口与当前部署不一致的 ZIP。使用域名时只需更新 DNS；如果旧 URI 直接写的是旧服务器 IP，或迁移时必须改端口，客户端地址已发生变化，无法做到无感恢复，必须重新分享配置。

证书指纹固定的是叶子证书。安装器升级和备份恢复都会保留原证书/私钥，不自动续签或重签；当前自签名证书默认生成 10 年有效期。证书到期后续签、重签或主动轮换会产生新指纹，旧 URI 必须更新后重新分享。Hysteria 官方说明服务端在每次 TLS 握手读取证书文件，客户端 `pinSHA256` 校验服务端证书指纹：[服务端 TLS 配置](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#tls)、[客户端 TLS 配置](https://v2.hysteria.network/docs/advanced/Full-Client-Config/#tls)。

## 运维

多台节点请遵循 [`max-unavailable=1` 发布与回滚流程](docs/DEPLOYMENT.md)，每次只升级并验收一台。

```bash
systemctl status hysteria2-panel hysteria2-panel-server hysteria2-panel-server-443 hysteria2-panel-tcp-probe hysteria2-panel-tcp-probe-443 hysteria2-panel-restore hysteria2-panel-restore-recover hysteria2-panel-restore-resume hysteria2-panel-cert-renew.timer hysteria2-panel-update
journalctl -u hysteria2-panel -u hysteria2-panel-server -u hysteria2-panel-server-443 -u hysteria2-panel-tcp-probe -u hysteria2-panel-tcp-probe-443 -u hysteria2-panel-restore -u hysteria2-panel-restore-recover -u hysteria2-panel-restore-resume -u hysteria2-panel-cert-renew.service -u hysteria2-panel-update --since today
curl http://127.0.0.1:19998/healthz
curl http://127.0.0.1:19998/readyz
curl http://127.0.0.1:19998/metrics
```

关键路径：

| 路径 | 内容 |
|---|---|
| `/opt/hysteria2-panel/` | 面板程序和项目专用 Hysteria 二进制 |
| `/etc/hysteria2-panel/` | Hysteria 配置、TLS 证书和运行环境 |
| `/etc/hysteria2-panel/acme/` | 面板 ACME 账户、续期配置与 Let’s Encrypt lineage |
| `/var/lib/hysteria2-panel/panel.db` | 用户、会话和审计记录 |
| `/var/backups/hysteria2-panel/` | 每次覆盖部署和恢复前的自动备份 |
| `/etc/sysctl.d/99-hysteria2-panel.conf` | 16 MiB QUIC UDP 缓冲，以及内核支持时的 `fq`/TCP BBR |
| `/etc/sudoers.d/hysteria2-panel` | 仅允许固定服务控制、整机重启，以及启动一次性恢复/更新服务 |
| `/etc/tmpfiles.d/hysteria2-panel.conf` | 每次开机重建维护锁目录；root 任务持排他锁，面板仅能只读取得恢复上传准入共享锁 |

### 回滚

安装器在覆盖已有部署前会在线生成一致的 SQLite 备份，并复制应用、配置、全部项目 systemd unit、启用状态、sudoers、sysctl 和 tmpfiles。升级失败会自动恢复旧版本并复核所有旧入口。

若自动回滚仍明确报告失败，不要只复制某个 `panel.db` 或只启动两个服务：当前拓扑还包含主/`443` Hysteria、两条 TCP 探测、恢复前置/后置任务、更新任务、WAL/SHM、启用链接和持久恢复标记。应先保持当前文件与最近的 `/var/backups/hysteria2-panel/<时间戳>/` 不变，记录 `systemctl status` 与上述各 unit 的日志，再在停机维护窗内按该备份整体恢复；无法确认服务已全部停止、数据库检查通过和身份四件套（数据库、HMAC 环境、证书、私钥）一致时不要覆盖。恢复后必须执行 `daemon-reload`，并重新验证面板/认证健康、主端口与获准 `443` 的 UDP/TCP 监听和旧链接握手。

## 本地验证

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile hysteria2_panel.py qrcodegen.py tcp_probe.py
bash -n install.sh tests/firewall_integration.sh tests/systemd_integration.sh
shellcheck install.sh tests/firewall_integration.sh tests/systemd_integration.sh
python3 -m pip install ruff==0.12.11 bandit==1.8.6
ruff check hysteria2_panel.py tcp_probe.py tests
bandit -q -r hysteria2_panel.py tcp_probe.py hy2panel
```

自动化会验证认证、限额、备份恢复、HTTP 行为、安装器契约和静态安全边界，并在 Linux CI 中执行真实 UFW、firewalld 与 systemd 依赖语义测试。发布后仍应在真实客户端完成：主端口与获准账号 UDP `443` 的 Hysteria 握手、未获准账号的 `443` 拒绝、网页访问、YouTube 连续播放、TCP `19999` 和 TCP `443` 延迟探测、旧分享 URI、双入口流量累计和重启后恢复。ICMP `ping` 不属于 Hysteria 可用性验收。

## 架构与接口

- [ADR-001：使用本机 HTTP 认证回调和标准库面板](docs/decisions/ADR-001-local-auth-panel.md)
- [ADR-002：可选 HTTP 面板与 QUIC UDP 优化](docs/decisions/ADR-002-panel-http-and-udp-tuning.md)
- [ADR-003：持久流量、连接限额与受限服务控制](docs/decisions/ADR-003-usage-policy-and-service-control.md)
- [ADR-004：可迁移用户身份与原子恢复](docs/decisions/ADR-004-portable-backup-restore.md)
- [ADR-005：HTTP 缺省、登录锁定与双层 BBR 优化](docs/decisions/ADR-005-http-login-network-hardening.md)
- [ADR-006：网页/视频出站策略与 BT/PT 防滥用边界](docs/decisions/ADR-006-web-egress-abuse-control.md)
- [ADR-007：固定来源的非交互在线更新](docs/decisions/ADR-007-fixed-source-online-update.md)
- [ADR-008：工作线程监督与升级失败自动回滚](docs/decisions/ADR-008-runtime-supervision-upgrade-rollback.md)
- [ADR-009：可观测在线更新与受限运维操作](docs/decisions/ADR-009-observable-update-and-admin-operations.md)
- [ADR-010：网页策略下允许公网 SSH 运维](docs/decisions/ADR-010-public-ssh-egress.md)
- [ADR-011：单账号 UDP 443 双入口授权](docs/decisions/ADR-011-per-user-udp-443-entrypoint.md)
- [ADR-012：受管防火墙端口自动开放](docs/decisions/ADR-012-managed-firewall-port-opening.md)
- [ADR-013：无密钥签名更新、模块边界与运行时就绪](docs/decisions/ADR-013-keyless-update-modules-readiness.md)
- [ADR-014：面板内受限切换节点全局出站策略](docs/decisions/ADR-014-runtime-egress-policy-switch.md)
- [ADR-015：可跨重启恢复的安装器升级事务](docs/decisions/ADR-015-crash-consistent-installer-upgrades.md)
- [HTTP 接口契约](docs/API.md)

## 许可证

项目主体使用 [MIT](LICENSE)。随版本固定的 `qrcodegen.py` 来自 [Nayuki QR Code generator](https://github.com/nayuki/QR-Code-generator)，并在源码头保留其 MIT 许可证全文。

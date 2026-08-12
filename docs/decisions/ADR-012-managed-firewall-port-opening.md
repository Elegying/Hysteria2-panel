# ADR-012：仅为已启用的受管防火墙自动开放部署端口

## 状态

已接受，2026-08-12。取代 ADR-005 和 ADR-011 中“不自动修改防火墙”的决定。

## 背景

安装器已经创建并检查 Hysteria、TCP 探测和面板监听，但服务器启用主机防火墙时，监听成功不代表公网可达。要求一键部署自动处理用户输入的节点端口、面板端口和账号专属 `443`，同时不能在原本没有防火墙限制的主机上凭空启用防火墙，也不能因猜测自定义规则结构而破坏 SSH 或其他业务。

## 决策

- 先识别防火墙所有权。UFW 与 firewalld 同时启用时在写入前停止；恰好一个启用时只通过该管理器的公开查询和写入接口处理规则，因为其底层会正常生成 nftables/iptables 规则，不能把这些规则误判为外部自定义策略。
- 只有 UFW 状态为 `active` 时才用 UFW 添加规则；只有 firewalld 正在运行时才处理其规则。安装器绝不执行 `ufw enable`，也不启动或启用 firewalld。
- UFW 的声明式规则中若存在与目标端口冲突或无法证明无关的入站 `deny`/`reject`/`limit`，安装器停止而不追加冲突 allow；解析覆盖 `prepend`/`insert`、单端口、列表、范围和完整 `from … to … port` 语法，并且只把目标端口而不是来源端口用于冲突判断。明确无关的端口规则和出站规则不会误阻断。
- `ufw show listening` 只用于确认 UFW 用户规则对真实监听端口的顺序，不能证明 framework 或管理器外规则安全。因此另行要求 `/etc/ufw/{before,before6,after,after6}.rules` 与发行版 `/usr/share/ufw/iptables/` 模板逐字一致、`before.init`/`after.init` 不可执行，并用 `ufw show raw`、`iptables-save`、`ip6tables-save` 和 `nft -j list ruleset` 核对实时 INPUT/PREROUTING 所有权。任一文件缺失、命令失败、JSON/规则结构无法解析或出现外部 base hook/原始入站规则都安全停止。
- firewalld 只支持能经 D-Bus 确认 `FirewallBackend=nftables` 的现代后端；旧 `iptables` 后端或 D-Bus 查询失败均停止。安装器先从 `firewall-cmd --help` 探测本机能力：不存在的 panic/policy/direct 功能不调用；若 direct 接口存在，则 `get-all-chains`、`get-all-rules`、`get-all-passthroughs` 必须全部可用且运行态、永久态均为空。命令返回 `0` 表示查询成功，布尔查询的 `1` 表示否，其余返回码均视为检查失败。
- firewalld 目标 zone 只接受没有 rich rule 的普通端口配置；发现 rich rule 时安全停止，不尝试重写复杂策略。支持 policy 的版本会同时审查运行态和永久态：已禁用 policy 跳过；仅当 egress 包含 `HOST` 时影响主机入站，`DROP`/`REJECT` target 或负向 rich action 是 blocker，`CONTINUE`/`ACCEPT` 且无负向 action 可继续，包括系统默认 `allow-host-ipv6`。同时核对 firewalld 自有 nftables 表之外的入站 base hook，以及 legacy iptables 视图中的未跟踪 direct `--passthrough` 规则。
- 两个管理器都未启用时，只读检查 nftables、IPv4 iptables 和 IPv6 ip6tables；检查命令失败或存在自定义入站策略时停止，不尝试推断自定义跳转链的最终语义。
- 自动开放 Hysteria 端口的 TCP/UDP、面板端口的 TCP，以及独立 `443` 入口的 TCP/UDP `443`。可配置端口必须先通过数字和 `1–65535` 范围校验；若升级保留既有特权端口，仅相应绑定服务获得 `CAP_NET_BIND_SERVICE`。主 Hysteria 端口本身为 `443` 时沿用旧版语义，不再启动第二套账号专属 `443` 入口。
- firewalld 对每个活动 zone 和默认 zone 分别查询并补充当前运行规则和永久规则，不执行可能中断现有连接的全局 reload。
- 防火墙写入在本机服务、健康检查和监听检查全部成功之后执行。只记录本次新增项；任一步失败按相反顺序撤销这些项，成功后才解除应用升级回滚保护。最终再次核对全部目标端口、UFW deny、firewalld zone 与 rich rules，避免写入期间漂移造成误报成功；重复部署不修改已经存在的规则。
- 若 UFW 和 firewalld 都未启用，且三套 netfilter 检查均确认没有自定义入站策略，则不修改任何规则。
- 若检测到未受支持的自定义 `iptables`/`nftables` 入站阻断，安装器停止并给出明确错误，不猜测表、链、优先级或持久化方式。所有检查均在首次预检、写入前重算和写入后最终验证执行，检查状态漂移时撤销且只撤销本次新增规则。
- 云平台安全组不由主机安装器控制，部署结果继续提示管理员人工放行。

## 备选方案

### 无条件启用 UFW 或 firewalld

会改变服务器原有安全模型，并可能在 SSH 规则尚未准备时锁死远程管理，因此拒绝。

### 直接向任意 iptables/nftables 规则集插入 ACCEPT

无法可靠判断自定义表链、nftables hook 优先级、IPv4/IPv6 对称性和重启后的持久化方式。错误插入可能无效，也可能绕过管理员的来源限制，因此拒绝。

### 继续只打印提示

不能满足一键部署在常见受管防火墙环境中自动可用的目标，因此由本决策取代。

## 后果

- 使用发行版默认、未定制的 UFW 或 nftables 后端 firewalld 可在一次部署内完成主机端口放行且重复执行不产生新规则；未启用防火墙的系统保持原状。
- 自动开放面板 TCP 端口等价于允许所有来源访问该端口。面板仍有认证、CSRF 和登录限速，但生产环境应在云安全组进一步限制管理来源。
- 自定义 UFW framework、firewalld rich/direct/passthrough/policy 阻断、旧 firewalld iptables 后端，以及没有 UFW/firewalld 所有权的自定义 netfilter 策略，需要管理员先简化或手工配置；安装器以安全失败代替冒险改写。
- 严格所有权检查会拒绝部分本来可能不影响目标端口的高级配置，这是有意的 fail-closed 取舍；安装器不把“看起来无害”当作已经证明无害。
- 主机防火墙成功不代表云安全组已经开放，公网验收仍需独立检查云侧规则。

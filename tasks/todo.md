# 分流节点数据面第四阶段任务

- [x] 第四阶段规格、计划与任务合同
  - Acceptance: 状态、API、秘密、回滚、质量门和 DNS 排除范围均可测试。
  - Verify: 人工审阅三个文档；`git diff --check`
  - Dependencies: v0.26.0 正式发布和 `.201` 升级验收
  - Files: `docs/specs/2026-08-28-data-plane-phase-4.md`, `tasks/plan.md`, `tasks/todo.md`
  - Scope: Medium

- [ ] bootstrap 状态机与 token 生命周期
  - Acceptance: 仅 verified+protocol-ready 节点可创建；10 分钟/3 次/IP/节点绑定；ACK 烧毁。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.DataPlaneBootstrapStateTests -v`
  - Dependencies: 规格批准
  - Files: `hysteria2_panel.py`, `hy2panel/nodes.py`, `tests/test_data_plane_bootstrap.py`
  - Scope: Medium

- [ ] HTTPS bootstrap 与 ACK 接口
  - Acceptance: Ed25519+nonce+token 全校验；响应内存流式发送；数据库/日志/审计无秘密。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.DataPlaneBootstrapHttpTests -v`
  - Dependencies: bootstrap 状态机
  - Files: `hysteria2_panel.py`, `hy2panel/nodes.py`, `tests/test_data_plane_bootstrap.py`
  - Scope: Medium

- [ ] 节点身份验证与配置渲染
  - Acceptance: PEM 可解析、证书/私钥匹配、三摘要一致；只生成固定 19999/443 配置。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.NodeDataPlaneConfigTests -v`
  - Dependencies: HTTPS bootstrap
  - Files: `node_agent.py`, `tests/test_data_plane_bootstrap.py`
  - Scope: Medium

- [ ] phase4 安装器事务与回滚
  - Acceptance: 预检零写入；成功只写 owned paths；任一失败恢复 phase2 并清除节点 TLS 副本。
  - Verify: `python3 -m unittest tests.test_installer.DataPlaneInstallerContractTests -v`
  - Dependencies: 节点身份验证与配置渲染
  - Files: `install.sh`, `tests/test_installer.py`
  - Scope: Medium

- [ ] 数据节点 systemd 与本地健康证明
  - Acceptance: auth proxy/control/Hysteria/probe 权限隔离；ACK 摘要和 stats/监听真实可验证。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.DataPlaneAttestationTests tests.test_installer -v`
  - Dependencies: phase4 安装器事务
  - Files: `node_agent.py`, `install.sh`, `tests/test_data_plane_bootstrap.py`, `tests/test_installer.py`
  - Scope: Medium

- [ ] 管理员 UI、审计与版本文档
  - Acceptance: 部署/installed/canary/DNS 状态独立；无秘密进 HTML/审计；版本 v0.27.0 一致。
  - Verify: `python3 -m unittest tests.test_panel tests.test_data_plane_bootstrap -v` + 320/768/1440px
  - Dependencies: 数据节点健康证明
  - Files: `hysteria2_panel.py`, `hy2panel/web_assets.py`, `hy2panel/version.py`, `CHANGELOG.md`, `docs/API.md`
  - Scope: Medium

- [ ] 全量门禁与安全审查
  - Acceptance: 全量测试/静态门通过；无任意命令面、秘密持久化或 DNS 写路径。
  - Verify: 规格全部命令、故障注入、`git diff --check`
  - Dependencies: 所有代码任务
  - Files: 本阶段改动
  - Scope: Medium

- [ ] v0.27.0 PR、受保护 CI 与签名发布
  - Acceptance: exact-head PR/main/tag CI、六平台矩阵、Sigstore 和匿名 synthetic 全绿。
  - Verify: GitHub runs + Release 资产逐字节/签名验证
  - Dependencies: 全量门禁与审查
  - Files: GitHub refs/Release
  - Scope: Large

- [ ] `.201` 升级与身份不变量
  - Acceptance: 351 用户身份、URI、Hysteria cert/key/pin、HMAC、端口和 DNS 不变。
  - Verify: root-only 快照、SQLite quick_check、前后 SHA-256、healthz/readyz
  - Dependencies: v0.27.0 正式发布
  - Files: `.201` 生产主机
  - Scope: Large

- [ ] `.210` 数据面部署与直连灰度
  - Acceptance: 无面板/用户库/HMAC；19999/443、真实 204、全局设备/流量/故障语义通过。
  - Verify: 独立直连 Hysteria、stats/central ledger、服务/端口/日志/身份哈希、回滚点
  - Dependencies: `.201` v0.27.0、节点 verified+protocol-ready
  - Files: `.210` 数据节点与 `.201` 控制面
  - Scope: Large

- [ ] 第五阶段 DNS admission（明确不在本阶段执行）
  - Acceptance: 用户再次明确批准，且权威 DNS 变更与回滚方案已单独审查。
  - Verify: 变更前后权威 DNS、多解析器、真实用户链路和回滚演练
  - Dependencies: `.210` 直连灰度通过 + 新人工批准
  - Files: Cloudflare DNS
  - Scope: Large

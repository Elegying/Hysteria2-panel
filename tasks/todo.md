# 数据节点极简对接任务

- [x] 签名 bootstrap claim 与自动协议门
  - Acceptance: 仅已核对指纹且心跳在线的节点可领取；重复领取废止旧 grant；无管理员凭据下发。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.AutoBootstrapClaimTests -v`
  - Dependencies: None
  - Files: `hy2panel/nodes.py`, `hysteria2_panel.py`, `node_agent.py`, `tests/test_data_plane_bootstrap.py`
  - Scope: Medium

- [x] 持久 onboarding 完成器
  - Acceptance: 首次命令返回后 timer 持续等待；重启可恢复；成功自动运行现有 heartbeat/data-plane 事务并自清理。
  - Verify: `python3 -m unittest tests.test_installer.StreamlinedOnboardingInstallerTests -v`
  - Dependencies: 签名 claim
  - Files: `install.sh`, `tests/test_installer.py`
  - Scope: Medium

- [x] bootstrap 绑定的真实 Hysteria 灰度
  - Acceptance: 不创建真实用户；仅活动 grant 可认证；中央通过节点公网 IP 获得外部响应；失败不 ACK。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.HysteriaCanaryRunnerTests -v`
  - Dependencies: 持久完成器
  - Files: `hysteria2_panel.py`, `hy2panel/nodes.py`, `tests/test_data_plane_bootstrap.py`
  - Scope: Medium

- [x] DNS 只读检测和自动准入
  - Acceptance: 只在解析含预期公网 IP、灰度已过及控制状态新鲜时准入；不写 DNS、不自动移除。
  - Verify: `python3 -m unittest tests.test_data_plane_bootstrap.NodeDnsAdmissionReconcilerTests -v`
  - Dependencies: 自动灰度
  - Files: `hysteria2_panel.py`, `install.sh`, `tests/test_data_plane_bootstrap.py`, `tests/test_installer.py`
  - Scope: Medium

- [x] 向导 UI、API/运维文档与版本说明
  - Acceptance: 管理员日常只需一条命令、一次指纹确认、一次 DNS 修改；所有不可自动化边界明确可见。
  - Verify: `python3 -m unittest tests.test_panel tests.test_node_onboarding -v`
  - Dependencies: 全部行为切片
  - Files: `hy2panel/web_assets.py`, `docs/API.md`, `docs/DEPLOYMENT.md`, `README.md`, `CHANGELOG.md`
  - Scope: Medium

- [ ] 完整质量门和对抗审查
  - Acceptance: 行为测试与静态门全绿；无任意 root 命令、秘密泄漏、自动证书轮换或用户配置变化。
  - Verify: 仓库全量测试与静态检查；`git diff --check`
  - Dependencies: 全部实现
  - Files: 本分支改动
  - Scope: Medium

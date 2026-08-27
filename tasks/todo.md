# 节点对接第一阶段任务

- [x] 节点/令牌数据库迁移与原子消费
  - Acceptance: 原文不落库，并发、过期、撤销和 IP 绑定失败关闭。
  - Verify: `python3 -m unittest tests.test_node_onboarding.NodeEnrollmentDatabaseTests -v`
  - Files: `hysteria2_panel.py`, `hy2panel/nodes.py`, `tests/test_node_onboarding.py`

- [x] 管理员与 Agent HTTP 合同
  - Acceptance: 管理接口有会话/CSRF；注册只在 HTTPS 配置开放且返回稳定 JSON。
  - Verify: `python3 -m unittest tests.test_panel.PanelHttpTests -v`
  - Files: `hysteria2_panel.py`, `tests/test_panel.py`

- [ ] 对接按钮、弹窗和状态列表
  - Acceptance: 可生成、复制、撤销；桌面和手机布局可用。
  - Verify: 面板 HTML 合同测试与真实浏览器 320/768/1440px。
  - Files: `hysteria2_panel.py`, `hy2panel/web_assets.py`, `tests/test_panel.py`

- [ ] Agent 与受签名安装模式
  - Acceptance: 只安装 Agent、本地密钥和待验证状态，不安装 Hysteria 或修改网络。
  - Verify: `python3 -m unittest tests.test_node_onboarding tests.test_installer -v`
  - Files: `node_agent.py`, `install.sh`, `tests/test_node_onboarding.py`, `tests/test_installer.py`

- [ ] 全量质量门和身份不变量复审
  - Acceptance: 全部质量门通过，diff 不含 Hysteria 身份和 DNS 写路径。
  - Verify: 规格中的全量命令与 `git diff --check`。
  - Files: 全部本阶段改动。

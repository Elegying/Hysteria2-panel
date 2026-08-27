# 节点控制第二阶段任务

- [x] 节点验证与心跳防重放数据合同
  - Acceptance: 指纹核验、时间窗、IP、nonce 唯一和撤销失败关闭。
  - Verify: `python3 -m unittest tests.test_node_control.NodeControlDatabaseTests -v`
  - Files: `hysteria2_panel.py`, `hy2panel/nodes.py`, `tests/test_node_control.py`

- [x] 管理员验证与签名心跳 HTTP 合同
  - Acceptance: 管理接口有会话/CSRF；心跳 HTTPS-only、限长且错误稳定。
  - Verify: `python3 -m unittest tests.test_node_control tests.test_panel -v`
  - Files: `hysteria2_panel.py`, `tests/test_panel.py`

- [x] 节点验证与在线状态 UI
  - Acceptance: 展示指纹、验证/撤销操作和在线/离线状态，布局可用。
  - Verify: 面板 HTML 合同测试与真实浏览器 320/768/1440px。
  - Files: `hysteria2_panel.py`, `hy2panel/web_assets.py`, `tests/test_panel.py`

- [x] Agent 心跳与隔离激活模式
  - Acceptance: Ed25519 签名心跳和 timer 可用，仍不安装 Hysteria 或修改网络。
  - Verify: `python3 -m unittest tests.test_node_control tests.test_installer -v`
  - Files: `node_agent.py`, `install.sh`, `tests/test_node_control.py`, `tests/test_installer.py`

- [ ] 全量质量门、正式发布与真实服务器验收
  - Acceptance: 全部 CI/签名门通过，新服务器心跳在线且身份不变量保持。
  - Verify: 规格中的全量命令、GitHub 门禁和双服务器实时检查。
  - Files: 全部本阶段改动。

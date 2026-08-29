# v0.32.0 节点运营任务

- [x] 月度预算数据库与模型
  - Acceptance: 本机/远端、幂等、跨日、重置和历史不回填全部正确。
  - Verify: `python3 -m unittest tests.test_node_operations.NodeBudgetTests -v`
  - Files: `hysteria2_panel.py`, `tests/test_node_operations.py`

- [x] 节点生命周期和固定 STOP/START 命令
  - Acceptance: 安全停用门禁失败关闭；Agent/spool/身份保留；恢复可收敛。
  - Verify: `python3 -m unittest tests.test_node_operations.NodeLifecycleTests -v`
  - Files: `hysteria2_panel.py`, `node_agent.py`, `tests/test_node_operations.py`

- [x] 每日 HTTPS WebDAV 异地备份
  - Acceptance: 未配置可见；上传原子；仅精确删除超过 30 天的本项目文件。
  - Verify: `python3 -m unittest tests.test_offsite_backup -v`
  - Files: `offsite_backup.py`, `install.sh`, `tests/test_offsite_backup.py`, `tests/test_installer.py`

- [x] 节点运营向导和预算 UI
  - Acceptance: 对接/停用均有 1-2-3-4；320/768/1024/1440 无溢出；危险操作文案准确。
  - Verify: `python3 -m unittest tests.test_panel.PanelHttpTests -v` 加浏览器验收。
  - Files: `hysteria2_panel.py`, `hy2panel/web_assets.py`, `tests/test_panel.py`

- [ ] 文档、版本、全量门禁和发布部署
  - Acceptance: 一键安装/升级/恢复覆盖新能力；签名发布；生产身份与用户配置不变。
  - Verify: 仓库质量门、CI、Release 验签、真实控制面和数据面验收。
  - Files: `README.md`, `docs/API.md`, `docs/DEPLOYMENT.md`, `CHANGELOG.md`, `hy2panel/version.py`

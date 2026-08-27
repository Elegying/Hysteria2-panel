# 分布式中央认证与计量第三阶段任务

- [x] 通用签名信封与参与状态
  - Acceptance: 每类请求域分离签名；nonce 原子消费；standby/revoked/IP/时间窗失败关闭。
  - Verify: `python3 -m unittest tests.test_distributed_control.SignedNodeRequestTests -v`
  - Dependencies: 无
  - Files: `hy2panel/nodes.py`, `hysteria2_panel.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] 完整在线快照
  - Acceptance: sequence 单调、完整替换、稀疏计数及在线/流量 ACK 的 5 秒 freshness 正确。
  - Verify: `python3 -m unittest tests.test_distributed_control.OnlineSnapshotTests -v`
  - Dependencies: 通用签名信封与参与状态
  - Files: `hysteria2_panel.py`, `hy2panel/nodes.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] 跨节点认证租约
  - Acceptance: 两节点四并发/限额三恰好三次允许；重复 requestId 不重复占位。
  - Verify: `python3 -m unittest tests.test_distributed_control.DistributedAuthorizationTests -v`
  - Dependencies: 完整在线快照
  - Files: `hysteria2_panel.py`, `hy2panel/distributed.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] 中央认证接口与回环代理
  - Acceptance: 标准 Hysteria JSON 可代理；中央异常一律映射为 HTTP 200 拒绝；token 不落盘。
  - Verify: `python3 -m unittest tests.test_distributed_control.NodeAgentProtocolTests tests.test_panel -v`
  - Dependencies: 跨节点认证租约
  - Files: `hysteria2_panel.py`, `node_agent.py`, `hy2panel/distributed.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] durable 流量批次
  - Acceptance: clear 后先 fsync spool；`(node_id,batch_id)` 只累计一次；ACK 前不删除。
  - Verify: `python3 -m unittest tests.test_distributed_control.DistributedTrafficTests -v`
  - Dependencies: 通用签名信封与参与状态
  - Files: `hysteria2_panel.py`, `node_agent.py`, `hy2panel/distributed.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] 固定命令队列与 ACK
  - Acceptance: 只执行三种枚举；KICK_USERS 幂等；任意 shell/路径/URL 参数被拒绝。
  - Verify: `python3 -m unittest tests.test_distributed_control.NodeCommandTests -v`
  - Dependencies: durable 流量批次
  - Files: `hysteria2_panel.py`, `node_agent.py`, `hy2panel/distributed.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] 协议状态 UI 与健康度
  - Acceptance: standby/protocol-ready、快照新鲜度、spool/命令状态可见且无秘密。
  - Verify: `python3 -m unittest tests.test_panel tests.test_distributed_control -v` + 320/768/1440px 浏览器
  - Dependencies: 中央认证接口、durable 流量批次、固定命令
  - Files: `hysteria2_panel.py`, `hy2panel/web_assets.py`, `tests/test_panel.py`, `tests/test_distributed_control.py`
  - Scope: Medium

- [x] 全量门禁与双节点合成验收
  - Acceptance: 全部测试和静态门通过；身份不变量不变；无数据面/DNS/网络写入。
  - Verify: 规格全量命令、故障注入矩阵、`git diff --check`
  - Dependencies: 全部任务
  - Files: 本阶段改动
  - Scope: Medium

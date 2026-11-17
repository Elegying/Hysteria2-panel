# Android 改版接口准备情况

审查日期：2026-11-17。范围：当前工作区代码；本轮新增接口尚未发布、未部署线上，也未改动 Android 界面。

## 覆盖范围

v0.39.58 为网页管理操作提供对应 Bearer API；原有 Android 页面继续兼容，新功能的 Android 界面尚待后续改版。接口覆盖不等于客户端已经实现全部页面。先读取 capabilities，再按能力显示入口。

| 网页功能 | 移动 API（统一前缀 `/api/v1/mobile`） |
| --- | --- |
| 登录、会话、用户增删改、额度、有效期、启停、身份重置 | 原有 auth、sessions、users 接口 |
| 总览、排行榜、用户日/小时流量和域名统计 | 原有 overview、用户 usage/domain 接口 |
| 服务器资源、近期和今日速率、检测结果 | GET server-monitor、line-monitor |
| 本机服务启停/重启、整机重启 | 原有 system 接口 |
| 节点对接、撤销对接码、断连、删除对接 | 原有 enrollments/nodes 接口 |
| 预算修改、手动检测 | POST usage-origins/{originId}/budget、diagnostics |
| 远端服务重启、整机重启 | POST nodes/{nodeId}/operations/restart、reboot |
| 专线配置、兼容生命周期与数据面操作 | nodes/{nodeId}/line-config、verify、revoke、protocol、lifecycle、data-plane |
| 订阅列表、默认/用户节点、启停、删除、重置 | GET subscriptions；POST subscriptions/defaults、{id}/nodes、{id}/{action}；原有用户 subscription 接口 |
| 外部节点读取、预览、发布 | GET/POST subscriptions/external、POST subscriptions/external/preview |
| 本机端口跳跃、出站策略 | POST port-hopping/{enable,disable}、egress/{web,full} |
| 批量流量清零、删除未归属历史 | POST users/reset-traffic、usage-origins/legacy-unattributed/delete |
| BBR/证书/备份状态、检查和应用更新 | 原有 overview 加 GET settings；POST updates/check、updates/apply |
| 下载备份、上传恢复 | POST backup、restore（流式 ZIP） |

证书与 BBR 对齐网页的状态展示能力；不新增网页没有的静默证书轮换或任意 shell 执行。设置端口是下发订阅配置，不能假定会修改远端监听。检测仍仅手动发起，TCP 成功不能证明国内 UDP 可用。

新增写接口契约见 [移动管理 API](MOBILE_ADMIN_API.md)。

## 新增只读接口

全部要求 `Authorization: Bearer <accessToken>`，返回现有 `data / meta / error` envelope。未登录 HTTP 401；不接受网页会话作为移动认证。新接口不触发外部探测。

### `GET /api/v1/mobile/server-monitor`

能力标识：`server-resource-monitor`。

`data.local`：本机 `cpu`、`memory`、`disk` 百分比，`memoryUsed / memoryTotal / diskUsed / diskTotal` 字节，`uptimeLabel`，`fresh`，`observedAt`。

`data.servers`：以 nodeId 为键的远端样本。同样包含百分比及字节容量；`uptime` 为秒。新 Agent 未上报、失联或撤销时可能缺少条目，不能假定每个节点都有样本。

`data.operations`：各节点最近一次运维任务的 `kind / created_at / acked_at / last_error`。ACK 表示执行安排已被确认，不等于机器已重启并恢复在线。错误和超时必须独立展示。`SESSIONS_NOT_DRAINED` 表示连接未排空，操作已拒绝、服务保持运行；旧 Agent 可能仍返回通用 `EXECUTION_FAILED`。

### `GET /api/v1/mobile/line-monitor?range=5m|today`

能力标识：`network-history-today`、`line-diagnostics-read`。

与网页共享同一读模型：`data.network` 是近期网卡速率样本，`data.checks` 是已有检测结果；`range=today` 额外返回 `data.today`。默认 `5m`。非法或重复范围参数返回 HTTP 400 / `RANGE_INVALID`。

`network[originId]` 包含 `fresh / observedAt / rx / tx / points`；每个 point 是 `{at, rx, tx}`。`at` 为 Unix 秒（可带小数），`rx/tx` 为**字节/秒**，显示 Mbps 时乘 8 再除以 1,000,000。`null` 是缺测，不是 0。近期接口最多返回约 15 分钟缓存，近 5 分钟视图由客户端裁剪到最后 300 秒。

`today` 包含 `start / end / step=60 / network`，其 `network[originId].points` 为分钟采样平均速率，不是该分钟流量总字节。

按 `originId` 对齐节点（本机 `local:…`，远端 `node:…`），不要用名称或 IP 当主键。计数器重置、重启 epoch 变化和缺测应断线，不平滑伪造数据；今日统计按北京时间，未采集的历史不能补成 0。

## 后续客户端组织建议

- API 路径、请求与响应类型放在独立 service/model 文件，屏幕只处理交互和状态；当前大量 `Map<String, dynamic>` 与字符串路径散落在页面中。
- 保留 AppController 的会话刷新、迟到请求隔离、凭据安全存储逻辑，不能为了重构删掉现有回归测试。
- 先完成只读总览和节点监控，再逐类增加写操作。每个能力同时有路由、鉴权、参数校验、服务层、错误码、capabilities 和客户端回归才算完成。
- 首次改版验收应包括真机后台恢复、网络中断、会话过期、账号切换、大字体及原签名覆盖安装。当前 Flutter 测试不替代真机验收。

# 移动管理 API（v0.39.58）

所有路径均以 `/api/v1/mobile` 开头。要求 `Authorization: Bearer <accessToken>`，不接受浏览器 Cookie。除文件接口外，POST 使用 JSON 对象；拒绝未知字段，返回现有 `data/meta/error` envelope。鉴权失败 401，参数错误 400，状态冲突 409，维护期间写入 503。写请求不可自动重放。

## 读取

- `GET /settings`：证书、出站策略、端口跳跃、更新、异地备份状态与备份恢复能力。不会返回私钥或异地存储凭据。
- `GET /budgets`：有效机器来源预算列表。`originId` 为 `local:32hex` 或 `node:32hex`。
- `GET /subscriptions`：订阅元数据列表；完整订阅使用原有 `GET /users/{id}/subscription`，不要把 token 写入日志。
- `GET /subscriptions/defaults`：默认节点和本机端口跳跃状态。
- `GET /subscriptions/external`：revision 与脱敏节点列表，不返回外部节点认证 URI。
- 资源和图表见 [Android API 准备情况](ANDROID_API_READINESS.md)。

## 配置与流量

| POST 路径 | JSON 字段 |
| --- | --- |
| `/usage-origins/{originId}/budget` | `limitGiB` 整数、`warningPercent` 整数；可选且成对 `usedGiB` 十进制字符串、`resetDay` 整数 |
| `/usage-origins/{originId}/diagnostics` | `{}`；202 已受理，409 冷却/已有任务 |
| `/subscriptions/defaults` | `nodes` 数组，不能为空 |
| `/subscriptions/{id}/nodes` | `nodes` 数组；空数组恢复继承 |
| `/subscriptions/{id}/{enable,disable,delete,regenerate}` | `confirm` 为订阅 ID 的十进制字符串；regenerate 会改变凭据 |
| `/subscriptions/external`、`/subscriptions/external/preview` | `revision` 整数、`nodes` 数组；陈旧 revision 返回 409；preview 不写入 |
| `/port-hopping/{enable,disable}` | `confirm: "LOCAL_NODE"`，仅本机 |
| `/egress/{web,full}` | `confirm: "LOCAL_NODE"`，经维护和结算后切换 |
| `/users/reset-traffic` | `confirm: "RESET_TRAFFIC"`、`group: "standard" / "premium" / "all"` |
| `/usage-origins/legacy-unattributed/delete` | `confirm: "DELETE_UNATTRIBUTED"` |

订阅节点项为 `label/host/port/pin_sha256/enabled`，可选 `node_id`；port 必须为 JSON 整数、enabled 必须为布尔值。外部节点项为 `label/enabled/uri`，已有节点可传 `id` 并留空 uri 保留凭据；不能依赖脱敏列表重建 URI。默认节点变更不改变订阅链接，但客户端须刷新订阅才取得新配置。

## 节点运维

下列路径均为 `/nodes/{nodeId}/…`，nodeId 为 32 位小写十六进制。除特别说明外传 `{"confirm":"目标 nodeId"}`。

- `operations/restart`、`operations/reboot`：要求新鲜资源上报，返回 202 与 commandId；只允许固定操作，不接受命令字符串。使用 server-monitor 查询 ACK、错误和恢复在线情况，202 不代表执行完成。
- `line-config`：仅传 `label/host/port`；沿用专线配置限制。
- `verify`：仅传 `fingerprint`（64 位小写十六进制），沿用节点指纹核验。
- `revoke`、`protocol/enable`、`protocol/disable`：沿用数据库状态门禁。
- `lifecycle/{drain,stop,emergency-stop,resume,archive,budget-dns-removed}`：兼容生命周期；正常停止核查 DNS 已摘除，紧急停止显式确认。
- `data-plane/bootstrap`：要求 HTTPS，返回 201。部署凭据敏感，禁止日志记录。
- `data-plane/canary/pass`、`data-plane/dns/{admit,remove}`：沿用原有数据面门禁。

远端排空失败的 `SESSIONS_NOT_DRAINED` 表示操作取消、服务保持运行。旧 Agent 可能仅上报 `EXECUTION_FAILED`。断连和删除对接继续使用原有节点接口。

## 更新和文件

`POST /updates/check {}` 返回检查结果。`POST /updates/apply` 传 `confirm: "UPDATE_PANEL"` 与 `target`（刚检查得到的 latest）；仅检查到可用版本才可排队，返回 202。更新状态沿用原有接口。存在不支持升级的外部节点状态时拒绝；不绕过签名校验。

`POST /backup {}` 成功返回 `application/zip` 二进制，失败返回 JSON。保存到受保护目录，勿写入应用日志。

`POST /restore` 使用 `Content-Type: application/zip`、准确 `Content-Length`、`X-HY2Panel-Confirm: RESTORE`，body 为原始 ZIP，不是 multipart 或 base64。沿用网页流式大小/完整性/身份预检和维护互斥，受理返回 202 JSON；恢复完成会使旧会话失效，需要重新登录。受理不等于恢复完成。

## 客户端验收边界

现有 Android 继续通过原有接口工作。新增能力应在后续界面改版中补充类型化模型、确认对话框、错误状态、文件安全保存和真机覆盖安装测试。服务端 HTTP 契约测试不替代 Android 真机验收。

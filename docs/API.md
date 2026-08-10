# HTTP 接口契约

## Hysteria 认证回调

监听：`127.0.0.1:19996`，不对公网开放。

### `POST /auth`

请求由 Hysteria 发出：

```json
{
  "addr": "192.0.2.10:44556",
  "auth": "客户端认证密钥",
  "tx": 123456
}
```

认证成功：

```json
{"ok": true, "id": "用户名称"}
```

认证失败仍返回 HTTP 200，以符合 Hysteria 的认证契约：

```json
{"ok": false, "id": ""}
```

无效 JSON、缺少 `auth` 或请求过大时返回结构化错误：

```json
{"error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}
```

参考：[Hysteria 2 官方 HTTP Authentication 文档](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#http-authentication)。

## 管理面板

监听：公网 TCP `19998`，默认 HTTPS，也可在安装时明确选择 HTTP。所有变更路由均要求有效管理会话和 CSRF token。

| 方法 | 路径 | 行为 |
|---|---|---|
| `GET` | `/healthz` | 无敏感信息的服务健康检查 |
| `GET` | `/login` | 登录页 |
| `POST` | `/login` | 创建 HttpOnly、SameSite=Strict 会话；HTTPS 模式额外设置 Secure |
| `GET` | `/` | 服务状态、全局统计、分页用户列表、在线设备与流量 |
| `POST` | `/users` | 创建用户并仅一次显示认证密钥和 URI |
| `POST` | `/users/{id}/toggle` | 携带当前 `generation`，启用或禁用用户 |
| `POST` | `/users/{id}/rotate` | 携带当前 `generation`，轮换认证密钥并断开旧连接 |
| `POST` | `/users/{id}/delete` | 携带当前 `generation`，删除用户并断开连接 |
| `POST` | `/logout` | 撤销管理会话 |

面板没有对公网提供通用 JSON 管理 API，避免扩大认证和 CORS 攻击面。
版本过期的用户变更返回 HTTP 409，避免并发操作覆盖刚生成的认证密钥。审计写入或断开在线连接失败会记录到服务日志，但不会吞掉已经生成且只显示一次的新凭据。

全局统计只汇总当前数据库中的用户，避免已删除用户仍残留在 Hysteria 统计快照时污染总数。不活跃用户定义为上传和下载均为 0 的账户；Hysteria 重启后其内存流量计数会重新开始。

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

认证成功前会同步持久流量并检查该用户的总流量和客户端实例上限。Hysteria `/online` 的数值是同一认证 ID 的客户端实例数，不是代理流数量或物理硬件指纹。达到任一上限或本地统计接口暂时不可用时，仍使用上述 HTTP 200 拒绝响应，避免绕过限额或改变 Hysteria 的认证契约；超过上限不会踢掉已在线实例。

无效 JSON、缺少 `auth` 或请求过大时返回结构化错误：

```json
{"error": {"code": "INVALID_REQUEST", "message": "Invalid request"}}
```

参考：[Hysteria 2 官方 HTTP Authentication 文档](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#http-authentication)。

## 管理面板

监听：公网 TCP `19998`，默认 HTTP，也可在安装时明确选择 HTTPS。所有变更路由均要求有效管理会话和 CSRF token。

| 方法 | 路径 | 行为 |
|---|---|---|
| `GET` | `/healthz` | 无敏感信息的服务健康检查 |
| `GET` | `/login` | 登录页 |
| `POST` | `/login` | 创建 HttpOnly、SameSite=Strict 会话；HTTPS 模式额外设置 Secure；按来源 IP 执行登录限速 |
| `GET` | `/` | 服务控制、系统资源、版本、全局统计、高流量前五、完整用户列表、即时搜索与限额进度 |
| `POST` | `/users` | 创建带设备/总流量限制的用户并显示认证密钥和 URI |
| `POST` | `/users/{id}/toggle` | 携带当前 `generation`，启用或禁用用户 |
| `POST` | `/users/{id}/rotate` | 携带当前 `generation`，轮换认证密钥并断开旧连接 |
| `POST` | `/users/{id}/delete` | 携带当前 `generation`，删除用户并断开连接 |
| `POST` | `/users/{id}/share` | 携带当前 `generation`，显示可复制的当前连接 URI |
| `POST` | `/users/{id}/reset` | 携带当前 `generation`，重置该用户流量并断开旧连接 |
| `POST` | `/users/reset-traffic` | 重置所有用户的持久累计流量 |
| `POST` | `/service/{start,stop,restart}` | 通过固定 sudoers 白名单控制项目专用 Hysteria 服务 |
| `POST` | `/updates/check` | 从固定 GitHub Release API 检查面板版本，不自动安装 |
| `POST` | `/backup` | 表单 CSRF 校验后返回 `application/zip` 敏感备份，响应强制 `no-store` |
| `POST` | `/restore` | 上传原始 `application/zip`；CSRF 通过 `X-HY2Panel-CSRF` 请求头提交，预检后排队执行一次性恢复服务 |
| `POST` | `/logout` | 撤销管理会话 |

面板没有对公网提供通用 JSON 管理 API，避免扩大认证和 CORS 攻击面。
版本过期的用户变更返回 HTTP 409，避免并发操作覆盖刚生成的认证密钥。审计写入或断开在线连接失败会记录到服务日志，但不会吞掉已经生成的新凭据。

登录错误响应不区分账号不存在与密码错误。每个来源 IP 在 15 分钟窗口内前 4 次错误返回 HTTP `401`，第 5 次立即返回 HTTP `429` 并设置整数秒 `Retry-After`；锁定期间正确密码也会被拒绝。成功登录清除该来源的失败记录。限速表最多记录 4096 个来源并仅保存在进程内存，面板重启后清空，避免给 SQLite 增加高频攻击写入。所有登录响应均带 `no-store`、CSP、`nosniff`、拒绝嵌入和禁止 Referrer 等安全头。

全局统计只汇总当前数据库中的用户，避免已删除用户仍残留在 Hysteria 统计快照时污染总数。不活跃用户定义为上传和下载均为 0 的账户。面板定期使用 Hysteria `/traffic?clear=true` 原子取得增量并写入 SQLite，因此正常重启不会清空累计流量。

`POST /restore` 要求 `Content-Length` 在 1 字节到 64 MiB 之间，不解析 multipart。服务端只接受格式版本 1 的固定五文件 ZIP，限制单项与总解压大小，拒绝额外文件、重复路径、目录和符号链接，并校验清单 SHA-256、SQLite 完整性/表结构、每个可恢复用户 token、证书/私钥、证书指纹、源域名及 UDP 端口。上传预检通过后只写入固定的待恢复路径，再用固定 sudoers 命令启动 root oneshot；root 进程会重复全部校验。

Hysteria 流量统计客户端只接受带明确端口、无路径的 `http://127.0.0.1` 或 `http://[::1]`，单次响应最多 8 MiB，避免配置错误把面板变成外部请求入口或让异常统计响应无限占用内存。

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

### `POST /auth/udp-443`

仅供本机 UDP `443` Hysteria 进程调用，请求和响应结构与 `/auth` 相同。除了启用状态、流量和客户端实例限制外，还要求账号的 `allow_udp_443` 为真；未开放的账号返回 HTTP 200 与 `{"ok": false, "id": ""}`。主端口认证不检查该字段，因此开放 UDP `443` 不会停止原端口。

## 管理面板

监听：公网 TCP `19998`，默认 HTTP，也可在安装时明确选择 HTTPS。所有变更路由均要求有效管理会话和 CSRF token。

| 方法 | 路径 | 行为 |
|---|---|---|
| `GET` | `/healthz` | 仅表示 HTTP 进程存活；返回固定的 `{"status":"ok"}` |
| `GET` | `/readyz` | 数据库、内部认证、流量采集工作线程和最近统计同步均正常时返回 200，否则返回 503；不暴露内部故障细节 |
| `GET` | `/metrics` | 仅回环来源可访问的有界 Prometheus 文本指标；外部来源返回 404，不包含用户名或来源 IP 标签 |
| `GET` | `/login` | 登录页 |
| `POST` | `/login` | 创建 HttpOnly、SameSite=Strict 会话；HTTPS 模式额外设置 Secure；按来源 IP 执行登录限速 |
| `GET` | `/` | 服务控制、系统资源、版本、全局统计、高流量前五、完整用户列表、即时搜索与限额进度 |
| `POST` | `/users` | 创建带设备/总流量限制的用户并显示认证密钥和 URI |
| `POST` | `/users/{id}/edit` | 携带当前 `generation`，修改客户端实例数、总流量限制和账号级 UDP 443 权限，不修改 token 或 URI |
| `POST` | `/users/{id}/toggle` | 携带当前 `generation`，启用或禁用用户 |
| `POST` | `/users/{id}/rotate` | 携带当前 `generation`，轮换认证密钥并断开旧连接 |
| `POST` | `/users/{id}/delete` | 携带当前 `generation`，删除用户并断开连接 |
| `POST` | `/users/{id}/share` | 携带当前 `generation`，显示可复制的当前连接 URI |
| `POST` | `/users/{id}/reset` | 携带当前 `generation`，重置该用户流量并断开旧连接 |
| `POST` | `/users/reset-traffic` | 重置所有用户的持久累计流量 |
| `POST` | `/service/{start,stop,restart}` | 通过固定 sudoers 白名单控制项目专用 Hysteria 服务 |
| `POST` | `/system/reboot` | 二次确认后通过固定 sudoers 白名单排队重启整台服务器，成功返回 HTTP 202 |
| `POST` | `/updates/check` | 从固定 GitHub Release API 检查面板版本；有新正式版本时显示在线更新入口 |
| `POST` | `/updates/apply` | 不接收版本或地址参数；排队启动固定的一次性 root 更新服务，成功返回 HTTP 202 |
| `GET` | `/updates/status` | 查询持久更新状态；返回 `idle/queued/running/success/failed` 与目标版本和提示 |
| `POST` | `/backup` | 表单 CSRF 校验后返回 `application/zip` 敏感备份，响应强制 `no-store` |
| `POST` | `/restore` | 上传原始 `application/zip`；CSRF 通过 `X-HY2Panel-CSRF` 请求头提交，预检后排队执行一次性恢复服务 |
| `POST` | `/logout` | 撤销管理会话 |

面板没有对公网提供通用 JSON 管理 API，避免扩大认证和 CORS 攻击面。
版本过期的用户变更返回 HTTP 409，避免并发操作覆盖刚生成的认证密钥。编辑用户时设备限制范围为 1 到 100，总流量必须为正值，`allow_udp_443=1` 表示开放 UDP `443`，缺少该字段表示关闭；该操作递增 `generation`，保留名称、认证 token 派生种子和累计流量。审计写入或断开在线连接失败会记录到服务日志，但不会吞掉已经生成的新凭据。

登录错误响应不区分账号不存在与密码错误。每个来源 IP 在 15 分钟窗口内前 4 次错误返回 HTTP `401`，第 5 次立即返回 HTTP `429` 并设置整数秒 `Retry-After`；同一 IPv6 `/64` 前缀按一个来源统计。锁定期间正确密码也会被拒绝，成功登录清除该来源的失败记录。限速表最多记录 4096 个来源并仅保存在进程内存，面板重启后清空。所有登录响应均带 `no-store`、CSP、`nosniff`、拒绝嵌入和禁止 Referrer 等安全头。

公网 HTTP 连接具有 10 秒读写空闲超时和 30 秒请求总截止时间；总截止时间到期会关闭连接并释放工作线程。`audit_log` 每次写入后在同一事务中删除超过 90 天的记录，并只保留最新 10,000 行，避免未认证登录失败无限扩张 SQLite。

全局统计只汇总当前数据库中的用户，避免已删除用户仍残留在 Hysteria 统计快照时污染总数。不活跃用户定义为上传和下载均为 0 的账户。面板分别从主入口和 UDP `443` 入口使用 Hysteria `/traffic?clear=1` 取得增量，按用户名相加后写入 SQLite；`/online` 实例数也按用户名相加，因此两个入口共同执行同一设备与流量额度，正常重启不会清空累计流量。

`POST /restore` 要求 `Content-Length` 在 1 字节到 64 MiB 之间，不解析 multipart。服务端只接受格式版本 1 的固定五文件 ZIP，限制单项与总解压大小，拒绝额外文件、重复路径、目录和符号链接，并校验清单 SHA-256、SQLite 完整性/表结构、每个可恢复用户 token、证书/私钥、证书指纹、源域名及 UDP 端口。上传预检还必须在安装/更新/恢复共用锁文件上取得短暂只读共享准入；root 维护任务持排他锁或已有恢复标记时拒绝上传。预检通过后只写入固定待恢复路径，再用固定 sudoers 命令启动 root oneshot。

root 进程不信任 Web 预检，会以 `O_NOFOLLOW` 和固定所有权/权限合同再次读取归档，并把恢复推进为持久的 `queued → prepared → disk-consistent → services-pending` 事务。启动前的 `restore-recover` oneshot 只验证、完成或回滚数据库/HMAC 环境/TLS 身份并清理 SQLite sidecar；业务服务强依赖该阶段成功。服务启动后的 `restore-resume` oneshot 连续验证 systemd、HTTP、统计和 TCP 健康后才删除标记。普通退出、信号或重启均从标记幂等继续；孤立或失败归档会隔离并释放固定上传路径。

`POST /updates/apply` 只有在当前会话刚检查到新版本时可用，但 root 任务不会信任这份页面状态，而会重新访问固定仓库的 GitHub `releases/latest`。响应 tag 必须是比当前版本新的 `vX.Y.Z`，安装器只能从该 tag 对应的固定 `raw.githubusercontent.com/Elegying/Hysteria2-panel/` 路径下载。执行前还会限制响应大小、验证 UTF-8、bash 解释器头、内嵌版本与 tag 一致并通过 `bash -n`。更新进程使用固定环境变量进入安装器的现有受管安装模式，网页请求无法指定命令、仓库、版本、节点参数或管理员凭据。排队状态以 `0600` 原子文件保存在面板数据目录；`GET /updates/status` 再读取固定 systemd 单元状态，且只有更新单元已成功结束并且当前版本达到目标版本才返回 `success`。浏览器短暂失联时继续轮询，任务失败、退出码非零或任务结束但版本未变化时返回明确失败提示。

`POST /system/reboot` 不接收命令、主机或延时参数。后端只执行固定的 `/usr/bin/sudo -n /bin/systemctl --no-block reboot`，并在排队前尽力落盘最新流量及写入审计记录。接口返回 202 只表示重启已排队，不表示系统已重新上线。

Hysteria 流量统计客户端只接受带明确端口、无路径的 `http://127.0.0.1` 或 `http://[::1]`，单次响应最多 8 MiB，避免配置错误把面板变成外部请求入口或让异常统计响应无限占用内存。

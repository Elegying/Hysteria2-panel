# 备份与迁移

完整备份可以在新服务器恢复用户连接所需的身份，因此应把它当作高敏感凭据，而不是普通报表。

## 备份包含什么

面板下载的 ZIP 包含：

- 一致性的 `panel.db` 用户与流量快照；
- 派生用户认证身份所需的 HMAC 签名密钥；
- Hysteria TLS 证书和私钥；
- 源节点域名、UDP 端口、节点名、证书指纹与有效期；
- 每个文件的 SHA-256 清单。

备份不包含：

- 旧服务器管理员密码哈希；
- 管理员会话；
- 审计日志；
- 统计 API secret；
- 面板端口和协议；
- WebDAV 目标地址、账号或密码。

恢复会整体替换新服务器上的代理用户数据；新服务器恢复前临时创建的代理用户会被移除。新服务器当前管理员账号仍会保留。

## 下载与保管

在顶部打开“数据迁移”，选择下载完整备份。下载完成后：

1. 将文件保存到加密磁盘或离线介质；
2. 不要上传到公开网盘、Issue、聊天群或工单附件；
3. 至少保留一份与生产服务器分离的副本；
4. 定期在隔离环境验证备份可读，而不是等故障后第一次测试。

如果面板明确使用 HTTP，下载和上传过程没有传输层加密，只能在可信网络中操作。生产环境应优先使用 HTTPS。

## 迁移中央面板

目标是保留现有 Hysteria 用户 URI。迁移顺序很重要：

1. **旧服务器下载备份**：不要立即删除或停机；
2. **准备新面板域名**：为新服务器使用独立 `PANEL_PUBLIC_HOST`，先配置 DNS，并放行 TCP `80` 与面板端口；
3. **部署新服务器**：使用与旧节点相同的 Hysteria `PUBLIC_HOST` 和 `HYSTERIA_PORT`，但使用新的面板域名；
4. **暂不切用户 DNS**：用户使用的 Hysteria 域名仍指向旧服务器；
5. **上传恢复 ZIP**：新面板会先进行大小、结构、哈希、数据库、证书、域名和端口检查；
6. **等待恢复完成**：root 恢复任务会再次验证，并以持久事务完成或回滚；
7. **检查身份**：核对用户数、累计流量、证书指纹、主端口和 UDP `443`；
8. **接入额外节点**：需要时在恢复后再生成全新节点对接或安全重绑定命令；
9. **切换用户 DNS**：用旧客户端配置完成真实握手、网页、视频、设备数和流量测试；
10. **保留回退窗口**：至少等待一个 DNS TTL 和一段稳定观察期，再停用旧服务器。

恢复会拒绝源 `PUBLIC_HOST` 或 Hysteria UDP 端口与当前部署不一致的 ZIP。使用域名时可以只修改 DNS；如果旧 URI 直接写入旧服务器 IP，或迁移时必须改端口，就无法做到无感迁移，需要重新分享配置。

## 恢复过程的安全设计

上传接口只接受 1 字节到 64 MiB 的原始 ZIP，不解析 multipart。预检会拒绝：

- 额外文件、重复路径、目录或符号链接；
- 单项或总解压大小超限；
- 清单或文件 SHA-256 不一致；
- SQLite 不完整或表结构不兼容；
- 用户 token 无效；
- 证书、私钥或指纹不匹配；
- 源域名或 UDP 端口与新部署不一致；
- 维护锁已被安装、更新、恢复或续期任务占用。

Web 层通过预检后，只会把归档放到固定待恢复路径并启动固定 systemd 任务。root 任务不会信任 Web 预检，会使用固定所有权和权限合同再次读取并验证。

恢复事务会经历 `queued → prepared → disk-consistent → services-pending`。主机重启或进程中断后，前置和后置恢复服务会从持久标记继续。不要手工删除标记或只替换数据库。

## 每日 WebDAV 异地备份

安装器会启用 `hysteria2-panel-offsite-backup.timer`。若要上传到 HTTPS WebDAV，请在服务器创建 root-only 配置：

```bash
install -o root -g root -m 0600 /dev/null /etc/hysteria2-panel/offsite-backup.json
editor /etc/hysteria2-panel/offsite-backup.json
systemctl start hysteria2-panel-offsite-backup.service
systemctl status hysteria2-panel-offsite-backup.service hysteria2-panel-offsite-backup.timer
```

配置格式：

```json
{
  "endpoint": "https://backup.example.com/hysteria2-panel/",
  "username": "专用备份账号",
  "password": "专用备份密码"
}
```

要求：

- `endpoint` 必须以 `/` 结尾；
- 只能使用 HTTPS；
- URL 不能包含账号、查询参数或片段；
- 文件必须保持 `root:root 0600`；
- 应使用权限受限的专用 WebDAV 账号。

任务会以临时名称上传、验证远端尺寸，再通过原子 MOVE 生效。只删除超过 30 天且名称精确匹配本项目格式的远端备份。未配置目标时，任务只记录 `not_configured`，不会制造重复本地 ZIP 或误报成功。

异地目标是服务器级秘密，不会进入可迁移 ZIP。迁移到新服务器后，需要重新创建这份配置。

## Hysteria 证书生命周期

节点证书指纹固定在已发放 URI 中。安装器升级和备份恢复会逐字节保留证书与私钥；项目只在 180/90/30 天时告警，不会自动续签或轮换节点证书。

人工更换节点证书会产生新指纹，旧 URI 必须更新并重新分发。操作前应先下载并离线验证完整备份，再安排维护窗口和客户端迁移计划。面板 Let’s Encrypt 证书与 Hysteria 节点证书是两套独立身份，不要混用。

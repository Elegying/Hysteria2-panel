# ADR-001：使用本机 HTTP 认证回调和标准库面板

## 状态

已接受；公网面板缺省协议部分已由 [ADR-005](ADR-005-http-login-network-hardening.md) 更新。

## 日期

2026-08-10

## 背景

项目需要在一台已有代理业务的 Linux 服务器上部署 Hysteria 2，并提供动态多用户管理。关键约束是：

- Hysteria 默认使用 UDP `19999`；
- 新增、禁用和轮换用户不能要求手工改配置；
- 管理密码和用户认证密钥不能进入 Git 仓库；
- Ubuntu 20.04 自带 Python 可直接运行，尽量避免额外依赖；
- 流量与断开连接能力应复用 Hysteria 官方接口。

## 决策

使用 Hysteria 官方 `auth.type: http`，认证回调仅监听 `127.0.0.1:19996`。面板使用 Python 标准库、SQLite 和 systemd。最初决策让公网管理界面缺省使用自签名 TLS；从 v0.10.0 起，缺省协议调整为 HTTP，风险与边界见 ADR-005。Hysteria 官方 Traffic Stats API 仅监听 `127.0.0.1:19997` 并设置随机 secret。

管理员密码使用 scrypt；Python 构建缺少 scrypt 时使用 600,000 次 PBKDF2-HMAC-SHA256。代理用户的随机认证密钥只显示一次，数据库仅保存 HMAC-SHA256 指纹。TLS 证书由 Hysteria 官方 `cert` 命令生成，连接 URI 携带证书固定指纹。

面板与 Hysteria 分别使用 `hy2panel` 和 `hy2server` 系统身份；只有 TLS 证书通过 `hy2tls` 组共享。项目使用独立的 `hysteria2-panel-server.service` 和 `/opt/hysteria2-panel/bin/hysteria`，不覆盖主机上已有的通用 Hysteria 安装。管理请求使用用户记录版本进行乐观并发校验，并对 HTTP 工作线程、连接读取时间和登录限速状态设置边界。

## 备选方案

### Hysteria `userpass` 静态映射

- 优点：无需认证回调服务。
- 缺点：每次用户变更都要重写配置并重启 Hysteria，在线连接和操作一致性较差。
- 结论：不采用。

### 部署通用第三方面板

- 优点：功能多、界面成熟。
- 缺点：依赖和攻击面明显增加，通常同时管理多种协议，超出本项目范围。
- 结论：不采用。

### Flask/Django 面板

- 优点：路由、模板和安全扩展生态完善。
- 缺点：需要额外 Python 运行依赖和供应链维护；当前低并发单管理员场景不需要完整框架。
- 结论：暂不采用；当并发、角色或 API 需求扩大时重新评估。

## 结果

- 用户变更实时生效，不需要重启 Hysteria；
- 运行依赖仅为 Python 标准库、官方 Hysteria 二进制和 systemd；
- 面板适合小规模自用，不承诺多管理员 RBAC、外部数据库或高并发；
- 自签名证书会产生浏览器警告，后续若配置正式域名证书，可保持接口和数据模型不变地替换证书。

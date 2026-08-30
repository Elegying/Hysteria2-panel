# 支持范围

## 提问前

请依次检查：

1. 当前是否为[最新正式版本](https://github.com/Elegying/Hysteria2-panel/releases/latest)；
2. [README](README.md)和[文档中心](docs/README.md)是否已有对应说明；
3. 面板 `/healthz`、`/readyz`、相关 systemd 状态和 journal；
4. 云安全组、DNS、TCP/UDP 端口和真实 Hysteria 客户端握手；
5. 是否有正在运行或未完成的安装、更新、恢复、续期事务。

## 可以提交的问题

- 可复现的安装、升级、恢复或回滚失败；
- 面板功能与文档不一致；
- 最新正式版本中的页面或移动端错误；
- 节点对接、流量统计、设备限制或更新行为异常；
- 清晰、通用且符合项目边界的功能建议。

## 不提供的支持

- 代购、代管或登录你的服务器操作；
- 云厂商账号、安全组、DNS 服务商或 WebDAV 服务本身的故障；
- Hysteria 客户端的第三方 GUI 配置问题；
- 绕过网络、平台、版权或服务商规则；
- 把设备限制改造成硬件授权系统；
- 对某个地区或线路速度作保证；
- 已经自行修改安装器、数据库、systemd 单元或受管文件后的完整兼容承诺。

## 提交诊断信息

创建 Issue 时请提供：

- 面板版本；
- Linux 发行版、版本和架构；
- 安装、升级、恢复还是节点操作；
- 预期结果与实际结果；
- 最小复现步骤；
- 已脱敏的 systemd 状态和相关 journal；
- `/healthz` 与 `/readyz` 的 HTTP 状态；
- 是否使用 HTTPS、UFW/firewalld 和多节点。

不要提交真实域名、服务器 IP、管理员账号、用户 URI、token、私钥、证书私钥、备份、Cookie、CSRF token 或 WebDAV 凭据。

安全漏洞请按[安全政策](SECURITY.md)私密报告。

# ADR-002：可选 HTTP 面板与 QUIC UDP 优化

## 状态

已接受，2026-08-10。

## 背景

部分部署环境无法方便地处理自签名 HTTPS 面板的浏览器警告，同时 Hysteria 使用 QUIC/UDP，高带宽传输可能受 Linux UDP socket 缓冲上限影响。

## 决策

- 面板继续默认使用 HTTPS，但安装器允许用户明确选择 HTTP。
- HTTP 模式不发送 HSTS，也不设置 Secure Cookie；HttpOnly、SameSite=Strict、CSRF、防暴力登录和会话撤销保持启用。
- Hysteria 的 TLS 不受面板协议影响，分享 URI 继续固定服务端证书 SHA-256 指纹。
- 安装器以项目专用 sysctl 文件把 UDP 收发缓冲上限提高到至少 7,500,000 字节；若系统当前值更高则保留更高值。
- Hysteria systemd 服务设置 `LimitNOFILE=1048576`，不修改防火墙，也不启用与 QUIC 无直接关系的内核 TCP 拥塞算法。

## 后果

HTTP 能消除自签名证书访问障碍，但管理员密码和会话会以明文经过网络，因此安装器必须给出明确警告。UDP 优化可跨重启保留，且不会降低服务器已有的更高缓冲值。

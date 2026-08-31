# Hysteria2管理 Android App

这是 Hysteria2-panel 同仓库维护的 Android 管理客户端，applicationId 为 `vip.ssrvpn.hysteria2manager`。

## 当前能力

- 使用面板地址、端口、管理员账号和密码建立独立设备会话；密码不保存，刷新令牌进入 Android 安全存储。
- 底栏包含首页、用户、节点和设置。
- 首页显示服务状态、用户/节点/流量摘要、节点预算、服务控制和系统资源。
- 用户页不分页，支持高流量排行、搜索、筛选、编辑、分享、二维码、启停、改密、流量重置和删除。
- 节点页显示注册、验证、心跳、控制协议、数据面、DNS 准入和命令状态，并支持节点对接和指纹核对。
- 设置页支持退出登录、检查 GitHub APK 更新、主题模式和强调色。

## 本地验证

```bash
cd mobile
flutter pub get
flutter analyze
flutter test
```

## 固定签名构建

正式包必须使用同一密钥。构建机从 `android/signing.properties` 读取密钥位置、别名和密码；该文件已被 Git 忽略。首次配置可参考 `android/signing.properties.example`。

```bash
flutter build apk --release --build-name=0.1.0 --build-number=1
```

每次更新必须同时满足：

1. applicationId 保持 `vip.ssrvpn.hysteria2manager`。
2. 使用同一个发布密钥。
3. `versionCode` 高于已安装版本。
4. APK Release 资产命名为 `Hysteria2-Manager-vX.Y.Z.apk`，App 才能自动发现更新。

发布密钥或密码一旦丢失，将无法覆盖更新已经安装的 App；应把密钥和本地签名配置放入受控的离线备份。

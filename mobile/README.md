# Hysteria2管理 Android App

这是 Hysteria2-panel 同仓库维护的 Android 管理客户端，applicationId 为 `vip.ssrvpn.hysteria2manager`。

## 当前能力

- 首次打开时由用户自行填写面板 HTTPS 地址、端口、管理员账号和密码；APK 不内置任何生产面板入口。密码不保存，刷新令牌进入 Android 安全存储，退出登录会清除已保存的入口和账号。
- 底栏包含首页、用户、节点和设置。
- 首页显示服务状态、包含面板本机的节点摘要、节点预算、服务控制和系统资源；系统资源卡可二次确认后排队重启服务器。
- 用户页不分页，默认按网页端的新增倒序显示；选择下拉项后可按流量、在线设备或用户名排序，并支持完整用户操作。
- 节点页同时显示面板本机与远程节点，支持指纹核对、紧急停用和启用；底部按 5 秒采样展示每台服务器的实时流量。
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
flutter build apk --release --build-name=0.2.1 --build-number=3
```

每次更新必须同时满足：

1. applicationId 保持 `vip.ssrvpn.hysteria2manager`。
2. 使用同一个发布密钥。
3. `versionCode` 高于已安装版本。
4. APK Release 资产命名为 `Hysteria2-Manager-vX.Y.Z.apk`，App 才能自动发现更新。

发布密钥或密码一旦丢失，将无法覆盖更新已经安装的 App；应把密钥和本地签名配置放入受控的离线备份。

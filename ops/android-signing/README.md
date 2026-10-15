# Android 发布签名的持久加密备份

`backup.json.age` 使用 age X25519 加密，包含本项目原发布密钥库、密钥库密码、私钥密码和别名。相邻 `backup.json.age.sha256` 记录密文 SHA-256。这里不保存解密密钥、明文签名配置或生产服务器数据。

- 初始化日期：2026-10-15（北京时间）。
- 来源：[原仓库签名 Secrets 的加密导出](https://github.com/Elegying/Hysteria2-panel/actions/runs/38726568935)。
- 恢复密钥：原仓库的 `ANDROID_SIGNING_BACKUP_AGE_IDENTITY` Secret。
- 首次本地验证：密钥库与原本机文件逐字节一致；密钥库密码、私钥密码及正式证书指纹均通过校验。
- 正式证书已与 `v0.39.40` Release 中的 `Hysteria2-Manager-v0.4.12.apk` 独立比对一致。

重新安装开发工具并登录 GitHub 原仓库所有者账号后，在项目根目录执行：

```bash
python3 .github/scripts/android_signing_recovery.py request
```

恢复工作流使用这里的持久密文与专用恢复 Secret，不读取日常构建的四项签名 Secrets；其加密下载 artifact 只保留一天，过期后重新执行即可。恢复脚本拒绝覆盖不同的本地签名文件。

完整安装、恢复、验证与发布步骤见[开发与发布恢复手册](../../docs/DEVELOPER_RECOVERY.md)。本方案依赖原 GitHub 仓库、所有者账号与恢复 Secret 可用，不以公开密文代替账号恢复或离线灾备。

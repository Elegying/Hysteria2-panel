# 两个面板的 OSS 备份

独立运维适配器，复用面板现有归档格式和校验器，不改动原有 WebDAV 后端。

| 面板 | OSS 前缀 | RAM 身份 |
| --- | --- | --- |
| 私家车面板 | `nikuaimobi/私家车备份/` | `hy2-private-car-backup` |
| 私家车专线面板 | `nikuaimobi/私家车专线备份/` | `hy2-private-car-dedicated-backup` |

## 运行方式

- Python 程序及隔离环境：`/opt/hy2-oss-backup/`。
- 凭据配置：`/etc/hysteria2-panel/oss-backup.json`，必须为 root 所有、权限 0600 的普通文件。按对应 example 填写，真实凭据不得提交仓库。
- `hy2-oss-backup.timer`：北京时间每周一 09:00 备份，停机错过时恢复后补跑。
- `hy2-oss-retention.timer`：每天北京时间 09:45 检查过期对象，不生成新备份。
- 首次上传并验证成功后才启用两个 timer，并停用原先未配置的 WebDAV 定时任务。

## 验证和保留

在线 SQLite 快照生成归档，校验数据库、备份结构及连接身份。上传指定前缀，显式设置对象 ACL 为 private、服务端 AES256 加密。上传后重新下载比对完整 SHA-256 和大小，并以匿名 HEAD 验证返回 403。

仅删除本程序命名的归档，文件名时间和 OSS 修改时间均须超过 30 天。清理前必须有最近 8 天内成功备份，且再次下载校验成功；否则停止清理，保护已有恢复点。因此故障期间保留期可能延长，正常情况下在满 30 天后的每日检查中清理。手动文件、其他目录和其他 Bucket 不在权限范围内。

Bucket 当前承担公开文件分发，备份必须保持对象级 private，不能依赖 Bucket 默认 ACL。目录不是独立权限边界，边界由 RAM 对象资源和 ListObjects 前缀条件建立。

## 运维命令

```sh
systemctl start hy2-oss-backup.service
systemctl start hy2-oss-retention.service
systemctl list-timers 'hy2-oss-*'
cat /var/lib/hysteria2-panel/oss-backup-status.json
journalctl -u hy2-oss-backup.service -u hy2-oss-retention.service
```

状态文件独立于面板原有 WebDAV 状态，当前不会自动显示在面板的异地备份状态卡片。失败日志只输出阶段和异常类型，不打印凭据或签名请求。

暂停：`systemctl disable --now hy2-oss-backup.timer hy2-oss-retention.timer`。暂停不会删除 OSS 归档，面板及 VPN 服务不依赖此适配器。

## 本地测试

```sh
python3 -m unittest discover -s ops/oss-backup -p 'test_*.py' -v
```

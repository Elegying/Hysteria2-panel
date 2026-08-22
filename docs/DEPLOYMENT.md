# 多节点发布与回滚

正式发布只从 GitHub Release 获取 `install.sh` 与 `install.sh.sigstore.json`，并按 README 的固定 Cosign SHA-256、OIDC issuer 和精确 workflow/tag identity 完成验签。不要从 `main` 直接以 root 执行脚本。

## 正式 Release 创建与发布门禁

发布工作流只接受严格的 `vX.Y.Z` 标签，并且必须从该标签引用显式调度。它会验证标签提交等于当前 `origin/main`、源码与安装器版本一致，并把七项常规 CI 与六平台安装矩阵都绑定到该标签引用和精确提交；随后创建或复用**草稿** Release，生成并上传 Sigstore bundle，重新下载草稿资产逐字节比较并验签。`gh release edit --draft=false` 是工作流最后一个命令，前一步失败时 Release 保持不可公开的草稿状态。

维护者先确认 PR/主分支 CI 通过，再在最新 `main` 创建并推送标签；标签 push 触发的 CI 也必须全部完成，发布工作流不会等待或跳过红灯。可以提前创建草稿；省略 `gh release create` 时工作流也会创建：

```bash
set -euo pipefail
tag=vX.Y.Z
git switch main
git pull --ff-only --prune origin main
version="${tag#v}"
grep -Fx "PANEL_VERSION = \"${version}\"" hy2panel/version.py
grep -Fx "PANEL_VERSION=\"${version}\"" install.sh
git tag --annotate "${tag}" --message "${tag}"
test "$(git rev-parse "${tag}^{commit}")" = "$(git rev-parse origin/main^{commit})"
git push origin "refs/tags/${tag}"
# 等待该标签 push 的 CI（含 full-installer-e2e）全部为 success
gh workflow run installer-nightly.yml --ref "${tag}"
# 等待该标签的 Ubuntu、Debian、Rocky Linux amd64/arm64 六项矩阵全部为 success
gh release create "${tag}" --verify-tag --draft --title "${tag}" --generate-notes
gh workflow run release-signature.yml --ref "${tag}" -f tag="${tag}"
```

不要从 `main` 引用调度签名：更新器固定的 Sigstore identity 以 `@refs/tags/<版本>` 结尾，工作流也会拒绝 `GITHUB_REF` 与输入标签不一致。若同名 Release 已公开或被标为 prerelease，工作流安全停止，不会覆盖后再签名。

本地契约测试会确认 `full-installer-e2e` 和六平台矩阵都是发布工作流的硬门禁，但本地文件不能伪造 GitHub 远端分支规则。`Protect main` ruleset 已于 2026-08-22 通过 GitHub API 回读确认七项 required status checks，其中包含 `full-installer-e2e`；每次发布仍应重新回读远端规则。发布门禁通过 Actions workflow-run 与 jobs API 绑定精确标签、提交、触发事件和任务集合，因此不会复用同一提交上更早的 PR 或 main 检查结果。

`Anonymous release distribution synthetic` 每日以无凭据请求 latest API、两个 Release 资产和标签 raw 文件，比较安装器并复核 Sigstore 身份；它只拥有 `contents: read`，失败会留下 Actions error 并令 job 变红。仓库由私有恢复为公开后，仍需手工运行一次该 workflow 并取得绿灯，再把匿名分发恢复判定为闭环；同时应为该 workflow 开启 GitHub Actions 失败通知。

## 节点证书生命周期

Hysteria 节点使用自签名证书并把 SHA-256 指纹固定在已发放链接中；管理面板继续按既定方案使用公开 HTTP `IP:端口`，两者不要混为一谈。自动静默更换节点证书会让所有仍固定旧指纹的客户端断连，因此项目不执行无人值守自动续签或轮换。

面板启动时会读取证书的生效和到期时间，`/metrics` 输出生效倒计时、剩余秒数和有效状态；仪表盘按 180 / 90 / 30 天显示剩余天数。尚未生效、已过期或无法解析的证书都会使 `/readyz` 失败，恢复包中的证书还必须至少剩余 15 分钟有效期。进入提醒窗口后应先下载并离线验证完整备份，再在维护窗口生成新证书、发布包含新指纹的节点链接，并保留旧入口完成客户端迁移；不要只替换证书文件后立即重启。

备份 ZIP 只有在完整自校验通过后才会原子提供下载。恢复过程采用流式校验和替换、预检工作目录与回滚目录空间，并保留最近 30 天且最多 10 份自动回滚目录；失败恢复包保留 7 天且最多 10 份。长期或异地备份仍须由运营方存入受控的加密存储，项目不会猜测外部存储凭据或目的地。

## 发布批次

多节点采用 `max-unavailable=1`：任何时刻只升级一台，当前节点全部验收通过后才进入下一台。建议先选低流量节点作为 canary，并保留至少一台未升级节点用于对照和回退。

每台节点升级前记录：

- 当前版本、节点域名、主 UDP 端口、面板端口、证书指纹和 `EGRESS_POLICY`；
- `systemctl is-active` 对面板、主 Hysteria、TCP 探测及启用时的 UDP/TCP `443` 服务结果；
- `/healthz`、`/readyz`、主/`443` 监听和最近一次自动备份目录；
- 备份分区可用空间，以及没有 `.upgrade-active`、恢复事务或出站切换事务。

升级后必须再次核对上述状态，并用既有分享链接完成 Hysteria 握手与网页数据面测试。发现任一身份、端口、流量结算、服务、监听或数据面异常时，立即停止后续批次；保留现场和 `/var/backups/hysteria2-panel/<时间戳>/`，不要同时升级其他节点。

## 中断恢复

安装器只在备份清单和 `.upgrade-active` 已持久化后覆盖程序。进程被强制终止或主机重启时，`hysteria2-panel-upgrade-recover.service` 会在面板前恢复文件并排队启动旧服务，随后独立健康复核任务验证旧入口并删除标记。标记仍存在即表示恢复没有完成，不得继续升级；先检查 recovery/verify unit 日志与备份清单。

普通失败会在当前安装器进程内回滚。自动恢复仍失败时保持节点隔离，按 README 的整体回滚说明处理，不要只替换数据库或单个 unit。

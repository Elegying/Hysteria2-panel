# 隔离恢复演练与容量基线

这些脚本只用于可丢弃的 Linux/systemd Docker 容器，不能对生产服务器运行。脚本同时检查容器标记、固定测试端口、合成入口和显式授权标记；只使用新生成的测试身份，不读取生产备份。容器不发布宿主端口。

## 建立基线

Linux 主机需要 Docker，源码位于当前目录。Docker 的 privileged 权限仅用于容器内 systemd、防火墙和安装器演练；主机本身也应是专用开发或测试环境。

```bash
set -euo pipefail
docker build -f tests/installer_e2e.Dockerfile -t hy2-runtime-lab .
docker run -d --privileged --cgroupns=host --cpus=2 --memory=2g --memory-swap=2g \
  --name hy2-runtime-lab --tmpfs /run --tmpfs /run/lock \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw hy2-runtime-lab
git archive --format=tar -o /tmp/hy2-runtime-source.tar HEAD
docker cp /tmp/hy2-runtime-source.tar hy2-runtime-lab:/tmp/source.tar
docker exec hy2-runtime-lab mkdir /workspace
docker exec hy2-runtime-lab tar xf /tmp/source.tar -C /workspace
docker exec hy2-runtime-lab systemctl is-system-running --wait
docker exec -e PANEL_REF="$(git rev-parse HEAD)" hy2-runtime-lab \
  bash /workspace/tests/installer_e2e.sh
```

安装器会下载精确提交的源码并核验其固定哈希，因此 `HEAD` 必须是远端可获取的提交。未提交的本地修复不会被上述安装器自动装入；不要把基线安装通过写成未发布工作树的安装验收通过。

复制本地实验工具并启用实验 TLS：

```bash
for file in runtime_lab.py runtime_lab_crash.py runtime_lab_nodes.py; do
  docker cp "tests/$file" "hy2-runtime-lab:/workspace/tests/$file"
done
docker exec hy2-runtime-lab sh -c 'echo synthetic-only > /run/hy2-disposable-runtime-lab'
docker exec hy2-runtime-lab python3 /workspace/tests/runtime_lab.py tls
docker exec hy2-runtime-lab python3 /workspace/tests/runtime_lab.py capacity \
  --users 100 200 500 --concurrency 2 8 16 --seconds 8 --output /tmp/capacity-before.json
```

如需测量当前未发布工作树，本轮只修改三个运行时文件，可在基线结束后明确复制并重启：

```bash
for file in hysteria2_panel.py hy2panel/dashboard.py hy2panel/mobile_api.py; do
  docker cp "$file" "hy2-runtime-lab:/opt/hysteria2-panel/$file"
done
docker exec hy2-runtime-lab systemctl restart hysteria2-panel.service
docker exec hy2-runtime-lab python3 /workspace/tests/runtime_lab.py capacity \
  --users 100 200 500 --concurrency 2 8 16 --seconds 8 --reset-load-users \
  --output /tmp/capacity-after.json
```

`--reset-load-users` 只重建合成 `load-*` 账户，并拒绝重建已有计量的账户。前后对比需要相同账户规模、并发、时长和硬件限制；避免同时运行其他实验。原始结果记录源码 SHA-256、请求结果、吞吐、P50/P95/P99、进程 CPU 时间和 RSS。CPU 配额包含容器内的负载发生器。

默认是闭环饱和测试：每个 worker 等上一次请求结束才发下一次，不能据此承诺固定到达率的延迟。增加 `--rate 60` 可固定总到达率，延迟从计划发出时刻计算，包含排队和调度延迟；过载时不会静默丢弃已计划的请求。HTTP 每次建立新连接，管理请求使用校验证书的 HTTPS，本机 Hysteria 认证使用生产同款回环 HTTP。

## 恢复与节点补传

```bash
docker exec hy2-runtime-lab python3 /workspace/tests/runtime_lab.py recovery \
  --output /tmp/recovery.json
docker exec hy2-runtime-lab python3 /workspace/tests/runtime_lab_nodes.py
```

恢复脚本通过真实网页接口导出、上传备份，比较用户、令牌、权限、额度和累计用量；在 `prepared`、数据库替换完成、`disk-consistent` 三个位置执行 SIGKILL，然后由已安装的 systemd 恢复服务自动完成。原目标与备份的 TLS/HMAC 身份相同时，数据库已完整替换的中断点允许验证后继续完成；更早的中断必须回滚。每次恢复后对主 UDP 端口与 UDP 443 分别运行真实 Hysteria 客户端，校验转发内容。测试目标为容器内 `198.18.0.1`，不向公网发送负载。

节点脚本使用合成节点记录和真实 Ed25519 签名，经 HTTPS 提交 1/2/5 路控制周期，核对精确字节增量；停止中央面板后落盘 50 个 spool 批次，重建 spool 读取器，中央恢复后重复提交每批以模拟 ACK 丢失，检查零重复、零少记和队列清空。它不覆盖节点安装、DNS 接入或多机器网络延迟。

导出 JSON 及相邻 `.metadata.json`，保留主机配置、Docker 配额和 Git 提交。不要导出容器里的数据库、私钥、归档或未脱敏完整日志。记录完成后停止并删除本次命名的容器：

```bash
docker stop hy2-runtime-lab
docker rm hy2-runtime-lab
```

短时实验不能代替 48 小时稳定运行、真实多机网络故障、主机断电测试或生产 RTO/RPO 承诺。尚未被采样的 Hysteria 内核计数仍可能在内核或主机崩溃时丢失。

## 未发布候选与发布前验收

`tests/release_lab_matrix.py` 接收一个独立目录，内含候选 `candidate.tar` 和从 `tests/installer_e2e.Dockerfile` 复制的 `Dockerfile`。归档必须包含当前工作树运行时源码、安装器、测试，以及 `tests/release_lab_curl.sh`；先记录源码 SHA-256。不要把私钥、数据库、签名材料或未脱敏日志打进归档。本轮按 Git 已跟踪与未忽略文件清单生成归档，未使用旧 HEAD 的源码替代工作树。

```bash
python3 tests/release_lab_matrix.py --directory /tmp/hy2-release-candidate \
  --architectures amd64 --prefix hy2-release-candidate
```

矩阵会创建自己的命名容器，运行原 `installer_e2e.sh`，保存各平台 JSON 和本地日志。需要 Docker Buildx；它会核对构建出的实际架构。ARM 优先在原生 ARM Linux 宿主执行相同命令并指定 `--architectures arm64`。源码传输替身只接受 `lab-candidate` 项目 URL，安装器固定哈希不变；外部软件仍按真实 URL 下载校验。不能把这个实验当作正式 GitHub 分发、标签绑定或 Sigstore 验签完成。

`--isolated-vm-host-network` 只适用于任务专用、可丢弃的 Linux 虚拟机，不能用于日常宿主或服务器；它改为串行并在每个场景结束后停止自己创建的容器。容器网络中的宿主 sysctl 缺失、自定义 netfilter 规则、D-Bus 初始化问题应解决实验环境，不应关闭产品保护逻辑。完整实验记录见 [发布前验收与短时异常复审](reviews/2026-10-24-release-acceptance.md)。

额外短时测试：

- `tests/runtime_fault_lab.py`：要求 root、Docker 及 `/workspace/.release-lab` 标记，创建仅 4 MiB 的 tmpfs 并真实写满，测试计量恢复、SQLite 写锁和统计 HTTP 503。
- `tests/runtime_service_faults.py`：沿用本页的显式 disposable 标记、端口和 HTTPS 配置，短暂丢弃本机统计端口报文并持有数据库写锁，随后校验双入口 QUIC。必须在完整安装完成后单独运行，不能与升级或恢复并发。

导出结果时只保存已知 JSON 路径。容器中 systemd 的挂载命名空间可能令 `docker cp` 对 `/tmp`、`/run` 的观察与 `docker exec` 不同；可使用 `docker exec <本轮容器> cat <明确的结果文件>` 读取 JSON，解析并保存，避免复制整个临时目录。

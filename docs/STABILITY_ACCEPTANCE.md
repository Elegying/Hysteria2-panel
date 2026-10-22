# 稳定性候选验收记录

本轮目标为现有功能不变的稳定性验收。完整合同见 [182 项功能基线](FUNCTION_ACCEPTANCE_BASELINE.md)，逐项记录见 [验收矩阵 CSV](STABILITY_ACCEPTANCE.csv)。矩阵中的测试文件只是执行入口；没有当前候选的充分证据时保持“未测”，不能把历史报告或文件存在视为通过。

## 候选与证据

- 测试分支：`codex/local-accounting-read-snapshots-20261022`。
- [草稿 PR #163](https://github.com/Elegying/Hysteria2-panel/pull/163)，不合并、不正式发布。
- 基线提交：`6d14976a44bdda112314407ed94a2a50e1c71316`。
- 第一检查点：`fe0c002`，累计计量恢复与展示查询去结算。
- 运行时修复：`7c21903b39f97f78f3cb9585f0333015a0638685`，展示在线 HTTP 移出认证锁、同一 SQLite 快照读取流量与时间、App 按节点样本计算速率。
- `bcb1e290ac588985606331a7d1318b589a40d01c`：采样、节点状态查询和固定服务操作不再继承父进程的 systemd 通知环境；隔离机日志曾反复出现子进程通知被拒绝，三个回归分支修复前失败、修复后通过。
- `41119ed4b9ba483212f43c643e61383b9b34913b`：在面板 unit 中设置 `MALLOC_MMAP_THRESHOLD_=131072`，保留原 `MemoryMax=256M`、请求线程上限、完整用户列表和页面流程。六平台安装回归增加 1,000 用户、10 客户端的真实页面请求。
- 后续短测 `gate6` 复现单次本地健康探测超时导致 watchdog 重启：健康与采集已经恢复，但失败后仍等待 15 秒才复查，超过剩余 systemd 窗口。失败后的复查间隔改为最多 1 秒，只有全部检查通过才发送心跳，原 30 秒窗口、2 秒探测和采集新鲜度不变。确定性回归在修复前首次恢复心跳为 32.4 秒（失败），修复后早于 30 秒；持续失败时仍不发送心跳。修复已随后续完整 CI、六平台安装和十分钟真实混合负载验证；连续观察仍未完成。
- 当前运行时候选：`b3d9509ff8615c2de942d56dd9b76467d35ff1bf`。在前述修复上，服务入口保留无活动事务的 SQLite 连接，防止 root 每日备份创建服务账号不可访问的 WAL。安装的 19 个 Python 文件与提交源码逐一一致。PR 测试合并提交 `f7b2e0453e760e14de38637fcae71f92dc256efe` 与该候选的树均为 `ad35b0e78cf108792e3ad86c34d19b14be335459`。
- [运行时 b3d9509 完整 CI](https://github.com/Elegying/Hysteria2-panel/actions/runs/39836271265)：Python 3.8.18/3.12.15/3.13.16 各执行 1,063 项，1,057 通过、6 项因加密工具/JDK 或 locale 条件跳过；Flutter 3.47.2 的 149 项及 analyze、Chromium 36 组交互、静态/隐私/哈希、依赖矩阵、systemd、防火墙及五组安装检查通过。该候选在本机补测签名恢复 9 项和证书 4 项全部通过，覆盖 CI 的六项跳过；不把跳过本身记为通过。
- [六平台完整安装](https://github.com/Elegying/Hysteria2-panel/actions/runs/39836264237)全部通过，包括新增的实际 root 备份期间服务账号读写、WAL 属主/0600/inode 和 checkpoint 检查。[附加原生/浏览器工作流](https://github.com/Elegying/Hysteria2-panel/actions/runs/39836271353)的 Firefox 151、WebKit 26.5 各九组核心流程和 Android API 24 通过；API 36 测试执行约 49 秒后通道结束，原始 artifact 确认宿主模拟器退出码 132，保留失败。
- 最新已核对的测试候选为 `dd8c03145e3c425f70774f312d9d89d1ea63c99e`，产品运行时仍为 `b3d9509`。[完整 CI](https://github.com/Elegying/Hysteria2-panel/actions/runs/39865561769)为 22 项成功、1 项 tag 条件跳过：Python 3.8/3.12/3.13 各执行 1,069 项（1,063 通过、6 条件跳过），Flutter 149 项/analyze、Chromium 36 组及其余既有检查通过；[六平台](https://github.com/Elegying/Hysteria2-panel/actions/runs/39865586195)全部通过，六组实际 root/WAL 并发均通过。[附加工作流](https://github.com/Elegying/Hysteria2-panel/actions/runs/39865561736)的 WebKit 15 组、API 24（21 秒）和修复后的 API 36（18 秒）原生断言通过。Firefox 在下载 Ubuntu 依赖时耗尽 15 分钟，未执行测试，不能记通过；原日志已保留。PR 合并测试提交 `87a0cca1a26f98f7a277ddbfef3ff323c5c41bb4` 与该提交同树 `8312d6d758cac23d39b345fc8d85f96496e88b24`。
- 北京时间 10 月 23 日手机 USB 实机检查已完成，原生回归及实际进程/网络恢复结果见 Android 小节。第二轮 48 小时观察在约 90 分钟断流后失败，原预计完成时间失效；旧失败实例停止保留，随后两小时诊断在 3,346.491 秒遇到节点控制请求 403；此次最先失败的是节点请求，100 条流均在停测后关闭。新实例只增加拒绝来源行和既有 Hysteria debug 日志继续定位。所有诊断均不能续算旧轮或转记 48 小时通过。
- 182 项逐条登记：75 项达到所列自动化/隔离测试合同，102 项尚缺完整实际验收证据，1 项连续观察失败待新候选重验，4 项属于后续正式发布而不适用。单条通过不等于各系统实机、部署和 48 小时整体门禁通过。
- 本机证据目录由执行环境保留，不向仓库上传私钥、会话、测试 APK、完整备份或原始面板配置。公开结果只记录源码 SHA、时间、构建摘要、错误分类及资源统计。

## 新增可重复入口

### 恢复上传边界

`tests/test_backup_upload_contract.py` 在真实 HTTP 处理器上补齐 BAK-08 的 14 个负向样本：额外/重复成员、目录、符号链接、相对穿越、绝对路径、压缩后不足 1 MiB 但实际展开超过 128 MiB 的数据库、multipart，以及 0、负数、非整数、超过 131 MiB、1 字节无效 ZIP 和声明 131 MiB 后提前 EOF 的请求。压缩样本分块生成，未缩小产品容量上限。三个测试均通过（Python 3.13.15，2.586 秒）；每组拒绝后确认未排队、无残留上传文件、原凭据有效，再通过原始有效 ZIP 的 202 响应确认维护锁可恢复。该证据属于自动化负向验收，不代表操作系统级恢复已经完成；产品代码未变。

### 浏览器

保留 `tests/browser_controls.py` 的 Chromium 完整交互。`tests/browser_core_flows.py` 为 Firefox/WebKit 增加真实 HTTP 往返、键盘登录、弹窗焦点、窄屏、200% 等效缩放视口、创建失败恢复、操作取消/确认、备份下载和退出。等效视口同时将 CSS 宽高减半、设备像素比例设为 2；仅设置 CSS zoom 不会触发相应媒体查询，首轮相关失败日志保留。浏览器菜单中原生缩放仍需人工验收。

补充验收将每个引擎从 9 组扩展到 15 组：三个视口均实际用键盘提交添加用户，逐一导航到备份、文件选择和恢复按钮，核对焦点位于视口内且未被固定标题遮挡；再验证 404、CSRF 403、错误登录后的恢复及退出。本机 Firefox 151 和 WebKit 26.5 均通过，截图已检查。首次补测的用户名选择器同时命中排行榜与用户表，已限定为用户表；另一首次失败确认是 macOS WebKit 的默认 Tab 仅经过文本输入，Option-Tab 才包括按钮，已使用 [Apple 文档中的平台按键](https://support.apple.com/guide/safari/keyboard-shortcuts-and-gestures-cpsh003/mac)，未修改系统键盘设置。两次夹具失败均保留，不能计为产品缺陷。缩放上下文使用独立会话，避免退出验收撤销另一个视口的会话。

纯文档提交 `18a26460b754c1360d0595142d5a2783d3b57b88` 的[完整 CI](https://github.com/Elegying/Hysteria2-panel/actions/runs/39841565551)与[六平台](https://github.com/Elegying/Hysteria2-panel/actions/runs/39841554382)均通过，Python/Flutter/Chromium 数量与运行时候选一致；六平台的真实 root 备份并发检查也全部通过。[原生工作流](https://github.com/Elegying/Hysteria2-panel/actions/runs/39841565604)的 API 24 通过，API 36 在原生测试约 58 秒后再次失败，artifact 确认宿主模拟器退出码 132，尚未定位具体崩溃帧。为下一轮 CI 增加仅作用于 API 36 宿主的 GDB 调用栈诊断，先用受控 SIGILL 自检；关闭栈参数和局部变量输出，不收集进程内存。调试器退出码单独记录，不冒充模拟器退出码，也不把调试运行当作故障已解决。渲染器、SDK 和应用断言保持原样。

实际回读 GitHub 的 `Protect main` 规则集确认 `mobile-tests` 仍为必需检查。当前提交的发布输入扫描与本地隐私回归通过；独立临时 Git 仓库同时验证忽略的本地证据不进入扫描、不被改写。上述新增内容仅为测试与证据，运行时仍固定为 `b3d9509`；当时没有因这些改动重置观察。该轮后来因真实断流失败，见末节。

`98293f3217bf79e4a4bdb6da157c28455f817eb5` 的[完整 CI](https://github.com/Elegying/Hysteria2-panel/actions/runs/39844286458)与[六平台](https://github.com/Elegying/Hysteria2-panel/actions/runs/39844372033)均已通过，Python 各 1,063 项（6 跳过）、Flutter 149 项、Chromium 36 组及 root/WAL 并发检查与前述一致。[附加工作流](https://github.com/Elegying/Hysteria2-panel/actions/runs/39844286782)确认 Linux Firefox/WebKit 各 15 组及 API 24 通过；API 36 受控 SIGILL 自检成功，随后实际模拟器仍失败。GDB 捕获 RenderThread 的 SIGILL，停止在 `libgfxstream_backend.so` 的 `ud2` 指令，调用者为 `gfxstream::gles2_decoder_context_t::decode`；继续传递原信号后宿主确实终止。该轮调试器退出码是 255，不当作模拟器退出码；没有将其归为应用 Dart 异常或 DDS 启动失败。完整栈、原生日志和 artifact（SHA-256 `ebdb2848c82c14a240b740012b2c9f5509ea2d73b640ac1044817ab0fd588954`）已保留。

后续仅把 Linux API 36 测试环境从 SwiftShader/ANGLE 改为 [Android 官方支持的 Mesa Lavapipe](https://developer.android.com/studio/run/emulator-acceleration) 做驱动对照，并记录模拟器版本、图形库哈希及设备图形能力；仍保留宿主栈诊断、Flutter 3.47.2、Impeller 和全部应用断言。这是有已知崩溃位置的环境对照，尚无通过结果，也不声称原 SwiftShader/ANGLE 路径已修复。服务端和 App 运行时代码未变。

`b4a6849` 的实际 Lavapipe 对照已完成，仍在相同 `0x7fffe97c3bed` 的 `ud2` 指令发生 SIGILL，调用者仍为 gfxstream GLES 解码路径。模拟器为 37.2.12 / build 16428233；二进制 SHA-256 为 `27e9a8cbd545529ba2c1aca973e5bc060f50b36a68d2c03296b0162291a16b83`，图形库为 `56be2b2c9db645d8277893cc7919b16f2862d72f6b98831ac60f334ef08c6d32`。完整 artifact 摘要 `261c84959a5307001b9248772c99e786b9af2170ae1cf0f1e17948c183f8a119` 已核验，原信号继续后宿主终止；调试器返回 255 不作为模拟器退出码。`-gpu lavapipe` 并不证明所有 GLES 路径已独立替换，不能把本次失败扩大为应用渲染缺陷或宣称驱动问题已修复。

`89923a9` 的失败 artifact 摘要为 `780cc586b1b8a4f0a3b68184a90a79d961bc5297bb10255fd575ed979777d1a9`。从官方安装包取出图形库，与 CI 上述哈希完全一致；离线 LLVM 分析把停止位置对应到库内 `0x7c3bed`，调用返回位置为 `0x739d89`。字符串引用和解码入口明确为 `glInvalidateFramebuffer`。该函数的附件数为零时跳转至 `ud2`；另一个数组越界分支也进入同一指令，因此旧堆栈本身尚不能判定具体参数。官方 gfxstream 对应实现对 `std::vector` 使用 `&emulatedAttachments[0]`，而固定 Flutter 3.47.2 的 GLES 渲染入口允许零附件调用。新增只记录两个整数寄存器的 GDB 诊断，以及[独立 GLES 探针](../tests/android_gles_probe/GlesProbe.java)，按一个附件、零附件依次执行真实 EGL/GLES 调用，不包含 Flutter、网络、会话或 App 数据。

`87da9475916c8f601429727a277394e6f062db36` 的[独立复现](https://github.com/Elegying/Hysteria2-panel/actions/runs/39863482421)确认：默认驱动执行一个附件成功，零附件时模拟器宿主在同一 `0x7c3bed` 触发 SIGILL；GDB 捕获 `ebx=0`、`r14d=36160`（`GL_FRAMEBUFFER`）。同提交[原 App 的失败](https://github.com/Elegying/Hysteria2-panel/actions/runs/39863482247)也捕获相同参数。因此本次根因是模拟器 host GLES translator 对合法空附件数组取首元素，已用不含 Flutter 的程序独立复现。两个完整 artifact 摘要分别为 `955e7d0cdec65be708c64352efc8ce3e6e6d698149c4ad7cdeab9c7fa20b220e` 和 `d8956c3c0ff9f99b4726e65e44cfd07a720088d416e41f9a630032f6ff2ef895`，失败证据保留。

同一独立实验中，按[Android 官方设置](https://developer.android.com/games/develop/vulkan/overview#about-angle)选择 Android 15+ 自带的 guest ANGLE 后，一个及零个附件均返回 `GL_NO_ERROR`，实际渲染器显示 ANGLE/Mesa Vulkan；artifact 摘要为 `224a0b8e298ebb3e09277756e232d09ddf5f0669bfaec209b1c9a6586e506c9c`。修复只配置 API 36 CI 内两个独立测试包的 GLES-on-Vulkan 驱动，正式 App、Flutter、Impeller 和其他包的选择规则不变。探针进一步断言自身加载 `libGLESv2_angle.so` 且使用 ANGLE/Vulkan，App 原生回归也独立核对本进程加载的 guest ANGLE 库；仅写设置或渲染器名称含 ANGLE 不足以满足断言。`dd8c031` 的实际原生回归现已通过：探针确认 guest 库已加载、两个附件数量都成功，App 进程也独立确认加载同库，原有全部原生断言 18 秒通过。完整 API 36 artifact 摘要为 `d56878d2de19bf9d5d6134ee1bea4c81670cab2f756d0a3ba43457488f83a55e`；API 24 为 `f382077ef34736e19cf0418e6e4681e583d742ab28afbd3090504452737d676b`。

原始默认驱动的已知失败保留在手动诊断工作流中，不声称上游图形库已经修复；每次 API 36 正式验收则必须先通过实际驱动与一/零附件探针，再执行原有完整 App 断言。

同轮 Firefox 未执行测试：Azure HTTP 软件源下载 7.5 MB 字体约耗时 156 秒、9 MB 编解码库约耗时 190 秒，最终在依赖安装阶段达到任务期限。此前 WebKit 也曾出现同类环境取消。仅将这两个临时浏览器 runner 的 Ubuntu 源改为官方 HTTPS archive，保留原发行版、签名验证、依赖、Playwright 版本、15 分钟任务边界和全部断言；须由新提交的实际 CI 验证，不能把取消视作产品测试通过。

`4deea60d91b8e0f5cfe43ba8d7d3e1bbc8b25c1e` 的[附加工作流](https://github.com/Elegying/Hysteria2-panel/actions/runs/39851417074)在新加的 `emulator -version` 环境采集处退出 127：命令加载图形版 QEMU，runner 缺少 `libpulse.so.0`，两个 Android 任务均未启动模拟器或应用测试。因此该轮不能用于判断 Lavapipe 结果。两个失败 artifact 已保留；版本改为直接读取安装包的 `source.properties`，继续记录二进制哈希，实际模拟器仍沿用已有 `-no-window -no-audio` 启动命令。

```sh
python -m pip install playwright==1.61.0
python -m playwright install firefox webkit
python tests/browser_core_flows.py --engine firefox --output /tmp/hy2-firefox
python tests/browser_core_flows.py --engine webkit --output /tmp/hy2-webkit
```

### Android

`stabilityTestBuild` 必须同时设置 `previewBuild`，只允许 debug。使用独立包名 `vip.ssrvpn.hysteria2manager.preview.stability`，支持测试用 x86_64/arm64；普通发行构建仍只有 arm64。正式 App 和已有预览 App 的存储不受影响。

`tests/mobile_fixture.py` 提供两套临时 HTTPS 测试面板。仅集成测试入口信任这次生成的测试证书；产品连接器、证书验证和 HTTPS 限制保持不变。`mobile/integration_test/native_acceptance_test.dart` 覆盖真实安全存储、HTTPS、双面板、控制器重建、注入网络错误后的恢复、四个模块及退出。控制器重建不等同于操作系统强杀进程、真实网络切换和后台驻留，这些项目需另记实机证据。

原生测试命令固定添加 `--no-uninstall`。Flutter 首次构建前可能缓存源码中的基础包名，失败清理曾尝试卸载该基础包名；不能让测试驱动自动卸载正式 App。测试代码先断言独立包名，再清理该测试包自身存储。手机首次测试前也应核对包名、ABI 和现有安装状态，任何清理只针对独立测试包。

Android 17 / API 37 的 USB 真机（2509FPN0BC）已在用户解锁后完成原有全部原生断言，1 passed，22 秒。固定 Flutter 3.47.2、原 Impeller 和界面，测试命令带 `--no-uninstall`；独立 APK SHA-256 为 `f3fa54eaf0f5f86ed5112ac3a5c7ed92055d5c3e9e086ab58a83afe5a10edee9`。正式 App 的版本、路径、首次安装和最后更新时间在检查前后完全一致。

另用仅测试的 [原生生命周期入口](../mobile/integration_test/native_lifecycle_probe.dart)运行现有 App/controller，不注入网络错误：在独立包内建立双面板会话，系统强停后由新 PID 启动，确认安全存储、所选面板和会话恢复，并确认刷新令牌确实轮换。实际 Home/恢复产生 paused/resumed，原 PID 保持不变且管理查询成功；两面板再次切换均与各自 overview 一致。退出后再强停、以第三个 PID 启动，仍为退出状态。

真实切网使用 `tests/mobile_fixture.py --listen-host <本机私有LAN地址> --base-port 31890 --defines <私有文件>`：只监听明确的私有地址，为 LAN 夹具生成一次性随机管理员密码与 CA，USB 不转发这两个端口。实际默认网络从 WIFI 切到 CELLULAR 后，局域网面板不可达，请求在 10.008 秒失败且保留会话；切回 WIFI 后 61 毫秒恢复成功。首次控制脚本在 Wi-Fi 关闭通知先于默认路由变更时提前停止，未执行网络阶段；原失败记录保留，随后在原 35 秒期限内同时等待设备状态和实际默认路由，完整流程通过。没有放宽 App 超时或更改网络处理。

生命周期入口从独立包私有 `files/lifecycle-config.json` 读取夹具定义及 `mode`（seed、restore、logged-out），从 `files/lifecycle-command.json` 读取递增 sequence 的 overview/select/logout 指令，向 `files/lifecycle-report.jsonl` 输出不含凭据的断言和 OS 生命周期事件。宿主通过该 debug 包的 `adb shell run-as` 原子写入控制文件；只有 seed 阶段清理这个测试包的存储。强停/重启使用同一 APK，不重装或清数据。实际测试 APK 摘要为 `68e99c26cae4cdf96be47d39c781b53eeb392a010ce877c6ae5b6315a6e0df43`，入口源码摘要为 `b3db9b71f37475903b5e8ad38673770c90100d21924c9ac7151bf641b2086641`。

测试后恢复手机原先关闭 Wi-Fi 的状态，停止独立包和两个夹具，移除本任务 ADB 映射。LAN 在移动网络下不可达是本次故障条件，不是公网面板在移动网络下可达的证据；未把这些结果扩展为手机整机重启、后台长驻、服务端撤销或全部 24 项 App 交互合同通过。逐项未测项仍保留。

| 状态 | 预期反馈与恢复 |
|---|---|
| 读取节点新样本 | 按该节点的采样间隔计算速率 |
| 重复样本 | 保留速率与基线，等待新样本 |
| 时间倒退或计数下降 | 速率归零并重建基线 |
| 旧服务缺少有效样本时间 | 使用原响应时间口径 |
| 迟到响应或离开页面 | 原有请求代次保护继续生效 |
| 请求失败 | 保留可信数据，提示错误，允许重试 |

### Linux 持续观察

两小时断流诊断 `89923a9` 在 3,346.491 秒失败。新增事件日志确认：`node-1` 的控制周期先返回 HTTP 403，随后所有 100 条回显连接才在 `stopping=true` 下关闭，首个关闭晚 22.162 ms。失败节点本轮流量、快照和命令轮询均未提交；另外九个节点完成了该轮。面板及两个数据面进程没有重启，面板 cgroup 的 OOM 计数均为零。完整事件、原始日志、宿主资源记录和 UID 997 一致数据库副本已保留。这个失败不同于上一轮最初的 `unexpected stream close`，不能混作同一根因。

在两份独立数据库副本上，使用原签名密钥与真实 OpenSSL 验签器做一次串行/同步对照：串行 10/10 接受；10 路同步时实际验签峰值为 8，其中一个请求在 `_verify` 第 245 行的非阻塞槽位门控处拒绝，另九个通过。该实验没有改运行中的服务、原数据库、8 路上限或返回语义；它确认了门控拒绝路径，仍不能代替旧现场缺失的分支证据。真实节点已有持久化批次与抖动退避，当前合成报告器则固定 10 秒且遇任意 403 停止全部负载，二者的恢复行为不能混同。

新的空白诊断实例仍运行原 1,000/10/100/10/64 负载，只在私有启动器记录拒绝函数/源码行/时间，并打开现有 Hysteria debug 关闭日志；无权限信息、payload 或密钥输出，不更改拒绝分支、负载、超时或产品源文件。该包装器仅用于定位，不属于最终候选或 48 小时验收环境。

`tests/stability_soak.py` 只接受明确标记的独立 Docker/systemd 测试环境，必须使用测试端口、空白用户/节点数据以及与安装目录一致的源码。它保留原 Hysteria TLS 身份与全部 ACL，在隔离网络中使用 `198.18.0.2` 作为数据面回显目标。

负载为 1,000 用户、10 个持 Ed25519 身份的合成节点报告器、10 个真实 Hysteria 客户端、双入口合计 100 条持续 TCP 流、10 个管理查询客户端及 64 路认证突发。合成节点报告器不等同于 10 台独立物理服务器或各自运行完整代理的节点。

默认观察 172,800 秒，记录每 30 秒的 RSS、线程、文件句柄、CPU ticks、监听队列和认证 p95。远端每批核对累计值，结束时核对双入口实际累计值与本机账本。运行不足 48 小时只标记 `short-run-only`；异常终止、服务/客户端退出、账本不符、RSS 或资源增长超限均失败，并保留原目录与数据库。

合成节点使用实际 Ed25519 签名分别发送控制周期与心跳；不能用测试直接改数据库维持在线。启动记录 Python、平台、CPU 数、安装目录源码和 unit 摘要。观察采样断档或墙钟与单调时钟偏离超过 90 秒即失败，不把主机睡眠或暂停计入连续观察。

首次预热 10 分钟后，比较首末一小时 RSS 中位数，允许增长为 `max(10%, 16 MiB)`。运行时代码改变后必须重新计时。仅文档调整可以继续，但必须保留源码哈希对应关系。

## 已复现的资源问题与修复证据

在 Ubuntu 24.04 arm64、2 vCPU/2 GiB 的独立 Linux 环境中，1,000 用户的完整页面约 2.95 MB。只运行 10 个管理查询客户端、连续 30 次请求即可使旧候选触发面板自身 256 MiB cgroup OOM；内核记录为 `CONSTRAINT_MEMCG`，不是整机内存用尽。失败容器、数据库和原始日志保留。

Python 分配剖析完成后仅约 14.9 MB 活跃分配，手动 GC 没有回收循环对象；大页面请求后的 RSS 增长与底层分配器保留大块缓冲一致。固定 mmap 阈值后的对照支持这一判断。该设置使超过阈值的大块分配可以在释放时归还系统，机制见 [glibc 官方说明](https://sourceware.org/glibc/manual/latest/html_node/Memory-Allocation-Tunables.html)。

| 相同规模的实际 HTTP/SQLite 查询 | 成功请求 | 面板峰值 RSS | 进程 |
|---|---:|---:|---|
| 原候选，默认分配器 | 10/30 | 265.5 MiB | OOM 退出 |
| 固定大块分配阈值，原页面并发 | 30/30 | 84.7 MiB | 未重启 |
| 新增可重复安装回归入口 | 30/30 | 88.8 MiB | 未重启 |

最后一行的中位请求时间为 1.90 秒，最大 2.84 秒。单次短时结果不代表持续 48 小时通过；最终平台矩阵和混合负载仍须独立验收。回归入口为 `tests/installer_dashboard_capacity.py`，验证全部 1,000 行仍返回、30 次请求全部成功、PID/重启数不变以及原 256 MiB 上限未放宽。

另一个本机受控 HTTP/SQLite 对照使用外部服务替身：30 次查询触发的结算调用由 30 次降为 0，`fsync` 由 90 次降为 0。该对照的延迟没有改善，不能据此声称普遍提速，也不能代替真实 Hysteria 数据面测量。

混合负载进一步复现了节点写事务竞争：只上报单用户或空在线快照也会扫描所有账号。回归测得账号从 1 增至 1,000 时，单用户流量请求的 SQLite 步数从 1,176 增至 8,261，空快照从 842 增至 3,878。修复后分别为 1,180→1,272 和 833→872。在同一事务内仅按索引读取报告涉及的账号，每批最多 100 个绑定参数，保持原有大小写匹配和已删除身份处理，不缓存权限、不放宽超时。测试覆盖稀疏报告随无关账号增长的工作量，以及大小写、未知/已删除账号边界。

该修复仍未使完整混合负载通过：`short6` 的 64 路认证出现超时；诊断运行 `profile4` 的节点控制周期超过 9 秒。仅在隔离容器中限制同时生成两份完整页面后，`gate5` 连续七轮认证完成，但一个管理查询超过夹具当时统一使用的 9 秒而停止；这不是生产修复或稳定通过证据。后续夹具按现有客户端分别采用节点 8 秒、管理接收 20 秒、认证传输 9 秒且总耗时必须小于 10 秒，不放宽产品时限；此前失败全部保留。后续完整混合负载达标结果见下文；以上失败原始证据保留。

进一步复现了展示数据库读取占用认证锁：人为暂停用户列表读取时，认证在 2 秒内不能完成。展示入口现只在锁内固定 SQLite WAL 读快照及对应采样时间，三个已有读取方法共享该连接，随后释放锁读取完整列表。回归同时验证认证强制结算可在读取暂停期间完成，而页面的用户累计值、来源账本和采样时间仍全部来自之前的同一个快照。原调用签名兼容，不引入缓存、页面并发门、数据库格式或权限变更；49 项展示/用户流量/域名流量、69 项分布式回归和 12 项资源检查通过；实际混合负载结果如下。

`ad676c9f32726497248a8bec46d8e3c3a882fc27` 随后的真实混合负载完成 600 秒观测和结束结算（合计 610.58 秒），标记 `short-run-only`。1,000 用户、10 个签名节点、100 条真实双入口流、10 个完整页面客户端、每轮 64 路认证均保持运行；20 个采样中认证最大 0.568 秒、采样 RSS 最高 72.7 MiB、监听队列为 0，服务未重启。最终两个实际内核与本机账本均为 138,501,326 字节。线程 6–12、文件句柄 5–23 反映请求活动，不能据十分钟数据断言长时不增长。此前超时与 watchdog 失败证据仍保留，48 小时门禁仍未完成。

实际进程过载验证占满 64 个认证槽位：额外请求在既有 5 秒排队期限后关闭（实测 5.005 秒），释放连接后线程从 70 恢复到 6，文件句柄从 69 恢复到 5，健康请求恢复 200。对齐 watchdog 周期后确实记录了一次本地探测失败，健康心跳距上次 19.284 秒恢复，PID 与重启次数保持不变。首轮探针误设 2 秒截止的失败日志保留；按代码既有 `worker_queue_timeout=5` 修正测试后验证，未改变产品排队或失败关闭规则。

`tests/accounting_filesystem_faults.py` 在独立 16 MiB tmpfs 上实际制造计量日志 ENOSPC、SQLite 文件系统耗尽和只读 EROFS。三种情况恢复后均准确计量 330 字节，重复采集仍为 330；数据库写入失败时保留待提交日志。该检查使用现有真实回环 HTTP/SQLite 夹具，不能代替整机断网或 Hysteria 数据面故障验收。

`tests/test_offsite_backup_https.py` 使用独立 HTTPS WebDAV 服务与一次性 CA，通过实际 TLS/socket 验证中文/已有转义路径、临时上传及 MOVE 前后回读、保留策略、等长损坏、PUT/MOVE 已执行但连接重置丢 ACK、拒绝重定向、不可信证书和错误凭据。5 项新测试及原有 16 项全部通过；丢 ACK 后保留已有备份和已发布对象，恢复后新上传成功，未在失败时提前清理历史。该测试覆盖协议与恢复，不代表生产存储接入或 root 每日 timer 的整机验收。

`tests/acme_isolated_acceptance.py` 使用 [Pebble v2.10.1](https://github.com/letsencrypt/pebble/releases/tag/v2.10.1)、配套 DNS 测试服务及 Certbot 2.9.0，在独立 Linux 环境执行原安装器证书函数，仅将 CA 地址替换为隔离服务。真实 HTTP-01 首次签发、重复安装保留未过期证书、非公网 DNS 在写入前拒绝、TCP 80 被占用时拒绝、DNS SERVFAIL 后保留旧证书及恢复后的续期共六项通过（9.06 秒）。测试没有关闭 TLS 验证，CA 仅在该子进程的信任文件中提供；专用 loopback 地址与 hosts 条目在结束后恢复。

Pebble 官方发布包固定 SHA-256：Linux arm64 的服务包为 `b53fd072a69eb7692451de4e8b0667e0bdf5cccd7e36fc51b8eaf2fcc135ed9f`，DNS 夹具包为 `db8e1a79ccdb2195c489fbe4f40fddb7f30e86f9cd8a07912566ee5025094d6c`。初次夹具缺少可执行权限、第二次被 Certbot 正常的随机调度等待超过 90 秒，两次证据均保留；只在测试续期命令中使用 Certbot 自带的 `--no-random-sleep-on-renew`，生产 timer 的调度不变。该结果不代替公网 CA 签发、自动部署 hook 和生产域名部署验收。

SIGKILL 实际终止了面板主进程，systemd 在约 4 秒内自动恢复。恢复后 SQLite quick check 为 `ok`，1,000 个用户的身份摘要、Hysteria 证书文件和本机账本 138,501,326 字节均与之前一致。该次强杀位于流量停止后的稳定账本阶段；在途提交各阶段的崩溃/恢复由既有累计计量回归另行覆盖，不把此结果扩大为未采样内核计数可在断电后恢复。

随后对专用 2 vCPU/2 GiB Linux 虚拟机执行完整停止/启动。Docker 测试容器按其重启策略自动启动，五个项目服务由 systemd 自动启动；同一组数据库、用户身份、TLS 与账本检查再次一致。已过期的合成节点状态未被冒充为新鲜状态：用户凭据仍有效，但新认证按原规则拒绝。该证据限于本次 Ubuntu arm64 虚拟机和容器，不扩展为六个发行版的物理主机冷启动验收。

## 失败与未测项目的处理

- 本机完整 Python 3.13.15 回归曾有一个总截止测试失败：请求子进程在到达 HTTP 服务前已被取消；截止与回收断言通过，服务端收到请求数的断言失败。保留原日志，不放宽产品超时。Linux CI 的三个 Python 版本结果单独记录。
- 首轮浏览器测试的 HTTP Secure Cookie、CSS zoom 视口模拟、用户列表返回类型错误属于测试配置问题，修正前日志保留。Linux Firefox/WebKit 核心流程通过；本机 WebKit 曾有导航阶段 access-control 报错，增加窗口异常诊断后的运行未复现，仍不能据此断言间歇问题已根除。
- Android API 24 原生集成通过。API 36 完成 HTTPS/双面板/安全存储后设备离线，Dart 驱动报告 `0 tests passed / No tests were found`。进一步记录确认宿主模拟器退出码 139；宿主仍有约 10.5 GiB 可用内存、swap 为 0，未记录 OOM。为区分模拟器图形后端，API 36 改用 Android 官方支持的 `swangle`（SwiftShader + ANGLE），保留产品 Impeller、玻璃效果及全部断言；原 `swiftshader` 崩溃日志保留，尚不能视为已解决或通过。选项见 [Android 官方图形加速说明](https://developer.android.com/studio/run/emulator-acceleration)。该轮尚无手机证据；后续 API 37 实机结果见 Android 小节，不用控制器重建或模拟网络错误替代真实系统操作。
- Android CI 的首轮模拟器启动失败已定位到 AVD 创建与查找目录不一致；固定独立目录，并在启动前检查 AVD 名称。安装容量回归在恢复 HTTP 配置后误用了 HTTPS Cookie，导致 303；测试按实际协议选择现有 Cookie 名称，产品会话规则不变。两类失败原始日志均保留。
- `41119ed` 的混合负载启动阶段出现一次固定服务 InvocationID 查询超过既有 2 秒时限，认证按失败关闭规则拒绝连接。同期本机存在其他构建负载；稍后 20 次只读查询为 11–61 毫秒。尚未证明根因，不放宽超时、不将本次记录计入 48 小时通过证据。
- 182 项矩阵保留正式发布阶段的“不适用”条目。`SEC-09` 与 `APP-03` 对可选记住密码的文字存在冲突：本轮保持现有可选安全存储行为，不能为了符合旧文字而删除功能。

API 36 的 `swangle` 对照也在首个测试完成前退出，宿主进程退出码 132，仍有约 10.9 GiB 可用内存且 swap 为 0。日志记录 Impeller OpenGLES，未出现应用崩溃栈。此症状与 [Flutter #192736](https://github.com/flutter/flutter/issues/192736) 报告的 Linux x86_64 软件图形栈崩溃相符；上游问题尚未解决，相关性不能代替本项目根因证据。随后 macOS arm64 的 Android 16/API 36 对照在同一 Flutter 3.47.2 下通过全部原生断言（155 秒，1 passed），保留 Impeller OpenGLES、现有玻璃界面和所有测试；模拟器为 37.2.12.0/16428233。该结果提供 arm64 的独立通过证据，不代表 Linux x86_64 原路径已解决。

## 收敛前仍需核对

后续若修改运行时代码，完整 CI、六平台矩阵和持续观察必须绑定新候选重新执行。Linux x86_64 的 Android API 36 失败、第二轮真实断流的根因、连续 48 小时及剩余逐项实际验收仍未完成。API 37 已完成的原生/生命周期/网络恢复不覆盖全部 App 验收点。HTTPS/ACME 和 WebDAV 的生产接入、真实公网证书签发仍为独立部署验收。

## 当前连续观察

候选 `845150bd9e1ab0598e735119cb4131875140c069` 的首轮真实 48 小时观察于北京时间 **2026-10-23 01:10:58** 开始，在 **2,651.449 秒（约 44 分钟）** 时失败，不能计入通过时长。一次管理页面请求在 0.131 秒被断开，服务端栈定位到 `list_nodes()` 的 `sqlite3.OperationalError: unable to open database file`。面板 PID 未变、重启数为 0，磁盘和 inode 充足，失败前采样 RSS 约 81.6 MiB；原始状态、指标、日志、数据目录和容器全部保留。此轮临时防空闲睡眠进程已停止，原预计完成时间失效。

独立临时数据库复现了夹具身份不一致的问题：root 查账进程与 `hy2panel` 服务账号交替打开 WAL 数据库，后者第 19 次读取即出现相同 `SQLITE_CANTOPEN`；SQLite 底层日志明确为打开 `probe.db-wal` 时 `EACCES(13)`。两边均以服务账号运行的对照累计 154,608 次读取无错误。SQLite 的 [Unix 文件实现](https://sqlite.org/src/artifact/410185df49)在 root 创建 WAL 后再修正属主，这段短暂窗口会影响另一个账号。

修正仅涉及隔离验收程序：共用一个身份切换入口，特权准备完成后永久切换到数据库服务账号，容量和持续负载均在该账号下直接查账；数据集预检也使用服务账号。数据库文件权限、产品代码、认证和账本规则不变。实际调用修正后的入口，原 root 工作进程与对照累计 103,256 次读取无错误，且不能重新取得 root 身份。仍须完成实际混合负载重验后，在全新隔离容器重新开始完整 48 小时；不能用此权限复现测试替代持续观察。

上一轮运行时代码的完整 CI 和六平台矩阵曾通过。纯文档提交 `08031420f8a4dd2bd7e0f02e15c6b3a0f2fb548b` 的[完整 CI](https://github.com/Elegying/Hysteria2-panel/actions/runs/39823643675)也通过；[附加工作流](https://github.com/Elegying/Hysteria2-panel/actions/runs/39823643712)的 Firefox、WebKit 全部 9 组核心流程、API 24 通过，原 WebKit 依赖下载超时记录保留。该轮 API 36 在测试加载前报告 `Failed to start Dart Development Service`，没有模拟器退出码文件，不能直接归为之前的 132/139 崩溃；原始日志保留待定位。macOS arm64 API 36 的原生通过证据独立保留。

夹具修正后的 `5845a118b68a5ecad5f26476e958c2fa454e7a35` 在全新容器完成 600.291 秒完整混合负载，测试进程与数据库均为 UID 997；认证最大 0.579 秒、采样 RSS 最高 69.4 MiB，真实双入口与本机账本同为 138,638,225 字节。此前一次新夹具在负载启动前读取 root-only unit 文件被拒，已将该摘要移至降权前读取；没有放宽 unit 文件权限，启动失败证据保留。

进一步复核确认产品的日常异地备份也会以 root 读取在线数据库。按现有备份服务相同的 `CAP_DAC_OVERRIDE` 边界调用实际 `BackupManager._copy_database()`，可复现 root/0600 WAL 与服务账号 `SQLITE_CANTOPEN`；在真实已部署面板上，新增安装回归同样首先失败于 WAL 属主为 root。修复在 `run_service()` 共同入口保留一个已完成读取、没有活动事务的服务账号连接，直到所有服务工作线程退出后关闭；不增加 root 能力、不放宽文件权限、不改变数据格式或权限校验。

独立真实权限对照表明，保持服务账号连接后，root 备份期间服务账号仍可读写，WAL 始终为原属主/0600；备份完成后 `wal_checkpoint(TRUNCATE)` 返回 `(0,0,0)`，关闭连接后正常清理。三个生命周期回归中，旧实现有两个失败；修复后的生命周期、watchdog、异地隔离及 HTTPS WebDAV 等 37 项聚焦检查通过，覆盖正常退出、运行异常及启动异常时的连接释放。六平台安装入口的真实 root 备份并发检查与当前完整 CI 均已通过。保留 1,000 用户的隔离实例实际升级后，身份摘要、Hysteria 证书、138,638,225 字节账本和 SQLite 完整性均一致，原已失败的安装回归现通过。新的完整混合短测已在独立空环境完成 601.257 秒：1,000 用户、10 个签名节点、100 条真实双入口 TCP 流、10 个管理客户端及每轮 64 路认证，认证最大 0.601 秒、采样 RSS 最高 67.6 MiB、监听队列 0，双入口累计值与账本同为 138,837,728 字节，PID/重启数未变；只记为 `short-run-only`，正式 48 小时另起新实例。

真实 `hysteria2-panel-offsite-backup.service` 也在候选 `b3d9509` 下通过：保留原 root / `CAP_DAC_OVERRIDE`、文件权限及 systemd 隔离，只给该测试任务提供独立 HTTPS CA。实际完成 PUT、HEAD、GET、MOVE、HEAD、GET、PROPFIND，归档为 140,604 字节、1,000 用户；并行 1,195 次服务账号读写无错，WAL 为服务账号/0600，用户身份、证书、账本、PID 和重启数均不变。测试配置与 CA drop-in 随后撤回，原 timer 状态恢复。下载的真实归档经当前 `validate_archive()` 验证，仍为 formatVersion 1 的五成员 ZIP；20 个运行时表及 4 个机器账本表均无导出行，用户身份摘要与在线库相同，quick check 和外键检查通过。失败前的 root/0600 WAL 原始证据仍保留。

这次实际升级还验证了夹具的恢复边界：负载程序临时配置的 `panel.stability.test` 没有公网 DNS，安装器正确拒绝 ACME 并回滚。自签 CA 不在系统信任库中，严格健康复核保留事务标记；只为该次恢复命令显式提供测试 CA 后，原恢复流程通过并正常清除标记。随后撤回负载程序的四个临时 HTTPS 配置键，恢复该安装夹具原有 HTTP 配置，升级成功。未跳过 TLS 校验、删除事务标记或改变公网证书规则。

## 当前兼容性矩阵

以下远端自动化结果绑定 `b4a6849673356191de4ff459b3f2f7c8fabdf212`，运行时仍为 `b3d9509`；各 Linux 行为独立 systemd 部署环境，不能等同于全部云厂商或物理硬件。原始日志已归档。

| 环境 | 当前证据 | 结论与边界 |
|---|---|---|
| Ubuntu 24.04 / amd64 | 六平台 job 120082822513 | 完整安装、升级、中断恢复、双入口、容量与 WAL 备份回归通过 |
| Ubuntu 24.04 / arm64 | 六平台 job 120082822091 | 同上；本机独立 2 vCPU/2 GiB 持续负载另记 |
| Debian stable / amd64 | 六平台 job 120082822420 | 完整部署回归通过 |
| Debian stable / arm64 | 六平台 job 120082822378 | 完整部署回归通过 |
| Rocky 9 / amd64 | 六平台 job 120082821778 | 完整部署回归通过 |
| Rocky 9 / arm64 | 六平台 job 120082822277 | 完整部署回归通过 |
| Debian 12、13 | 完整 CI 对应安装 job | 两个既有安装检查通过 |
| Debian 11/12/13、Ubuntu 20.04/22.04/24.04、Rocky 8/9 | 完整 CI 八发行版依赖 job | 首次与重复依赖安装通过 |
| Python 3.8 / 3.12 / 3.13 | 完整 CI 三组各 1,066 项 | 每组 1,060 通过、6 跳过；本机 13 项加密/证书补测通过 |
| Flutter 3.47.2 | 固定 SDK `d3b14c876900e553bc736ca19295fc09e3853e8e` | 149 项及 analyze 通过 |
| Chromium | 完整 CI browser-smoke | 完整 36 组交互及 JS 失败路径通过 |
| Firefox 151 / WebKit 26.5 | 附加工作流两个 browser-core job | 各 15 组流程通过；原生菜单 200% 缩放仍未测 |
| Android API 24 / x86_64 | 附加工作流 job 120082639021 | 独立包原生测试通过，固定 `--no-uninstall` |
| Android API 36 / x86_64 | 附加工作流 job 120082639122 | 失败；Lavapipe 对照仍为 gfxstream SIGILL，未完成全部断言 |
| Android API 36 / arm64 | 先前本机固定 Flutter/应用源码测试 | 原生断言通过；属于独立架构证据，不覆盖 x86_64 失败 |
| Android 17 / API 37 手机 | USB 独立包原生 22 秒通过；真实生命周期/切网另有逐步记录 | 强停恢复、令牌轮换、前后台、双面板、真实网络失败/恢复及退出通过；正式 App 元数据未变；剩余逐项 UI 合同仍未测 |
| 连续 48 小时 | 首轮 2,651.449 秒和第二轮 5,417.062 秒失败现场均保留 | 尚未通过；第二轮意外断流待定位，不续算；专用 VM 已停止 |

同一新运行时的实际过载与故障检查已重新执行：64 个未完成认证占满槽位，额外请求 5.011 秒后被拒绝；释放后线程 70→6、FD 85→21，恢复到该进程测试前基线。确实出现一次 watchdog withheld，19.322 秒内恢复心跳，PID/重启数未变。独立 SIGKILL 检查仅强杀隔离面板主进程，3.570 秒后重新 ready；全部用户业务行摘要、TLS、138,837,728 字节本机账本不变，WAL 恢复为服务账号/0600，root 并发备份再次通过。16 MiB tmpfs 的 ENOSPC、SQLite IOERR 和 EROFS 三项也重新通过，恢复与重复采集都精确为 330 字节。这些故障只作用于已经结束短测的实例，不计入或干扰正式连续观察。

当前候选的安装器 ACME 六项隔离协议验收也已重跑通过（Pebble 2.10.1 / Certbot 2.9.0，8.875 秒），所有真实签发、有效证书复用、失败保留和恢复续期证据独立保留；测试结束恢复 hosts 并移除临时回环地址，未调用公网 CA。

同一故障验证实例随后经历专用 Linux VM 的完整停止/启动：Docker 自动拉起容器，五个 systemd 服务均 active，1,000 用户完整业务行摘要、10 个节点、Hysteria 证书和 138,837,728 字节账本保持一致，SQLite quick check 通过。旧用户凭据仍可校验，但重启后未重新报告的节点不再被视为新鲜状态，新认证正确拒绝。该实例随后停止保留，正式观察使用新空镜像实例。

## 第二轮连续观察失败

候选 `b3d9509ff8615c2de942d56dd9b76467d35ff1bf` 在全新空镜像实例于北京时间 **2026-10-23 03:34:26** 开始真实 172,800 秒观察，**05:04:40** 结束，记录总耗时 **5,417.062 秒（约 90 分钟）**。一条真实流收到意外 EOF，错误为 `RuntimeError: unexpected stream close`，整轮已失败；原预计 10 月 25 日 03:34 完成的时间失效。固定 2 vCPU/2 GiB、1,000 用户、10 个签名合成节点、100 条真实双入口流、10 个管理客户端及 64 路认证，未用减载或自动重连掩盖断流。

面板与两个 Hysteria 服务 PID 未变、重启次数均为 0，现有内核日志未见 OOM。最后一次采样为 5,390.862 秒：RSS 80,788 KiB、线程 6、FD 28、队列 0、认证最大 3.099 秒；最大采样间隔 33.292 秒。预热后首小时 RSS 中位数 66,736 KiB 只作失败前基线，不作为首末小时增长合格证据。10 个 Hysteria 客户端日志的优雅退出与服务端断开均发生于清理阶段，不能据此判定它们是初始故障原因。断流先于这次 USB APK 安装和测试连接器启动，也不能把后者当作初始原因。

原状态、指标、10 个客户端日志、服务/数据面/内核日志、进程和容器元数据、完整数据目录及以原数据库 UID 997 创建的一致 SQLite 副本均已保留；quick check 为 ok，仍为 1,000 用户/10 节点。失败容器停机保留并关闭自动重启，专用 VM 于 05:13:28 停止，专属防空闲睡眠进程已停止；没有操作其他任务进程。48 小时必须在根因定位和相关回归后使用新实例从零开始。

现有夹具会吞掉回显服务的 socket 异常，工作线程也只记录异常文本，导致无法从该轮日志区分对端 EOF 与回显闲置超时。新增诊断保留工作线程名称、原堆栈、关闭前累计接收字节/闲置时长、具体错误类型和清理起点；回显仍为原 15 秒期限，客户端和认证边界不变。三个真实 socket 回归已验证部分接收后的 EOF、主动半关闭及实际闲置超时会留下不同证据。这只是诊断缺口修复，尚未解决本次 90 分钟断流，不据此启动新的正式 48 小时观察。

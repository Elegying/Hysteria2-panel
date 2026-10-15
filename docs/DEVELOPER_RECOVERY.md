# 重装电脑后的开发环境与发布恢复

适用于重装开发电脑后继续维护 **原仓库 `Elegying/Hysteria2-panel`**。代码、锁文件、工作流和加密签名备份从 GitHub 恢复；编译器、SDK 和依赖缓存重新安装。无需保留旧 APK、Flutter build、Gradle 或 Pub 缓存。

这份流程不迁移生产服务器。用户数据库、Hysteria 身份、服务器配置和 SSH 凭据应另行按[备份与迁移](BACKUP_AND_MIGRATION.md)保管。

## 1. 确认 GitHub 恢复条件

- 能登录原仓库所有者账号，包括完成两步验证；GitHub 账号的恢复码由账号持有人独立保管。
- 原仓库及 Actions 仍可用；源码主分支保护与 Release 标签规则保留。
- 仓库 Secrets 中保留正式构建使用的四项 `ANDROID_SIGNING_*`，以及加密备份专用的 `ANDROID_SIGNING_BACKUP_AGE_IDENTITY`。
- `ops/android-signing/backup.json.age` 与相邻 `.sha256` 是持久备份。它们包含加密后的原密钥库、两项密码和别名；恢复密钥只存于 GitHub Secrets，不提交源码。

正常恢复只使用备份专用 Secret；不依赖原四项构建 Secrets。即使误删了四项构建 Secrets，也可恢复本地配置后重新设置。若原仓库与全部云端 Secrets 同时丢失，仅有公开密文无法解密。此方案解决电脑重装，不替代 GitHub 账号恢复。

## 2. macOS 安装基础工具并拉取源码

先从 [Homebrew 官方网站](https://brew.sh/)安装 Homebrew，然后执行：

```bash
brew install git gh age python@3.13 openjdk@17
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$(brew --prefix python@3.13)/libexec/bin:$PATH"
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
mkdir -p "$HOME/Developer"
gh repo clone Elegying/Hysteria2-panel "$HOME/Developer/Hysteria2-panel"
cd "$HOME/Developer/Hysteria2-panel"
git status --short --branch
```

把上述 `JAVA_HOME` 与 PATH 配置保存到新电脑的 shell 配置中。不要把密码、GitHub token 或恢复私钥放入 shell 历史。Linux 可使用发行版包管理器安装 Git、GitHub CLI、age、Python 3.8+ 和 JDK 17；正式面板完整部署、systemd 与防火墙测试需要 Linux。

## 3. 一条命令恢复正式签名

在项目根目录执行：

```bash
python3 .github/scripts/android_signing_recovery.py request
```

命令会：

1. 在权限受限的临时目录生成一次性 age 接收密钥。
2. 以原仓库所有者身份手动触发 `Recover Android signing identity`，绑定 `main`。
3. 云端验证持久备份 SHA-256、解密并验证原发布证书、密钥库密码和私钥密码，然后重新加密给这台电脑。
4. 下载只保留一天的加密 Actions artifact；密钥明文和密码不进入日志或 artifact。
5. 本机再次验签并恢复下列文件，完成后清理一次性接收密钥和下载目录。

| 文件 | 作用与权限 |
|---|---|
| `~/.config/hysteria2-manager/signing/hysteria2-manager-release.jks` | 原发布私钥，目录 `0700`、文件 `0600` |
| `mobile/android/signing.properties` | 新电脑绝对路径、别名及密码，`0600`，已被 Git 忽略 |

已存在且一致的文件可重复恢复；不同内容或符号链接会拒绝覆盖。中断、超时或失败后可重新执行，脚本不输出凭据。不要改用新生成的发布密钥。

固定正式证书 SHA-256 以 [Android 发布工作流](../.github/workflows/android-release.yml) 的 `EXPECTED_CERT_SHA256` 为准。恢复脚本直接读取这一值，不另维护一份可漂移的信任配置。

## 4. 安装匹配的 Flutter 和 Android SDK

当前发布工作流使用 Flutter `3.47.2`，精确提交为 `d3b14c876900e553bc736ca19295fc09e3853e8e`，JDK `17`。按源码中工作流的固定版本恢复，不直接切换 Flutter latest。

```bash
git clone --branch 3.47.2 --depth 1 https://github.com/flutter/flutter.git "$HOME/Developer/flutter-3.47.2"
test "$(git -C "$HOME/Developer/flutter-3.47.2" rev-parse HEAD)" = d3b14c876900e553bc736ca19295fc09e3853e8e
export PATH="$HOME/Developer/flutter-3.47.2/bin:$PATH"
flutter --version
flutter config --jdk-dir "$JAVA_HOME"
brew install --cask android-studio
```

打开 Android Studio 完成首次设置，在 SDK Manager 安装 Android SDK、Command-line Tools 和 Build-Tools。当前固定 Flutter 对应 Android Platform `36`、Build-Tools `36.x` 和 NDK `28.2.13676358`；以固定 SDK 的配置为准。默认 SDK 目录为 `~/Library/Android/sdk`。执行以下命令并阅读、接受 SDK 许可：

```bash
export ANDROID_HOME="$HOME/Library/Android/sdk"
flutter config --android-sdk "$ANDROID_HOME"
flutter doctor --android-licenses
flutter precache --android
flutter doctor -v
```

将 Flutter 路径和 `ANDROID_HOME` 保存到 shell 配置。Gradle、插件、SDK/NDK 版本以仓库和固定 Flutter SDK 为准，首次构建需要下载依赖。`local.properties`、Gradle wrapper 可执行文件和依赖缓存由 Flutter 工具准备，不从旧电脑复制绝对路径。

## 5. 验证本地维护和签名构建

在项目根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
bash -n install.sh tests/firewall_integration.sh tests/systemd_integration.sh
python3 .github/scripts/check_markdown_links.py
cd mobile
flutter pub get
git diff --exit-code -- pubspec.lock
flutter analyze --no-pub
flutter test --no-pub
flutter build apk --release --target-platform android-arm64
cd ..
git status --short
```

正式 APK 位于 `mobile/build/app/outputs/flutter-apk/app-release.apk`。使用 Android SDK Build-Tools 中的 `apksigner verify --verbose --print-certs` 检查签名，核对证书与发布工作流一致；用 `aapt dump badging` 核对包名、版本和构建号。构建成功不等于生产节点或真实手机验收完成。

## 6. 继续维护和发布更新

普通维护：新建分支 → 修改并验证 → 推送 → 创建 PR → 等待全部必需检查 → 合并。保持主分支与标签保护，不因换电脑而绕过发布门禁。

新版本准备：

- 面板的 `hy2panel/version.py`、`install.sh`、`CHANGELOG.md` 正式版本必须一致。
- Android 的 `mobile/pubspec.yaml` 更新版本名与 `+构建号`，构建号必须高于已发布包。
- Android 保持 `vip.ssrvpn.hysteria2manager` 与原发布密钥；资产名使用 `Hysteria2-Manager-vX.Y.Z.apk`，只包含 `arm64-v8a`。
- 新版本合并到最新 `main` 后再创建标签；面板标签版本与 Android 应用版本独立。

以下 `vX.Y.Z` 必须替换为**尚未发布**且与面板源码一致的版本，不要重新发布已有版本：

```bash
tag=vX.Y.Z
git switch main
git pull --ff-only origin main
git tag --annotate "$tag" --message "$tag"
git push origin "refs/tags/$tag"
# 等待这个标签 push 触发的全部 CI 成功。
gh workflow run installer-nightly.yml --ref "$tag"
# 等待这个标签的六平台安装矩阵全部成功。
gh release create "$tag" --verify-tag --draft --title "$tag" --generate-notes
gh workflow run android-release.yml --ref "$tag" -f tag="$tag"
# 等待 APK 构建、固定签名核验、版本核验和草稿上传全部成功。
gh workflow run release-signature.yml --ref "$tag" -f tag="$tag"
```

最后一个工作流验证发布门禁、签署并回读安装器/SBOM，再公开 Release。发布时 `tag` 必须仍指向最新 `main`。详细要求、canary 实机验收和回滚见[发布与回滚](DEPLOYMENT.md)。电脑重装不要求重装生产面板，线上更新仍从原仓库 Release 获取。

## 7. 备份维护与故障处理

- `export-current` 只用于备份初始化或显式更新备份；日常恢复使用 `restore-backup`。
- 更新备份时生成专用 age 密钥，把密钥的 `AGE-SECRET-KEY-1...` 行经标准输入保存到 `ANDROID_SIGNING_BACKUP_AGE_IDENTITY`；只把公钥作为工作流参数。
- 下载 `export-current` 的加密 artifact，先本地解密验签并对比原密钥，再把密文及 SHA-256 经 PR 保存到 `ops/android-signing/`。禁止提交解密后的 JSON、密码、`.jks` 或 age 私钥。
- 更换备份恢复密钥之前先验证新旧备份均可恢复；不能只更换 Secret 留下旧密文。
- 恢复提示证书不同、密码错误或备份哈希不符时停止，保留原文件；不要通过重建签名或放宽指纹检查“修复”。
- 恢复工作流仅允许原仓库所有者手动执行，并同时检查原始触发人与重跑人。其他协作者不能使用该入口导出密钥。

加密使用 [age 官方工具](https://github.com/FiloSottile/age)；工作流由 [GitHub workflow_dispatch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow) 手动触发。GitHub 登录、Actions 权限和恢复 Secret 都是恢复前提；它们不会随 `git clone` 进入本地。

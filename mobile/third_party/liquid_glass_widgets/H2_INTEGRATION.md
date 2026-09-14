# Hysteria2 管理客户端集成

来源：用户授权复用 SSRVPN 项目的本地运行时快照（2026-09-14）。SSRVPN 基础提交为 87ec8ace0a294848eea6620e6faec3549e94d3ba；快照包含其尚未提交的渲染优化，因此不能把该提交单独视为此目录的完整来源。

完整保留上游 MIT LICENSE、渲染器归属与 SSRVPN_PATCHES.md。复制范围仅运行时 lib/、shaders/、pubspec.yaml 和归属说明；没有复制账号、服务器配置或客户端业务。

H2 适配：一个条件语句补齐大括号以满足当前项目 lint，无逻辑变化。应用侧 h2_glass_capture.dart 与 h2_drifting_background.dart 移植自 SSRVPN，改名以隔离项目。固定 Premium 质量，不启用低画质自动降级。对应的取样调度和图层复用测试一起移植。

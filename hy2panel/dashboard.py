"""Dashboard rendering isolated from the HTTP transport entrypoint."""

import html
import json
import time
import urllib.parse
from dataclasses import dataclass


def select_dashboard_users(
    all_users,
    snapshot,
    sort_by="",
    sort_order="",
    search_query="",
    status_filter="",
    online_filter="",
    udp443_filter="",
):
    sort_by = sort_by if sort_by in {"traffic", "online"} else ""
    sort_order = sort_order if sort_order in {"asc", "desc"} else ""
    search_query = str(search_query)[:96]
    status_filter = status_filter if status_filter in {"enabled", "disabled"} else ""
    online_filter = online_filter if online_filter in {"active", "inactive"} else ""
    udp443_filter = udp443_filter if udp443_filter in {"allowed", "blocked"} else ""
    online = snapshot.get("online", {})
    query = search_query.casefold().strip()
    filtered = []
    for user in all_users:
        online_count = int(online.get(user["name"], 0) or 0)
        if query and query not in user["name"].casefold():
            continue
        if status_filter and bool(user["enabled"]) != (status_filter == "enabled"):
            continue
        if online_filter and (online_count > 0) != (online_filter == "active"):
            continue
        if udp443_filter and bool(user["allow_udp_443"]) != (
            udp443_filter == "allowed"
        ):
            continue
        filtered.append(user)
    listed_users = sorted(
        filtered,
        key=lambda item: (item["created_at"], item["id"]),
        reverse=True,
    )
    if sort_by == "traffic" and sort_order:
        listed_users = sorted(
            filtered,
            key=lambda item: item["tx_bytes"] + item["rx_bytes"],
            reverse=sort_order == "desc",
        )
    elif sort_by == "online" and sort_order:
        listed_users = sorted(
            filtered,
            key=lambda item: int(online.get(item["name"], 0) or 0),
            reverse=sort_order == "desc",
        )
    return {
        "users": listed_users,
        "filtered_total": len(listed_users),
        "total_users": len(all_users),
        "sort_by": sort_by,
        "sort_order": sort_order,
        "search_query": search_query,
        "status_filter": status_filter,
        "online_filter": online_filter,
        "udp443_filter": udp443_filter,
    }


@dataclass(frozen=True)
class DashboardContext:
    logger: object
    default_device_limit: int
    default_traffic_limit_bytes: int
    panel_version: str
    max_state_age_seconds: int
    bytes_to_gib_input: object
    human_bytes: object
    stat_int: object
    summarize_dashboard: object


def render_dashboard(
    self,
    session,
    sort_by="",
    sort_order="",
    search_query="",
    status_filter="",
    online_filter="",
    udp443_filter="",
    context=None,
):
    if context is None:
        raise ValueError("dashboard rendering context is required")
    LOGGER = context.logger
    DEFAULT_DEVICE_LIMIT = context.default_device_limit
    DEFAULT_TRAFFIC_LIMIT_BYTES = context.default_traffic_limit_bytes
    PANEL_VERSION = context.panel_version
    bytes_to_gib_input = context.bytes_to_gib_input
    _human_bytes = context.human_bytes
    _stat_int = context.stat_int
    summarize_dashboard = context.summarize_dashboard
    try:
        snapshot = self.app.usage_manager.snapshot()
    except Exception:
        LOGGER.exception("stats snapshot failed")
        snapshot = {"traffic": {}, "online": {}, "available": False}
    all_users = self.app.database.list_proxy_users_for_usage()
    user_selection = select_dashboard_users(
        all_users,
        snapshot,
        sort_by,
        sort_order,
        search_query,
        status_filter,
        online_filter,
        udp443_filter,
    )
    listed_users = user_selection["users"]
    sort_by = user_selection["sort_by"]
    sort_order = user_selection["sort_order"]
    search_query = user_selection["search_query"]
    status_filter = user_selection["status_filter"]
    online_filter = user_selection["online_filter"]
    udp443_filter = user_selection["udp443_filter"]
    summary = summarize_dashboard([user["name"] for user in all_users], snapshot)
    try:
        service_status = self.app.service_controller.status()
    except Exception:
        LOGGER.exception("service status failed")
        service_status = "unknown"
    try:
        if hasattr(self.app.egress_policy_controller, "inspect"):
            egress_details = self.app.egress_policy_controller.inspect()
            egress_policy = egress_details["state"]
            configured_egress_policy = egress_details.get("configured_policy")
        else:
            egress_policy = self.app.egress_policy_controller.status()
            configured_egress_policy = egress_policy
    except Exception:
        LOGGER.exception("egress policy status failed")
        egress_policy = "unknown"
        configured_egress_policy = None
    try:
        resources = self.app.system_metrics.snapshot()
        metrics_available = True
    except Exception:
        LOGGER.exception("system metrics failed")
        resources = {
            "cpu_percent": None,
            "memory_percent": None,
            "memory_used": 0,
            "memory_total": 0,
            "disk_percent": None,
            "disk_used": 0,
            "disk_total": 0,
            "uptime": "不可用",
            "tcp_congestion_control": "不可用",
            "default_qdisc": "不可用",
        }
        metrics_available = False
    csrf = html.escape(session["csrf_token"], quote=True)
    rows = []
    for user in listed_users:
        name = user["name"]
        traffic = snapshot.get("traffic", {}).get(name, {})
        online = _stat_int(snapshot.get("online", {}).get(name, 0))
        device_limit = int(user["device_limit"])
        over_device_limit = online > device_limit
        used = _stat_int(traffic.get("tx", 0)) + _stat_int(traffic.get("rx", 0))
        limit = user["traffic_limit_bytes"]
        percent = min(100.0, 100.0 * used / limit) if limit else 0.0
        enabled = bool(user["enabled"])
        action_label = "禁用" if enabled else "启用"
        action_class = "ghost" if enabled else "success"
        rows.append(
            """<tr data-user-name="{search_name}" data-enabled="{enabled_value}" data-online="{online}" data-device-limit="{device_limit}" data-allow-udp443="{allow_udp_443}" data-over-device-limit="{over_device_limit}"><td data-label="名称" data-live-user-name><strong{name_class}>{name}</strong>{limit_alert}</td>
<td data-label="状态"><span class="status {state_class}">{state}</span></td><td data-label="在线设备"><span data-live-user-online>{online}</span> / {device_limit}</td><td data-label="上传 / 下载">{tx} / {rx}</td>
<td class="traffic-cell" data-label="总流量"><progress max="100" value="{percent:.1f}" aria-label="{name} 总流量使用 {percent:.1f}%"></progress><div class="traffic-label"><span>{used} / {limit}</span><span>{percent:.1f}%</span></div></td>
<td data-label="操作"><div class="actions">
<form class="inline" method="post" action="/users/{id}/share" data-share-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><input type="hidden" name="inline" value="1"><button type="submit">分享</button></form>
<form class="inline" method="post" action="/users/{id}/share" data-qr-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><input type="hidden" name="inline" value="1"><input type="hidden" name="qr" value="1"><button class="secondary" type="submit">二维码</button></form>
<form class="inline" method="post" action="/users/{id}/toggle"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="{action_class}" type="submit">{action}</button></form>
<form class="inline" method="post" action="/users/{id}/rotate" data-confirm="轮换后旧连接地址会立即失效，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="warning" type="submit">改密</button></form>
<form class="inline" method="post" action="/users/{id}/reset" data-confirm="确定重置该用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="ghost" type="submit">重置</button></form>
<form class="inline" method="post" action="/users/{id}/delete" data-confirm="确定删除用户 {name} 吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="generation" value="{generation}"><button class="danger" type="submit">删除</button></form>
</div></td></tr>""".format(
                name=html.escape(name),
                search_name=html.escape(name, quote=True),
                name_class=' class="over-limit-name"' if over_device_limit else "",
                limit_alert='<span class="limit-alert" data-live-limit-alert{}>客户端实例超限</span>'.format(
                    "" if over_device_limit else " hidden"
                ),
                over_device_limit="1" if over_device_limit else "0",
                enabled_value="1" if enabled else "0",
                allow_udp_443="1" if user["allow_udp_443"] else "0",
                state="启用" if enabled else "禁用",
                state_class="enabled" if enabled else "disabled",
                online=online,
                device_limit=device_limit,
                tx=_human_bytes(traffic.get("tx", 0)),
                rx=_human_bytes(traffic.get("rx", 0)),
                used=_human_bytes(used),
                limit=_human_bytes(limit),
                percent=percent,
                id=user["id"],
                generation=user["generation"],
                csrf=csrf,
                action=action_label,
                action_class=action_class,
            )
        )
    if not rows:
        empty_message = (
            "没有符合当前筛选条件的用户。"
            if all_users
            else "暂无用户，请先创建。"
        )
        rows.append(
            '<tr><td colspan="6" class="muted empty-state">{}</td></tr>'.format(
                empty_message
            )
        )
    edit_options = "".join(
        """<option value="{id}" data-generation="{generation}" data-device-limit="{device_limit}" data-traffic-limit-gb="{traffic_limit_gb}" data-allow-udp443="{allow_udp_443}">{name}</option>""".format(
            id=user["id"],
            generation=user["generation"],
            device_limit=user["device_limit"],
            traffic_limit_gb=max(1, user["traffic_limit_bytes"] // 1024**3),
            allow_udp_443="1" if user["allow_udp_443"] else "0",
            name=html.escape(user["name"]),
        )
        for user in listed_users
    )
    first_edit_user = listed_users[0] if listed_users else None
    sort_marks = {"asc": "↑", "desc": "↓"}
    sort_aria = {"asc": "ascending", "desc": "descending"}
    online_sort_order = sort_order if sort_by == "online" else ""
    online_sort_next = "asc" if online_sort_order == "desc" else "desc"
    online_sort_mark = sort_marks.get(online_sort_order, "⇅")
    online_sort_aria = sort_aria.get(online_sort_order, "none")
    traffic_sort_order = sort_order if sort_by == "traffic" else ""
    traffic_sort_next = "asc" if traffic_sort_order == "desc" else "desc"
    traffic_sort_mark = sort_marks.get(traffic_sort_order, "⇅")
    traffic_sort_aria = sort_aria.get(traffic_sort_order, "none")
    base_query = {
        key: value
        for key, value in {
            "q": search_query,
            "status": status_filter,
            "online": online_filter,
            "udp443": udp443_filter,
        }.items()
        if value
    }

    def dashboard_url(**changes):
        values = dict(base_query)
        if sort_by and sort_order:
            values.update({"sort": sort_by, "order": sort_order})
        values.update(changes)
        values = {key: value for key, value in values.items() if value not in {"", None}}
        query_string = urllib.parse.urlencode(values)
        return "/?" + query_string if query_string else "/"

    online_sort_href = dashboard_url(sort="online", order=online_sort_next)
    traffic_sort_href = dashboard_url(sort="traffic", order=traffic_sort_next)
    if user_selection["filtered_total"] == user_selection["total_users"]:
        user_count_text = "共 {} 位用户".format(user_selection["total_users"])
    else:
        user_count_text = "显示 {} / 全部 {} 位用户".format(
            user_selection["filtered_total"], user_selection["total_users"]
        )
    filter_values = {
        "search_query": html.escape(search_query, quote=True),
        "status_enabled": " selected" if status_filter == "enabled" else "",
        "status_disabled": " selected" if status_filter == "disabled" else "",
        "online_active": " selected" if online_filter == "active" else "",
        "online_inactive": " selected" if online_filter == "inactive" else "",
        "udp443_allowed": " selected" if udp443_filter == "allowed" else "",
        "udp443_blocked": " selected" if udp443_filter == "blocked" else "",
    }
    machine_stats = snapshot.get("machine_stats", {})
    machine_origins = machine_stats.get("origins", [])
    budget_origin_ids = [
        origin["origin_id"]
        for origin in machine_origins
        if origin.get("kind") in {"local", "remote"}
    ]
    try:
        machine_budgets = {
            budget["origin_id"]: budget
            for budget in self.app.database.list_origin_budgets(
                budget_origin_ids, int(time.time())
            )
        }
    except (TypeError, ValueError):
        LOGGER.exception("machine traffic budgets failed")
        machine_budgets = {}
    machine_status_labels = {
        "fresh": ("新鲜", "ok"),
        "stale": ("数据过期", "warning"),
        "standby": ("已停用", "muted"),
        "revoked": ("已撤销", "bad"),
        "unavailable": ("等待上报", "warning"),
        "history": ("历史记录", "muted"),
    }

    online_note = (
        '<small class="metric-warning" data-live-online-note>设备统计暂不完整：部分节点上报已过期</small>'
        if not snapshot.get("online_complete", True)
        else '<small class="muted" data-live-online-note>按 Hysteria 客户端实例统计</small>'
    )
    machine_rows = []
    machine_budget_dialogs = []
    for origin in machine_origins:
        online_state = origin.get("online_state", "history")
        status_label, status_class = machine_status_labels.get(
            online_state, ("状态未知", "warning")
        )
        online_devices = origin.get("online_devices")
        if online_devices is None:
            last_known = int(origin.get("last_known_online_devices") or 0)
            online_text = "—（上次 {}）".format(last_known) if last_known else "—"
        else:
            online_text = str(int(online_devices))
        observed_at = origin.get("observed_at")
        observed_text = (
            time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(int(observed_at))
            )
            if observed_at
            else "尚未上报"
        )
        kind_label = {
            "local": "面板节点",
            "remote": "远端数据节点",
            "legacy": "历史归属",
        }.get(origin.get("kind"), "历史归属")
        budget = machine_budgets.get(origin["origin_id"])
        if budget is not None:
            budget_status = {
                "disabled": ("未设置", "muted"),
                "normal": ("正常", "ok"),
                "warning": ("接近预算", "warning"),
                "exhausted": ("预算已用尽", "bad"),
            }.get(budget["status"], ("状态未知", "warning"))
            limit_gib = (
                int(budget["limit_bytes"]) // 1024**3
                if budget["limit_bytes"]
                else 0
            )
            used_text = _human_bytes(budget["used_bytes"])
            limit_text = (
                _human_bytes(budget["limit_bytes"])
                if budget["limit_bytes"]
                else "不限"
            )
            dialog_id = "budget-dialog-{}".format(
                origin["origin_id"].split(":", 1)[-1]
            )
            budget_action = """<button class="compact-button secondary machine-budget-edit" type="button" data-dialog-open="{dialog_id}">编辑预算</button>""".format(
                dialog_id=html.escape(dialog_id, quote=True)
            )
            machine_budget_dialogs.append(
                """<dialog id="{dialog_id}" class="migration-dialog budget-dialog" aria-labelledby="{dialog_id}-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="{dialog_id}-title">编辑 {name} 的流量预算</h2><p class="muted">调整本周期基线、月预算和告警阈值。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭预算编辑弹窗">关闭</button></div><form class="budget-form budget-dialog-form" method="post" action="/usage-origins/{origin_id}/budget"><input type="hidden" name="csrf" value="{csrf}"><label>月预算 GiB<input name="limit_gib" type="number" min="0" max="8589934591" value="{limit_gib}" required></label><label>当前已用 GiB<input name="used_gib" type="number" min="0" max="8589934591" step="0.000000000001" value="{used_gib}" required></label><label>告警 %<input name="warning_percent" type="number" min="1" max="99" value="{warning}" required></label><label>每月重置日<input name="reset_day" type="number" min="1" max="31" value="{reset_day}" required></label><button type="submit">保存预算与基线</button></form></div></dialog>""".format(
                    dialog_id=html.escape(dialog_id, quote=True),
                    name=html.escape(
                        str(origin.get("display_name") or "未命名节点")
                    ),
                    origin_id=html.escape(origin["origin_id"], quote=True),
                    csrf=csrf,
                    limit_gib=limit_gib,
                    used_gib=bytes_to_gib_input(budget["used_bytes"]),
                    warning=budget["warning_percent"],
                    reset_day=budget["reset_day"],
                )
            )
            budget_line = "{used} / {limit} · {percent:.1f}%".format(
                used=used_text,
                limit=limit_text,
                percent=budget["percent"],
            )
            budget_detail = "本周期 {} 至 {}（UTC） · 下次重置 {}".format(
                budget["period_start"],
                budget["period_end"],
                budget["next_reset_date"],
            )
            progress_value = max(0.0, min(100.0, float(budget["percent"])))
        else:
            budget_status = ("历史记录", "muted")
            budget_line = "升级前未归属历史 · 不计入节点预算"
            budget_detail = "可以单独清理这条历史，不影响用户流量与已归属节点。"
            progress_value = 0.0
            budget_action = """<form class="legacy-cleanup-form" method="post" action="/usage-origins/legacy-unattributed/delete" data-confirm="只会删除这条未归属历史，不会删除用户流量或已归属节点统计。确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="confirm" value="DELETE_UNATTRIBUTED"><button class="compact-button danger" type="submit">删除历史</button></form>""".format(
                csrf=csrf
            )
        machine_rows.append(
            """<article class="machine-budget-row" data-origin-id="{origin_id}"><div class="machine-budget-head"><div><strong>{name}</strong><small class="muted">{kind} · <span class="{status_class}" data-live-machine-state>{status}</span></small></div><span class="machine-online"><strong data-live-machine-online>{online}</strong> 台在线</span></div><progress max="100" value="{progress:.4f}" aria-label="{name} 流量预算使用比例"></progress><div class="machine-budget-usage"><strong class="{budget_class}">{budget_line}</strong><span class="muted">上传 {tx} · 下载 {rx}</span></div><div class="machine-budget-meta"><small class="muted">{budget_detail} · 最后上报 <span data-live-machine-observed>{observed}</span></small>{budget_action}</div></article>""".format(
                origin_id=html.escape(origin["origin_id"], quote=True),
                name=html.escape(str(origin.get("display_name") or "未命名节点")),
                kind=kind_label,
                status_class=status_class,
                status=status_label,
                online=online_text,
                progress=progress_value,
                budget_class=budget_status[1],
                budget_line=budget_line,
                tx=_human_bytes(int(origin.get("tx_bytes") or 0)),
                rx=_human_bytes(int(origin.get("rx_bytes") or 0)),
                budget_detail=budget_detail,
                observed=observed_text,
                budget_action=budget_action,
            )
        )
    machine_warning = (
        '<p class="notice machine-warning"><strong>设备统计暂不完整：</strong>过期节点的上次设备数仅供参考，不计入当前总数；流量仍按幂等批次继续结算。</p>'
        if machine_stats.get("has_stale_online")
        else ""
    )
    machine_stats_section = "" if not machine_origins else (
        """<section class="card machine-stats"><div class="section-head machine-section-head"><div><h2>节点统计与流量预算</h2><p class="muted">按面板节点与远程节点统计当前周期用量。</p></div><span class="machine-count">{count} 台机器</span></div>{warning}<div class="machine-budget-list">{rows}</div>{dialogs}</section>""".format(
            warning=machine_warning,
            count=len(machine_origins),
            rows="".join(machine_rows),
            dialogs="".join(machine_budget_dialogs),
        )
    )
    stats_state = "正常" if summary["service_available"] else "异常"
    service_label, service_class = {
        "active": ("Hysteria 运行中", ""),
        "inactive": ("Hysteria 已停止", " off"),
        "failed": ("Hysteria 启动失败", " failed"),
        "activating": ("Hysteria 启动中", " pending"),
        "deactivating": ("Hysteria 停止中", " pending"),
        "reloading": ("Hysteria 重载中", " pending"),
    }.get(service_status, ("Hysteria 状态未知", " pending"))
    full_enabled = egress_policy == "full"
    if full_enabled:
        egress_state = "FULL 已开启"
        egress_state_class = " on"
        egress_target = "web"
        egress_action = "关闭"
        egress_confirm = (
            "关闭 FULL 会切换为 WEB 端口白名单，并短暂重启全部 Hysteria 连接，确定继续吗？"
        )
    elif egress_policy == "web":
        egress_state = "FULL 已关闭"
        egress_state_class = ""
        egress_target = "full"
        egress_action = "开启"
        egress_confirm = (
            "开启 FULL 会允许代理访问公网全部端口（包括 BT/PT 和邮件端口），"
            "并短暂重启全部 Hysteria 连接，确定继续吗？"
        )
    elif egress_policy == "inconsistent":
        egress_state = "FULL 状态不一致"
        egress_state_class = " unknown"
        egress_target = (
            configured_egress_policy
            if configured_egress_policy in {"web", "full"}
            else "web"
        )
        egress_action = "修复"
        egress_confirm = (
            "当前环境、ACL 或运行状态不一致；修复会重新应用已配置策略并短暂重启运行中的 Hysteria 连接，确定继续吗？"
        )
    else:
        egress_state = "FULL 状态未知"
        egress_state_class = " unknown"
        egress_target = "web"
        egress_action = "修复"
        egress_confirm = (
            "当前无法证明出站策略；修复会应用安全的 WEB 策略并短暂重启运行中的 Hysteria 连接，确定继续吗？"
        )
    top_users = sorted(
        all_users,
        key=lambda item: item["tx_bytes"] + item["rx_bytes"],
        reverse=True,
    )[:5]
    rank_rows = "".join(
        '<div class="rank-row"><span class="rank-number">#{rank}</span><span class="rank-main"><span class="rank-name">{name}</span><span class="rank-traffic">{traffic}</span></span></div>'.format(
            rank=index,
            name=html.escape(user["name"]),
            traffic=_human_bytes(user["tx_bytes"] + user["rx_bytes"]),
        )
        for index, user in enumerate(top_users, 1)
    ) or '<p class="muted">暂无用户流量。</p>'
    update = self.app.update_result
    if update:
        update_text = (
            '发现新版本 <a href="{url}">{latest}</a>'
            if update["update_available"]
            else "当前已是最新版本"
        ).format(url=html.escape(update["url"], quote=True), latest=html.escape(update["latest"]))
    else:
        update_text = "尚未检查远程版本"
    try:
        update_status = self.app.update_controller.status()
    except Exception:
        LOGGER.exception("update status failed")
        update_status = {
            "state": "failed",
            "message": "暂时无法读取更新任务状态",
        }
    update_state = update_status.get("state", "idle")
    if update_state not in {"idle", "queued", "running", "success", "failed"}:
        update_state = "failed"
    update_status_text = html.escape(str(update_status.get("message", "")))
    update_action = ""
    update_active = update_state in {"queued", "running"}
    if update_active or (update and update["update_available"]):
        update_action = """<form method="post" action="/updates/apply" data-update-form data-confirm="在线更新会短暂重启面板与 Hysteria 服务，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button success" type="submit"{disabled}>{label}</button></form>""".format(
            csrf=csrf,
            disabled=" disabled" if update_active else "",
            label="正在更新…" if update_active else "立即更新",
        )
    certificate_status = self.app.health_monitor.certificate_status()
    certificate_remaining = certificate_status["seconds_remaining"]
    if certificate_remaining is None:
        certificate_text = "未监测"
        certificate_class = "bad"
    elif certificate_status["level"] == "not-yet-valid":
        certificate_text = "尚未生效"
        certificate_class = "bad"
    elif certificate_remaining <= 0:
        certificate_text = "已过期"
        certificate_class = "bad"
    else:
        certificate_days = max(1, (certificate_remaining + 86399) // 86400)
        certificate_prefix = {
            "critical": "紧急",
            "warning": "警告",
            "notice": "注意",
        }.get(certificate_status["level"], "正常")
        certificate_text = "{} · 剩余 {} 天".format(
            certificate_prefix, certificate_days
        )
        certificate_class = (
            "bad"
            if certificate_status["level"] in {"critical", "warning", "expired"}
            else "ok"
        )
    node_rows = []
    current_time = int(time.time())
    for node in self.app.database.list_nodes():
        status = node["status"]
        if status == "revoked":
            continue
        lifecycle_state = node.get("lifecycle_state") or "active"
        expired = bool(
            status == "pending_registration"
            and node.get("expires_at")
            and node["expires_at"] <= current_time
        )
        verified = node.get("verified_at") is not None
        heartbeat_fresh = bool(
            verified
            and node.get("last_heartbeat_at")
            and current_time - node["last_heartbeat_at"]
            <= context.max_state_age_seconds
        )
        if lifecycle_state == "disconnecting":
            status_label, status_class = "正在一键断连", "warning"
        elif (
            verified
            and node.get("policy_state") == "protocol_ready"
            and node.get("data_plane_state")
            in {"direct_canary_passed", "dns_admitted"}
        ):
            status_label, status_class = (
                ("已对接 · 在线", "ok")
                if heartbeat_fresh
                else ("已对接 · 离线", "warning")
            )
        elif expired:
            status_label, status_class = "对接代码已过期", "bad"
        else:
            status_label, status_class = "正在对接", "warning"
        details = [node.get("observed_ip") or node.get("expected_ip") or "公网 IP 未知"]
        if node.get("last_heartbeat_at"):
            details.append(
                "最后心跳：{}".format(
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(node["last_heartbeat_at"]),
                    )
                )
            )
        if lifecycle_state == "disconnecting":
            details.append("远端正在卸载；收到签名回执后自动从当前列表隐藏")
        elif status == "pending_registration":
            details.append("请在目标服务器以 root 粘贴运行生成的代码")
        else:
            details.append("DNS 由你自行维护；面板不会检查或修改")
        agent_version_parts = str(node.get("agent_version") or "").split(".")
        agent_supports_disconnect = bool(
            len(agent_version_parts) == 3
            and all(part.isdigit() for part in agent_version_parts)
            and tuple(int(part) for part in agent_version_parts) >= (0, 39, 0)
        )
        if verified and not agent_supports_disconnect:
            details.append("旧版 Agent 不支持安全的一键断连")
        can_disconnect = bool(
            status == "pending_verification"
            and verified
            and agent_supports_disconnect
            and node.get("policy_state") == "protocol_ready"
            and node.get("data_plane_state")
            in {"data_plane_installed", "direct_canary_passed", "dns_admitted"}
            and lifecycle_state in {"active", "draining"}
            and heartbeat_fresh
            and int(node.get("pending_commands") or 0) == 0
        )
        can_delete = bool(not heartbeat_fresh and lifecycle_state != "disconnecting")
        if can_disconnect:
            disconnect_action = """<form method="post" action="/nodes/{node_id}/disconnect" data-confirm="一键断连会立即停止该服务器上的对接业务，并卸载本项目安装的服务、身份、配置、状态、防火墙规则和网络参数。确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">一键断连</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        else:
            disconnect_action = '<button class="danger compact-button" type="button" disabled aria-disabled="true" title="仅已完成对接、在线且无待处理命令的节点可一键断连">一键断连</button>'
        if can_delete:
            delete_action = """<form method="post" action="/nodes/{node_id}/delete" data-confirm="仅当服务器失联、无法执行一键断连时使用。此操作只会吊销并删除面板中的当前对接，不会清理失联服务器上的文件。确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary compact-button" type="submit">删除对接</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        else:
            delete_action = '<button class="secondary compact-button" type="button" disabled aria-disabled="true" title="节点在线时请使用一键断连；删除对接只用于失联节点">删除对接</button>'
        node_actions = disconnect_action + delete_action
        node_rows.append(
            """<article class="node-row"><div><strong>{name}</strong><small class="muted">{detail}</small></div><span class="{status_class}">{status_label}</span><div class="node-actions">{node_actions}</div></article>""".format(
                name=html.escape(node["name"]),
                detail=html.escape(" · ".join(details)),
                status_class=status_class,
                status_label=status_label,
                node_actions=node_actions,
            )
        )
    node_rows_html = "".join(node_rows) or '<p class="muted">尚未创建对接节点。</p>'
    onboarding_disabled = (
        ""
        if self.app.secure_cookies and self.app.node_enrollment_service is not None
        else " disabled title=\"请先为面板启用 HTTPS\""
    )
    offsite_backup_label = "未配置"
    offsite_backup_class = "muted"
    offsite_backup_detail = "配置 root-only HTTPS WebDAV 后每天自动上传并保留 30 天"
    try:
        status_path = self.app.offsite_backup_status_path
        if status_path.is_file() and not status_path.is_symlink():
            raw_status = status_path.read_bytes()
            if len(raw_status) > 4096:
                raise ValueError("offsite backup status is too large")
            offsite_status = json.loads(raw_status.decode("utf-8"))
            state = offsite_status.get("state")
            if state == "success":
                offsite_backup_label = "最近备份成功"
                offsite_backup_class = "ok"
                offsite_backup_detail = "每天一次，远端精确保留 30 天"
            elif state == "failed":
                offsite_backup_label = "最近备份失败"
                offsite_backup_class = "bad"
                offsite_backup_detail = "请检查 systemctl status hysteria2-panel-offsite-backup.service"
            elif state != "not_configured":
                raise ValueError("offsite backup status is invalid")
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        LOGGER.warning("offsite backup status is unreadable")
        offsite_backup_label = "状态不可用"
        offsite_backup_class = "warning"
        offsite_backup_detail = "状态文件无效；备份不会被误报为成功"
    content = """<header class="topbar"><span class="eyebrow brand">HYSTERIA CONTROL CENTER</span><h1>Hysteria 2 用户管理面板</h1><span class="topbar-spacer"></span>
<span class="pill">服务状态 <strong>{service_label}</strong></span><span class="pill">最近刷新 <strong data-live-refreshed>{refreshed}</strong></span><span class="pill">当前用户 <strong>{total_users}</strong></span>
<button class="secondary topbar-action" type="button" data-dialog-open="migration-dialog">数据迁移</button><form class="logout-form" method="post" action="/logout"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary" type="submit">退出登录</button></form></header>
<section class="metrics" aria-label="服务概览">
<div class="metric"><span>不活跃用户</span><strong>{inactive_users}</strong><small class="muted">上传与下载均为 0</small></div>
<div class="metric"><span>在线设备</span><strong data-live-online-total aria-live="polite">{online_devices}</strong>{online_note}</div>
<div class="metric"><span>总上传流量</span><strong>{total_tx}</strong><small class="muted">全部用户累计上传</small></div>
<div class="metric"><span>总下载流量</span><strong>{total_rx}</strong><small class="muted">全部用户累计下载</small></div>
</section>
{machine_stats_section}
<section class="operations dashboard-trio">
<article class="card"><div class="section-head"><div><h2>服务控制</h2><p class="muted">启停、重启和版本检查集中在这里。</p></div><span class="service-badge{service_class}">{service_label}</span></div>
<div class="button-row service-actions"><form method="post" action="/service/start"><input type="hidden" name="csrf" value="{csrf}"><button class="success" type="submit">启动</button></form>
<form method="post" action="/service/restart" data-confirm="确定重启 Hysteria 服务吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="warning" type="submit">重启</button></form>
<form method="post" action="/service/stop" data-confirm="停止后所有连接会中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">停止</button></form><a class="button secondary" href="/">刷新</a><button class="secondary" type="button" data-dialog-open="node-onboarding-dialog"{onboarding_disabled}>对接管理</button></div>
<div class="service-details primary-details"><div class="detail compact-detail"><span class="muted">流量统计</span><strong class="{stats_class}">{stats}</strong></div><div class="detail compact-detail port-detail"><div><span class="muted">服务端口</span><strong>UDP {port}</strong></div><form class="egress-control" method="post" action="/egress/{egress_target}" data-egress-form data-confirm="{egress_confirm}"><input type="hidden" name="csrf" value="{csrf}"><span class="egress-state{egress_state_class}" data-egress-state>{egress_state}</span><button class="egress-switch{egress_state_class}" type="submit" aria-pressed="{egress_checked}" aria-label="{egress_action} FULL 出口策略"><span class="egress-switch-track" aria-hidden="true"><span></span></span><span class="egress-switch-action">{egress_action}</span></button></form></div></div>
<div class="service-details version-details"><div class="detail compact-detail bbr-detail"><span class="muted">BBR 状态</span><strong class="ok">Hysteria BBR</strong><small class="muted">standard · 内核 {tcp_cc} / {qdisc}</small></div><div class="detail compact-detail version-panel"><div class="version-row"><div><span class="muted">当前版本</span><strong>v{version}</strong></div><div class="button-row version-actions"><form method="post" action="/updates/check"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button" type="submit">检查更新</button></form>{update_action}</div></div><p class="muted">{update_text}</p><p class="update-state" data-update-status data-state="{update_state}" role="status" aria-live="polite">{update_status_text}</p></div></div></article>
<article class="card"><div class="section-head"><div><h2>系统资源</h2><p class="muted">服务器实时负载与容量。</p></div><form class="system-actions" method="post" action="/system/reboot" data-confirm="重启服务器后，所有节点连接会暂时中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">重启服务器</button></form></div><div class="resource-grid">
<div class="resource"><span class="muted">CPU 使用率</span><strong>{cpu}</strong></div><div class="resource"><span class="muted">内存占用</span><strong>{memory}</strong><small class="muted">{memory_used} / {memory_total}</small></div>
<div class="resource"><span class="muted">磁盘占用</span><strong>{disk}</strong><small class="muted">{disk_used} / {disk_total}</small></div><div class="resource"><span class="muted">运行时长</span><strong>{uptime}</strong></div>
<div class="resource certificate-resource"><span class="muted">节点证书</span><strong class="{certificate_class}">{certificate_text}</strong></div></div></article>
<article class="card traffic-card"><div class="section-head"><div><h2>高流量用户</h2><p class="muted">当前累计总流量最高的 5 个账号。</p></div></div><div class="rank-list">{rank_rows}</div></article>
</section>
<dialog id="node-onboarding-dialog" class="migration-dialog node-onboarding-dialog" aria-labelledby="node-onboarding-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="node-onboarding-title">第二台服务器对接</h2><p class="muted">生成代码后，在目标服务器以 root 粘贴运行一次即可。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭节点操作弹窗">关闭</button></div>
<p class="notice"><strong>生成前请先完成 DNS 设置：</strong>请自行把需要的域名解析到目标服务器公网 IP。面板不会查询、修改或等待 DNS，也不会把 DNS 作为对接成功条件。</p>
<form class="node-enrollment-grid" method="post" action="/node-enrollments" data-node-enrollment-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="mode" value="join"><input type="hidden" name="ttl_minutes" value="10"><div><label for="node-name">节点名称</label><input id="node-name" name="name" required maxlength="64" placeholder="例如：香港分流-02"></div><div><label for="node-expected-ip">目标服务器公网 IP</label><input id="node-expected-ip" name="expected_ip" inputmode="text" required placeholder="例如：203.0.113.10"></div><button type="submit"{onboarding_disabled}>一键对接</button></form>
<section class="enrollment-result" data-node-enrollment-result hidden><label for="node-deployment-code">在目标服务器粘贴运行</label><textarea id="node-deployment-code" rows="12" readonly spellcheck="false"></textarea><p class="muted" data-node-enrollment-expiry role="status"></p></section>
<div class="node-list-head"><h3>节点状态</h3><span class="muted">刷新页面可获取最新注册状态</span></div><div class="node-list">{node_rows}</div></div></dialog>
<dialog id="migration-dialog" class="migration-dialog" aria-labelledby="migration-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="migration-title">用户数据迁移</h2><p class="muted">完整备份或恢复节点身份与全部用户数据。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭数据迁移弹窗">关闭</button></div>
<p class="notice"><strong>重要：</strong>备份包含代理用户、累计流量、签名密钥、证书和私钥，请离线妥善保存。恢复时必须保持节点域名 <code>{public_host}</code> 与 UDP 端口 <code>{port}</code> 不变，旧客户端配置才可继续使用；更换服务器时先通过服务器 IP 登录新面板完成恢复并验证，再切换 DNS。当前面板管理员账号不会被替换。</p>
<div class="migration-grid"><article class="detail"><h3>一键备份</h3><p class="muted">生成经过完整性校验的 ZIP 文件并直接下载。</p><form method="post" action="/backup"><input type="hidden" name="csrf" value="{csrf}"><button type="submit">下载完整备份</button></form></article>
<article class="detail"><h3>一键恢复</h3><p class="muted">上传本面板生成的 ZIP。恢复会短暂重启服务，完成后旧会话失效。</p><form data-restore-form data-csrf="{csrf}"><label for="restore-file">ZIP 备份文件</label><input id="restore-file" type="file" accept=".zip,application/zip" required><p><button class="warning" type="submit">上传并恢复</button></p><p class="muted" data-restore-status role="status"></p></form></article><article class="detail wide-detail"><h3>每日异地备份</h3><p><strong class="{offsite_backup_class}">{offsite_backup_label}</strong></p><p class="muted">{offsite_backup_detail}。凭据只允许保存在服务器的 <code>/etc/hysteria2-panel/offsite-backup.json</code>（root:root 0600），不会进入网页、数据库或备份。</p></article></div></div></dialog>
<dialog id="credentials-dialog" class="migration-dialog credentials-dialog" aria-labelledby="credentials-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="credentials-title" data-credentials-title>节点信息</h2><p class="muted">连接地址包含认证凭据，请只分享给受信任的人。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭节点信息弹窗">关闭</button></div>
<div class="qr-panel" data-qr-panel hidden><canvas id="credentials-qr" class="qr-canvas" role="img" aria-label="Hysteria 2 节点配置二维码"></canvas><p class="muted">可直接扫描导入，或保存 PNG 到受信任的设备。</p></div>
<label for="credentials-uri">Hysteria 2 节点代码</label><textarea id="credentials-uri" rows="5" readonly></textarea><div class="credential-actions"><button type="button" data-copy-target="credentials-uri">复制节点代码</button><button class="secondary" type="button" data-save-qr hidden>保存二维码 PNG</button></div><p class="notice" data-credentials-notice>关闭弹窗后会刷新当前用户列表。</p></div></dialog>
<dialog id="create-user-dialog" class="migration-dialog create-dialog" aria-labelledby="create-user-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="create-user-title">添加用户</h2><p class="muted">设置用户名称、设备数和总流量限制。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭添加用户弹窗">关闭</button></div>
<form class="create-grid" method="post" action="/users" data-create-user-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="inline" value="1"><div class="wide"><label for="name">用户名称</label><input id="name" name="name" required maxlength="64" placeholder="例如：Alice 手机" autofocus></div>
<div><label for="device_limit">限制设备数</label><input id="device_limit" name="device_limit" type="number" min="1" max="100" value="3" required></div>
<div><label for="traffic_limit_gb">总流量（GiB）</label><input id="traffic_limit_gb" name="traffic_limit_gb" type="number" min="1" max="1048576" value="250" required></div><button type="submit">添加用户</button></form></div></dialog>
<dialog id="edit-user-dialog" class="migration-dialog create-dialog" aria-labelledby="edit-user-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="edit-user-title">编辑用户</h2><p class="muted">修改限制或开放 UDP 443，不会改变已发放节点链接。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭编辑用户弹窗">关闭</button></div>
<form class="create-grid" method="post" action="/users/{first_edit_id}/edit" data-edit-user-form><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="inline" value="1"><input type="hidden" name="generation" value="{first_edit_generation}"><div class="wide"><label for="edit-user-select">选择用户</label><select id="edit-user-select" data-edit-user-select required>{edit_options}</select></div>
<div><label for="edit-device-limit">限制设备数</label><input id="edit-device-limit" name="device_limit" type="number" min="1" max="100" value="{first_edit_device_limit}" required></div>
<div><label for="edit-traffic-limit-gb">总流量（GiB）</label><input id="edit-traffic-limit-gb" name="traffic_limit_gb" type="number" min="1" max="1048576" value="{first_edit_traffic_limit_gb}" required></div>
<label class="checkbox-field wide" for="edit-allow-udp-443"><input id="edit-allow-udp-443" name="allow_udp_443" type="checkbox" value="1"{first_edit_udp_443_checked}{udp_443_disabled}><span>允许该账号使用 UDP 443<small class="muted">开启后，客户端把服务器端口从 {port} 改为 443 即可；原 {port} 仍可继续使用。</small></span></label><button type="submit"{edit_disabled}>保存修改</button></form>
<p class="notice">设备数按在线 Hysteria 客户端实例估算；标准通用节点链接不包含硬件设备指纹。</p></div></dialog>
<p class="toast" data-page-status role="status" aria-live="polite" hidden></p>
<section class="card"><div class="section-head user-section-head"><div class="user-heading"><h2>用户管理</h2><p class="muted">创建用户并设置并发设备和总流量限制。</p></div>
<div class="section-actions"><button type="button" data-dialog-open="create-user-dialog">添加用户</button><button class="secondary" type="button" data-dialog-open="edit-user-dialog"{edit_disabled}>编辑用户</button><form method="post" action="/users/reset-traffic" data-confirm="确定重置所有用户的上传和下载流量吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">重置全部流量</button></form></div></div>
<div class="user-tools"><form class="user-filters" method="get" action="/" data-user-filters><div class="user-search"><label for="user-search">用户名</label><input id="user-search" name="q" type="search" value="{search_query}" placeholder="输入用户名搜索" autocomplete="off" maxlength="96" data-user-search></div>
<div><label for="user-status-filter">状态</label><select id="user-status-filter" name="status" data-status-filter><option value="">全部</option><option value="enabled"{status_enabled}>启用</option><option value="disabled"{status_disabled}>禁用</option></select></div>
<div><label for="user-online-filter">在线</label><select id="user-online-filter" name="online" data-online-filter><option value="">全部</option><option value="active"{online_active}>在线</option><option value="inactive"{online_inactive}>离线</option></select></div>
<div><label for="user-udp443-filter">UDP 443</label><select id="user-udp443-filter" name="udp443" data-udp443-filter><option value="">全部</option><option value="allowed"{udp443_allowed}>已开放</option><option value="blocked"{udp443_blocked}>未开放</option></select></div>
<button class="ghost" type="button" data-clear-user-filters>清除</button></form><p class="muted search-status" data-search-status role="status" aria-live="polite">{user_count_text}</p></div>
<p class="muted filter-empty" data-filter-empty hidden>没有符合当前条件的用户。</p>
<div class="table-wrap user-table"><table><thead><tr><th>名称</th><th>状态</th><th aria-sort="{online_sort_aria}"><a class="sort-link" href="{online_sort_href}">在线设备 {online_sort_mark}</a></th><th>上传 / 下载</th><th aria-sort="{traffic_sort_aria}"><a class="sort-link" href="{traffic_sort_href}">总流量 {traffic_sort_mark}</a></th><th>操作</th></tr></thead><tbody>{rows}</tbody></table></div></section>""".format(
        port=self.app.hysteria_port,
        public_host=html.escape(self.app.public_host),
        stats=stats_state,
        stats_class="ok" if summary["service_available"] else "bad",
        service_label=service_label,
        service_class=service_class,
        refreshed=time.strftime("%H:%M:%S"),
        total_users=summary["total_users"],
        inactive_users=summary["inactive_users"],
        online_devices=summary["online_devices"],
        total_tx=_human_bytes(summary["total_tx"]),
        total_rx=_human_bytes(summary["total_rx"]),
        online_note=online_note,
        machine_stats_section=machine_stats_section,
        csrf=csrf,
        onboarding_disabled=onboarding_disabled,
        node_rows=node_rows_html,
        offsite_backup_class=offsite_backup_class,
        offsite_backup_label=offsite_backup_label,
        offsite_backup_detail=html.escape(offsite_backup_detail),
        version=PANEL_VERSION,
        update_text=update_text,
        update_action=update_action,
        update_state=update_state,
        update_status_text=update_status_text,
        egress_target=egress_target,
        egress_confirm=html.escape(egress_confirm, quote=True),
        egress_state=egress_state,
        egress_state_class=egress_state_class,
        egress_checked="true" if full_enabled else "false",
        egress_action=egress_action,
        cpu=(
            "{:.1f}%".format(resources["cpu_percent"])
            if metrics_available
            else "—"
        ),
        memory=(
            "{:.1f}%".format(resources["memory_percent"])
            if metrics_available
            else "—"
        ),
        memory_used=(
            _human_bytes(resources["memory_used"]) if metrics_available else "—"
        ),
        memory_total=(
            _human_bytes(resources["memory_total"]) if metrics_available else "—"
        ),
        disk=(
            "{:.1f}%".format(resources["disk_percent"])
            if metrics_available
            else "—"
        ),
        disk_used=(
            _human_bytes(resources["disk_used"]) if metrics_available else "—"
        ),
        disk_total=(
            _human_bytes(resources["disk_total"]) if metrics_available else "—"
        ),
        uptime=html.escape(resources["uptime"]),
        certificate_class=certificate_class,
        certificate_text=certificate_text,
        tcp_cc=html.escape(resources["tcp_congestion_control"]),
        qdisc=html.escape(resources["default_qdisc"]),
        rank_rows=rank_rows,
        rows="".join(rows),
        edit_options=(
            edit_options
            if edit_options
            else '<option value="">暂无可编辑用户</option>'
        ),
        first_edit_id=first_edit_user["id"] if first_edit_user else 0,
        first_edit_generation=(
            first_edit_user["generation"] if first_edit_user else 0
        ),
        first_edit_device_limit=(
            first_edit_user["device_limit"] if first_edit_user else DEFAULT_DEVICE_LIMIT
        ),
        first_edit_traffic_limit_gb=(
            max(1, first_edit_user["traffic_limit_bytes"] // 1024**3)
            if first_edit_user
            else DEFAULT_TRAFFIC_LIMIT_BYTES // 1024**3
        ),
        first_edit_udp_443_checked=(
            " checked"
            if first_edit_user and first_edit_user["allow_udp_443"]
            else ""
        ),
        udp_443_disabled="" if self.app.hysteria_port != 443 else " disabled",
        edit_disabled="" if first_edit_user else " disabled",
        user_count_text=html.escape(user_count_text),
        online_sort_href=html.escape(online_sort_href, quote=True),
        online_sort_aria=online_sort_aria,
        online_sort_next=online_sort_next,
        online_sort_mark=online_sort_mark,
        traffic_sort_href=html.escape(traffic_sort_href, quote=True),
        traffic_sort_aria=traffic_sort_aria,
        traffic_sort_next=traffic_sort_next,
        traffic_sort_mark=traffic_sort_mark,
        **filter_values,
    )
    return self._page("控制台", content)

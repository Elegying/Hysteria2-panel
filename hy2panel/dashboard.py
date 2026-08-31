"""Dashboard rendering isolated from the HTTP transport entrypoint."""

import base64
import hashlib
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
    MAX_STATE_AGE_SECONDS = context.max_state_age_seconds
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
    if update and update["update_available"]:
        update_action = """<form method="post" action="/updates/apply" data-update-form data-confirm="在线更新会短暂重启面板与 Hysteria 服务，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button success" type="submit">立即更新</button></form>""".format(
            csrf=csrf
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
        if status == "revoked" and node.get("registered_at") is None:
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
            and current_time - node["last_heartbeat_at"] <= 150
        )
        if status == "revoked":
            status_label, status_class = "已撤销", "bad"
        elif heartbeat_fresh:
            status_label, status_class = "在线", "ok"
        elif verified:
            status_label, status_class = "已验证 · 离线", "warning"
        elif status == "pending_verification":
            status_label, status_class = "待验证", "warning"
        elif expired:
            status_label, status_class = "注册链接已过期", "bad"
        else:
            status_label, status_class = "待注册", "warning"
        lifecycle_labels = {
            "draining": ("摘流中", "warning"),
            "stopping": ("正在停用", "warning"),
            "stopped": ("已安全停用", "muted"),
            "starting": ("正在恢复", "warning"),
            "archived": ("已归档", "muted"),
        }
        if lifecycle_state in lifecycle_labels:
            status_label, status_class = lifecycle_labels[lifecycle_state]
        node_actions = ""
        if (
            status == "pending_registration"
            and not expired
            and node.get("enrollment_id")
            and node.get("consumed_at") is None
            and node.get("revoked_at") is None
        ):
            node_actions = """<form method="post" action="/node-enrollments/{enrollment_id}/revoke" data-confirm="确定作废该对接码吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">立即作废</button></form>""".format(
                enrollment_id=node["enrollment_id"], csrf=csrf
            )
        fingerprint = ""
        if node.get("public_key"):
            try:
                fingerprint = hashlib.sha256(
                    base64.b64decode(node["public_key"], validate=True)
                ).hexdigest()
            except (TypeError, ValueError):
                fingerprint = ""
        if status == "pending_verification" and not verified and fingerprint:
            node_actions = """<form method="post" action="/nodes/{node_id}/verify" data-confirm="请确认服务器显示的指纹短码也是 {short_fingerprint}；确认后节点将自动完成部署。"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="fingerprint" value="{fingerprint}"><span class="muted">与服务器输出核对短码</span><strong><code>{short_fingerprint}</code></strong><button class="compact-button" type="submit">短码一致，开始自动部署</button></form>""".format(
                node_id=node["node_id"],
                csrf=csrf,
                fingerprint=fingerprint,
                short_fingerprint=fingerprint[:16],
            )
        if status == "pending_verification" and lifecycle_state != "archived":
            node_actions += """<form method="post" action="/nodes/{node_id}/revoke" data-confirm="撤销后该节点的后续心跳会被拒绝，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">撤销节点</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        details = [
            node.get("observed_ip")
            or node.get("expected_ip")
            or "尚未绑定公网 IP"
        ]
        if fingerprint:
            details.append("公钥 SHA-256：{}".format(fingerprint))
        if node.get("last_heartbeat_at"):
            details.append(
                "最后心跳：{}".format(
                    time.strftime(
                        "%Y-%m-%d %H:%M:%S",
                        time.localtime(node["last_heartbeat_at"]),
                    )
                )
            )
        policy_state = node.get("policy_state") or "standby"
        if policy_state == "protocol_ready" and lifecycle_state != "archived":
            snapshot_fresh = bool(
                node.get("last_snapshot_at")
                and node.get("last_traffic_ack_at")
                and current_time - node["last_snapshot_at"]
                <= MAX_STATE_AGE_SECONDS
                and current_time - node["last_traffic_ack_at"]
                <= MAX_STATE_AGE_SECONDS
            )
            details.append(
                "协议就绪 · {}".format(
                    "在线快照与流量检查点新鲜"
                    if snapshot_fresh
                    else "等待在线快照/流量队列确认"
                )
            )
            details.append(
                "节点运营状态：{}".format(
                    {
                        "active": "正常服务",
                        "draining": "等待 DNS 撤出和设备归零",
                        "stopping": "停止命令等待节点确认",
                        "stopped": "数据面已停止，身份与流量队列保留",
                        "starting": "启动命令等待节点确认",
                        "archived": "历史记录已归档",
                    }.get(lifecycle_state, "未知")
                )
            )
            details.append(
                "待确认命令：{}{}".format(
                    int(node.get("pending_commands") or 0),
                    "（含失败重试 {}）".format(
                        int(node.get("failed_commands") or 0)
                    )
                    if node.get("failed_commands")
                    else "",
                )
            )
            if lifecycle_state == "active":
                node_actions += """<form method="post" action="/nodes/{node_id}/protocol/disable" data-confirm="停用后该节点的中央认证、快照、流量和命令都会被拒绝，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary compact-button" type="submit">停用控制协议</button></form>""".format(
                    node_id=node["node_id"], csrf=csrf
                )
        elif verified and status == "pending_verification":
            details.append("自动部署等待中（通常 30 秒内开始）")
            node_actions += """<form method="post" action="/nodes/{node_id}/protocol/enable" data-confirm="这是旧节点故障恢复入口，只启用中央控制协议，不会部署 Hysteria 或修改 DNS。确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary compact-button" type="submit">旧节点手动启用</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        data_plane_state = node.get("data_plane_state") or "not_issued"
        data_plane_labels = {
            "not_issued": "等待节点自动领取部署凭据",
            "bootstrap_issued": "自动部署中 · 正在配置 FULL/双入口/网络优化",
            "data_plane_installed": "数据面已安装 · 待直连灰度",
            "direct_canary_passed": "主 UDP {}/443 真实验收通过 · 请手工添加 DNS".format(
                self.app.hysteria_port
            ),
            "dns_admitted": "DNS 已检测并自动准入 · 节点可用",
        }
        details.append(data_plane_labels.get(data_plane_state, "数据面状态异常"))
        data_plane_eligible = bool(
            status == "pending_verification"
            and verified
            and policy_state == "protocol_ready"
            and lifecycle_state == "active"
        )
        if (
            data_plane_eligible
            and data_plane_state
            in {
                "not_issued",
                "bootstrap_issued",
                "data_plane_installed",
                "direct_canary_passed",
                "dns_admitted",
            }
            and self.app.secure_cookies
            and self.app.data_plane_bootstrap_service is not None
            and not (
                data_plane_state == "bootstrap_issued"
                and node.get("active_automatic_canary")
            )
        ):
            if data_plane_state == "not_issued":
                data_plane_action = "旧节点手动部署"
            elif data_plane_state == "bootstrap_issued":
                data_plane_action = "重新生成部署码"
            else:
                data_plane_action = "生成数据面升级码"
            node_actions += """<form method="post" action="/nodes/{node_id}/data-plane/bootstrap" data-data-plane-bootstrap-form><input type="hidden" name="csrf" value="{csrf}"><button class="success compact-button" type="submit">{action}</button></form>""".format(
                node_id=node["node_id"], csrf=csrf, action=data_plane_action
            )
        if data_plane_eligible and data_plane_state == "data_plane_installed":
            node_actions += """<form method="post" action="/nodes/{node_id}/data-plane/canary/pass" data-data-plane-canary-form data-confirm="只记录该节点直连灰度通过，不会修改 DNS。确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="warning compact-button" type="submit">确认直连灰度通过</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        if (
            lifecycle_state == "active"
            and data_plane_state == "dns_admitted"
            and heartbeat_fresh
        ):
            node_actions += """<form method="post" action="/nodes/{node_id}/lifecycle/drain" data-confirm="开始摘流不会立刻断开用户。下一步请手工从 DNS 删除此节点 IP，再等待在线设备归零。确定开始吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="warning compact-button" type="submit">1. 开始摘流</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        if lifecycle_state == "draining":
            node_actions += """<form method="post" action="/nodes/{node_id}/lifecycle/stop" data-confirm="面板会先确认 DNS 已移除、设备数为 0、流量已结算；任何一项不满足都会拒绝停机。确定检查并停用吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">3. 检查并安全停用</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        if lifecycle_state in {"active", "draining"}:
            node_actions += """<form method="post" action="/nodes/{node_id}/lifecycle/emergency-stop" data-confirm="紧急停用会立即停止数据面。若 DNS 仍包含此 IP，部分用户会立刻连接失败。仅在故障或流量耗尽时使用，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">紧急停用</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        if lifecycle_state == "stopped":
            node_actions += """<form method="post" action="/nodes/{node_id}/lifecycle/resume" data-confirm="恢复后还需要把节点 IP 重新加入 DNS，面板检测和真实验收通过后用户才会使用。确定恢复吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="success compact-button" type="submit">恢复此节点</button></form><form method="post" action="/nodes/{node_id}/lifecycle/archive" data-confirm="请先把替换服务器按“全新节点对接”完成并加入 DNS。归档只隐藏旧节点操作入口，统计和审计仍保留。确定归档吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="secondary compact-button" type="submit">换机完成，归档旧节点</button></form>""".format(
                node_id=node["node_id"], csrf=csrf
            )
        if lifecycle_state == "archived":
            node_actions = '<span class="muted">统计与审计记录已保留</span>'
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
<form method="post" action="/service/stop" data-confirm="停止后所有连接会中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger" type="submit">停止</button></form><a class="button secondary" href="/">刷新</a><button class="secondary" type="button" data-dialog-open="node-onboarding-dialog"{onboarding_disabled}>对接</button></div>
<div class="service-details primary-details"><div class="detail compact-detail"><span class="muted">流量统计</span><strong class="{stats_class}">{stats}</strong></div><div class="detail compact-detail port-detail"><div><span class="muted">服务端口</span><strong>UDP {port}</strong></div><form class="egress-control" method="post" action="/egress/{egress_target}" data-egress-form data-confirm="{egress_confirm}"><input type="hidden" name="csrf" value="{csrf}"><span class="egress-state{egress_state_class}" data-egress-state>{egress_state}</span><button class="egress-switch{egress_state_class}" type="submit" aria-pressed="{egress_checked}" aria-label="{egress_action} FULL 出口策略"><span class="egress-switch-track" aria-hidden="true"><span></span></span><span class="egress-switch-action">{egress_action}</span></button></form></div></div>
<div class="service-details version-details"><div class="detail compact-detail bbr-detail"><span class="muted">BBR 状态</span><strong class="ok">Hysteria BBR</strong><small class="muted">standard · 内核 {tcp_cc} / {qdisc}</small></div><div class="detail compact-detail version-panel"><div class="version-row"><div><span class="muted">当前版本</span><strong>v{version}</strong></div><div class="button-row version-actions"><form method="post" action="/updates/check"><input type="hidden" name="csrf" value="{csrf}"><button class="compact-button" type="submit">检查更新</button></form>{update_action}</div></div><p class="muted">{update_text}</p><p class="update-state" data-update-status data-state="{update_state}" role="status" aria-live="polite">{update_status_text}</p></div></div></article>
<article class="card"><div class="section-head"><div><h2>系统资源</h2><p class="muted">服务器实时负载与容量。</p></div><form class="system-actions" method="post" action="/system/reboot" data-confirm="重启服务器后，所有节点连接会暂时中断，确定继续吗？"><input type="hidden" name="csrf" value="{csrf}"><button class="danger compact-button" type="submit">重启服务器</button></form></div><div class="resource-grid">
<div class="resource"><span class="muted">CPU 使用率</span><strong>{cpu}</strong></div><div class="resource"><span class="muted">内存占用</span><strong>{memory}</strong><small class="muted">{memory_used} / {memory_total}</small></div>
<div class="resource"><span class="muted">磁盘占用</span><strong>{disk}</strong><small class="muted">{disk_used} / {disk_total}</small></div><div class="resource"><span class="muted">运行时长</span><strong>{uptime}</strong></div>
<div class="resource certificate-resource"><span class="muted">节点证书</span><strong class="{certificate_class}">{certificate_text}</strong></div></div></article>
<article class="card traffic-card"><div class="section-head"><div><h2>高流量用户</h2><p class="muted">当前累计总流量最高的 5 个账号。</p></div></div><div class="rank-list">{rank_rows}</div></article>
</section>
<dialog id="node-onboarding-dialog" class="migration-dialog node-onboarding-dialog" aria-labelledby="node-onboarding-title"><div class="dialog-shell"><div class="dialog-head"><div><h2 id="node-onboarding-title">节点对接与停用</h2><p class="muted">按 1-2-3-4 操作；面板会把可以自动完成的步骤全部完成。</p></div><button class="dialog-close" type="button" data-dialog-close aria-label="关闭节点操作弹窗">关闭</button></div>
<p class="notice"><strong>固定安全边界：</strong>面板不会自动写入或删除 DNS；Hysteria 长期身份只会原样复制，不会自动轮换；现有用户配置不会改变。</p>
<div class="operation-guides"><section class="operation-guide"><h3>对接新节点：4 步完成</h3><ol class="numbered-steps"><li><strong>生成代码</strong><span>填写名称和公网 IP，点击“生成部署代码”。</span></li><li><strong>新机执行</strong><span>在新服务器用 root 运行整条代码，等待它显示 16 位短码。</span></li><li><strong>核对短码</strong><span>回到节点卡片逐字核对。相同后点击确认，面板自动配置 FULL、UDP {port}/443、fq/BBR 和 16 MiB 缓冲。</span></li><li><strong>添加 DNS</strong><span>真实出口验收通过后，把节点 IP 加入 <code>{public_host}</code> 的 A/AAAA；面板只读检测并自动准入。</span></li></ol></section><section class="operation-guide danger-guide"><h3>安全停用或换机：4 步完成</h3><ol class="numbered-steps"><li><strong>开始摘流</strong><span>在节点卡片点击“1. 开始摘流”，此时不会断开用户。</span></li><li><strong>删除 DNS</strong><span>手工从 <code>{public_host}</code> 删除旧节点 IP，等待 DNS 生效和在线设备归零。</span></li><li><strong>安全停用</strong><span>点击“3. 检查并安全停用”。面板确认 DNS、设备和流量 ACK 后才会停止 Hysteria，Agent、私钥和 spool 保留。</span></li><li><strong>恢复或换机</strong><span>原机恢复可直接点击“恢复此节点”；换服务器请在新机选择“全新节点对接”，加入 DNS 后再归档旧节点。“安全重绑定”只用于已部署节点重新连接面板。</span></li></ol></section></div>
<form class="node-enrollment-grid" method="post" action="/node-enrollments" data-node-enrollment-form><input type="hidden" name="csrf" value="{csrf}"><div><label for="node-name">节点名称</label><input id="node-name" name="name" required maxlength="64" placeholder="例如：香港分流-02"></div><div><label for="node-expected-ip">节点公网 IP（可选）</label><input id="node-expected-ip" name="expected_ip" inputmode="text" placeholder="例如：203.0.113.10"></div><div><label for="node-enrollment-mode">操作类型</label><select id="node-enrollment-mode" name="mode"><option value="join" selected>全新节点对接</option><option value="rebind">已有数据节点安全重绑定</option></select></div><div><label for="node-enrollment-ttl">对接码有效期</label><select id="node-enrollment-ttl" name="ttl_minutes"><option value="5">5 分钟</option><option value="10" selected>10 分钟</option><option value="30">30 分钟</option></select></div><button type="submit"{onboarding_disabled}>生成部署代码</button></form>
<section class="enrollment-result" data-node-enrollment-result hidden><label for="node-deployment-code">一键部署代码</label><textarea id="node-deployment-code" rows="12" readonly spellcheck="false"></textarea><div class="credential-actions"><button type="button" data-copy-target="node-deployment-code">复制部署代码</button></div><p class="muted" data-node-enrollment-expiry role="status"></p></section>
<section class="enrollment-result" data-data-plane-bootstrap-result hidden><label for="data-plane-deployment-code">数据面一键部署代码</label><textarea id="data-plane-deployment-code" rows="12" readonly spellcheck="false"></textarea><div class="credential-actions"><button type="button" data-copy-target="data-plane-deployment-code">复制数据面部署代码</button></div><p class="muted" data-data-plane-bootstrap-expiry role="status"></p><p class="notice"><strong>安全边界：</strong>代码只携带绑定节点与来源 IP 的短时授权；不会携带 Hysteria 证书私钥、HMAC、统计密钥、用户数据，也不会修改 DNS。</p></section>
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

"""Stable JSON projections for the Hysteria2 Manager Android client."""

import base64
import hashlib
import time


MOBILE_API_VERSION = "1"
MOBILE_APP_MIN_VERSION = "0.1.0"
NODE_FRESHNESS_SECONDS = 150


def _non_negative_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _safe_snapshot(application):
    try:
        snapshot = application.usage_manager.snapshot()
    except Exception:
        snapshot = {
            "traffic": {},
            "online": {},
            "available": False,
            "online_complete": False,
            "machine_stats": {"origins": []},
        }
    if not isinstance(snapshot, dict):
        return {
            "traffic": {},
            "online": {},
            "available": False,
            "online_complete": False,
            "machine_stats": {"origins": []},
        }
    return snapshot


def _user_items(application, snapshot):
    traffic_by_user = snapshot.get("traffic", {})
    online_by_user = snapshot.get("online", {})
    items = []
    for user in application.database.list_proxy_users_for_usage():
        traffic = traffic_by_user.get(user["name"], {})
        tx_bytes = _non_negative_int(traffic.get("tx", user.get("tx_bytes", 0)))
        rx_bytes = _non_negative_int(traffic.get("rx", user.get("rx_bytes", 0)))
        traffic_limit_bytes = _non_negative_int(user.get("traffic_limit_bytes"))
        used_bytes = tx_bytes + rx_bytes
        items.append(
            {
                "id": int(user["id"]),
                "name": user["name"],
                "enabled": bool(user["enabled"]),
                "generation": int(user["generation"]),
                "deviceLimit": int(user["device_limit"]),
                "onlineDevices": _non_negative_int(online_by_user.get(user["name"], 0)),
                "allowUdp443": bool(user["allow_udp_443"]),
                "txBytes": tx_bytes,
                "rxBytes": rx_bytes,
                "usedBytes": used_bytes,
                "trafficLimitBytes": traffic_limit_bytes,
                "trafficPercent": (
                    min(100.0, used_bytes * 100.0 / traffic_limit_bytes)
                    if traffic_limit_bytes
                    else 0.0
                ),
                "createdAt": _non_negative_int(user.get("created_at")),
                "updatedAt": _non_negative_int(user.get("updated_at")),
            }
        )
    return items


def users_payload(application):
    snapshot = _safe_snapshot(application)
    items = _user_items(application, snapshot)
    return {
        "items": items,
        "total": len(items),
        "available": bool(snapshot.get("available")),
        "onlineComplete": bool(snapshot.get("online_complete", True)),
        "observedAt": int(time.time()),
    }


def _node_fingerprint(public_key):
    if not public_key:
        return ""
    try:
        return hashlib.sha256(base64.b64decode(public_key, validate=True)).hexdigest()
    except (TypeError, ValueError):
        return ""


def _node_status(node, now):
    lifecycle_state = node.get("lifecycle_state") or "active"
    if lifecycle_state in {"draining", "stopping", "stopped", "starting", "archived"}:
        return lifecycle_state
    if node.get("status") == "revoked":
        return "revoked"
    if (
        node.get("status") == "pending_registration"
        and node.get("expires_at")
        and int(node["expires_at"]) <= now
    ):
        return "registration_expired"
    if node.get("verified_at"):
        heartbeat_at = _non_negative_int(node.get("last_heartbeat_at"))
        return "online" if heartbeat_at and now - heartbeat_at <= NODE_FRESHNESS_SECONDS else "offline"
    if node.get("status") == "pending_verification":
        return "pending_verification"
    return "pending_registration"


def nodes_payload(application):
    now = int(time.time())
    online_states = {
        state["node_id"]: state
        for state in application.database.list_node_online_states(
            now, NODE_FRESHNESS_SECONDS
        )
    }
    items = []
    for node in application.database.list_nodes():
        if node.get("status") == "revoked" and node.get("registered_at") is None:
            continue
        online_state = online_states.get(node["node_id"], {})
        fingerprint = _node_fingerprint(node.get("public_key"))
        items.append(
            {
                "nodeId": node["node_id"],
                "name": node["name"],
                "status": _node_status(node, now),
                "registrationStatus": node.get("status") or "unknown",
                "lifecycleState": node.get("lifecycle_state") or "active",
                "policyState": node.get("policy_state") or "standby",
                "dataPlaneState": node.get("data_plane_state") or "not_issued",
                "expectedIp": node.get("expected_ip") or "",
                "observedIp": node.get("observed_ip") or "",
                "hostname": node.get("hostname") or "",
                "platform": node.get("platform") or "",
                "architecture": node.get("architecture") or "",
                "agentVersion": node.get("agent_version") or "",
                "fingerprint": fingerprint,
                "fingerprintShort": fingerprint[:16],
                "verified": node.get("verified_at") is not None,
                "createdAt": _non_negative_int(node.get("created_at")),
                "registeredAt": _non_negative_int(node.get("registered_at")),
                "lastHeartbeatAt": _non_negative_int(node.get("last_heartbeat_at")),
                "lastSnapshotAt": _non_negative_int(node.get("last_snapshot_at")),
                "lastTrafficAckAt": _non_negative_int(node.get("last_traffic_ack_at")),
                "onlineState": online_state.get("online_state", "unavailable"),
                "onlineDevices": online_state.get("online_devices"),
                "lastKnownOnlineDevices": _non_negative_int(
                    online_state.get("last_known_online_devices")
                ),
                "pendingCommands": _non_negative_int(node.get("pending_commands")),
                "failedCommands": _non_negative_int(node.get("failed_commands")),
                "dnsAdmitted": node.get("dns_admitted_at") is not None,
                "expiresAt": _non_negative_int(node.get("expires_at")),
                "enrollmentId": node.get("enrollment_id") or "",
            }
        )
    status_counts = {}
    for item in items:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    return {
        "items": items,
        "total": len(items),
        "online": status_counts.get("online", 0),
        "statusCounts": status_counts,
        "observedAt": now,
    }


def _traffic_budgets(application, snapshot):
    origins = snapshot.get("machine_stats", {}).get("origins", [])
    budget_origin_ids = [
        origin.get("origin_id")
        for origin in origins
        if origin.get("kind") in {"local", "remote"} and origin.get("origin_id")
    ]
    budgets = {
        budget["origin_id"]: budget
        for budget in application.database.list_origin_budgets(
            budget_origin_ids, int(time.time())
        )
    }
    items = []
    for origin in origins:
        budget = budgets.get(origin.get("origin_id"))
        items.append(
            {
                "originId": origin.get("origin_id") or "",
                "kind": origin.get("kind") or "legacy",
                "name": origin.get("display_name") or origin.get("name") or "未知节点",
                "onlineState": origin.get("online_state") or "history",
                "onlineDevices": origin.get("online_devices"),
                "lastKnownOnlineDevices": _non_negative_int(
                    origin.get("last_known_online_devices")
                ),
                "txBytes": _non_negative_int(origin.get("tx_bytes")),
                "rxBytes": _non_negative_int(origin.get("rx_bytes")),
                "observedAt": _non_negative_int(origin.get("observed_at")),
                "budget": (
                    {
                        "status": budget["status"],
                        "usedBytes": _non_negative_int(budget["used_bytes"]),
                        "limitBytes": _non_negative_int(budget["limit_bytes"]),
                        "percent": float(budget["percent"]),
                        "warningPercent": int(budget["warning_percent"]),
                        "resetDay": int(budget["reset_day"]),
                        "nextResetAt": _non_negative_int(budget.get("next_reset_at")),
                    }
                    if budget
                    else None
                ),
            }
        )
    return items


def overview_payload(application, panel_version):
    snapshot = _safe_snapshot(application)
    users = _user_items(application, snapshot)
    nodes = nodes_payload(application)
    try:
        service_status = application.service_controller.status()
    except Exception:
        service_status = "unknown"
    try:
        resources = application.system_metrics.snapshot()
    except Exception:
        resources = {}
    total_tx = sum(user["txBytes"] for user in users)
    total_rx = sum(user["rxBytes"] for user in users)
    high_traffic = sorted(users, key=lambda item: item["usedBytes"], reverse=True)[:5]
    return {
        "panelVersion": str(panel_version),
        "apiVersion": MOBILE_API_VERSION,
        "panelName": application.node_name,
        "publicHost": application.public_host,
        "hysteriaPort": application.hysteria_port,
        "serviceStatus": service_status,
        "statsAvailable": bool(snapshot.get("available")),
        "onlineComplete": bool(snapshot.get("online_complete", True)),
        "refreshedAt": int(time.time()),
        "users": {
            "total": len(users),
            "inactive": sum(1 for user in users if user["usedBytes"] == 0),
            "onlineDevices": sum(user["onlineDevices"] for user in users),
            "highTraffic": high_traffic,
        },
        "traffic": {
            "txBytes": total_tx,
            "rxBytes": total_rx,
            "totalBytes": total_tx + total_rx,
        },
        "nodes": {
            "total": nodes["total"],
            "online": nodes["online"],
            "statusCounts": nodes["statusCounts"],
        },
        "trafficBudgets": _traffic_budgets(application, snapshot),
        "resources": {
            "cpuPercent": resources.get("cpu_percent"),
            "memoryPercent": resources.get("memory_percent"),
            "memoryUsed": _non_negative_int(resources.get("memory_used")),
            "memoryTotal": _non_negative_int(resources.get("memory_total")),
            "diskPercent": resources.get("disk_percent"),
            "diskUsed": _non_negative_int(resources.get("disk_used")),
            "diskTotal": _non_negative_int(resources.get("disk_total")),
            "uptime": resources.get("uptime") or "不可用",
            "tcpCongestionControl": resources.get("tcp_congestion_control") or "不可用",
            "defaultQdisc": resources.get("default_qdisc") or "不可用",
        },
    }


def capabilities_payload(panel_version):
    return {
        "apiVersion": MOBILE_API_VERSION,
        "panelVersion": str(panel_version),
        "minimumAppVersion": MOBILE_APP_MIN_VERSION,
        "platforms": ["android"],
        "features": [
            "overview",
            "users",
            "nodes",
            "node-enrollment",
            "service-control",
            "app-update-check",
        ],
    }

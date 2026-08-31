String formatBytes(Object? raw) {
  var value = raw is num ? raw.toDouble() : 0.0;
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'];
  var index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index++;
  }
  if (index == 0) return '${value.round()} ${units[index]}';
  return '${value.toStringAsFixed(value >= 100 ? 0 : 1)} ${units[index]}';
}

String formatTimestamp(Object? raw) {
  if (raw is! num || raw <= 0) return '尚未上报';
  final value = DateTime.fromMillisecondsSinceEpoch(raw.toInt() * 1000)
      .toLocal();
  String two(int number) => number.toString().padLeft(2, '0');
  return '${value.month}-${two(value.day)} ${two(value.hour)}:${two(value.minute)}:${two(value.second)}';
}

String serviceLabel(Object? status) {
  switch (status?.toString()) {
    case 'active':
      return 'Hysteria 运行中';
    case 'inactive':
      return 'Hysteria 已停止';
    case 'failed':
      return 'Hysteria 运行异常';
    default:
      return 'Hysteria 状态未知';
  }
}

String nodeStatusLabel(Object? status) {
  const labels = {
    'online': '在线',
    'offline': '已验证 · 离线',
    'pending_registration': '等待服务器注册',
    'registration_expired': '对接码已过期',
    'pending_verification': '等待核对短码',
    'draining': '正在摘流',
    'stopping': '正在安全停用',
    'stopped': '已停用',
    'starting': '正在恢复',
    'archived': '已归档',
    'revoked': '已撤销',
  };
  return labels[status?.toString()] ?? '状态未知';
}

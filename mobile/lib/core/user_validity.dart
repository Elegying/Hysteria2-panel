import 'package:flutter/material.dart';

String validityLabel(Object? seconds, {String empty = '永久'}) {
  if (seconds is! num || seconds <= 0) return empty;
  final date = DateTime.fromMillisecondsSinceEpoch(
    seconds.toInt() * 1000,
    isUtc: true,
  ).add(const Duration(hours: 8));
  String two(int n) => n.toString().padLeft(2, '0');
  return '${date.year}-${two(date.month)}-${two(date.day)} ${two(date.hour)}:${two(date.minute)}';
}

class UserValidityField extends StatelessWidget {
  const UserValidityField({
    super.key,
    required this.label,
    required this.empty,
    required this.value,
    required this.onChanged,
  });
  final String label;
  final String empty;
  final int? value;
  final ValueChanged<int?> onChanged;
  @override
  Widget build(BuildContext context) => ListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(label),
    subtitle: Text('${validityLabel(value, empty: empty)}（北京时间）'),
    trailing: value == null
        ? const Icon(Icons.calendar_month)
        : IconButton(
            tooltip: '清除$label',
            icon: const Icon(Icons.clear),
            onPressed: () => onChanged(null),
          ),
    onTap: () async {
      final initial =
          (value == null
                  ? DateTime.now().toUtc()
                  : DateTime.fromMillisecondsSinceEpoch(
                      value! * 1000,
                      isUtc: true,
                    ))
              .add(const Duration(hours: 8));
      final date = await showDatePicker(
        context: context,
        initialDate: DateTime(initial.year, initial.month, initial.day),
        firstDate: DateTime(1970),
        lastDate: DateTime(9999, 12, 31),
      );
      if (date == null || !context.mounted) return;
      final time = await showTimePicker(
        context: context,
        initialTime: TimeOfDay(hour: initial.hour, minute: initial.minute),
      );
      if (time == null || !context.mounted) return;
      onChanged(
        DateTime.utc(
              date.year,
              date.month,
              date.day,
              time.hour,
              time.minute,
            ).subtract(const Duration(hours: 8)).millisecondsSinceEpoch ~/
            1000,
      );
    },
  );
}

String userActivityLabel(Map<String, dynamic> user, {int? now}) {
  if (user['enabled'] != true) return '禁用';
  final current = now ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
  final expires = user['expiresAt'] as num?;
  final starts = user['startsAt'] as num?;
  if (expires != null && expires <= current) return '已到期';
  if (starts != null && starts > current) return '未开通';
  return '启用';
}

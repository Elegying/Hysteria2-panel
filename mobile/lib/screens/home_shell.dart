import 'package:flutter/material.dart';

import '../core/glass.dart';
import 'home_screen.dart';
import 'nodes_screen.dart';
import 'settings_screen.dart';
import 'users_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _pages = [
    HomeScreen(),
    UsersScreen(),
    NodesScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: AppBottomDock(
        selectedIndex: _index,
        onSelected: (value) => setState(() => _index = value),
      ),
    );
  }
}

class AppBottomDock extends StatelessWidget {
  const AppBottomDock({
    required this.selectedIndex,
    required this.onSelected,
    super.key,
  });

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  static const _items = [
    (
      label: '首页',
      icon: Icons.dashboard_outlined,
      selected: Icons.dashboard_rounded,
    ),
    (
      label: '用户',
      icon: Icons.people_outline_rounded,
      selected: Icons.people_rounded,
    ),
    (label: '节点', icon: Icons.dns_outlined, selected: Icons.dns_rounded),
    (
      label: '设置',
      icon: Icons.settings_outlined,
      selected: Icons.settings_rounded,
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final scale = MediaQuery.textScalerOf(context).scale(12) / 12;
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(16, 8, 16, 8),
      child: GlassSurface(
        borderRadius: 28,
        blurSigma: 20,
        child: Padding(
          padding: const EdgeInsets.all(5),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: 56 + (scale - 1) * 16),
            child: Row(
              children: [
                for (var index = 0; index < _items.length; index++)
                  Expanded(
                    child: Semantics(
                      button: true,
                      selected: selectedIndex == index,
                      label: _items[index].label,
                      excludeSemantics: true,
                      child: Material(
                        color: selectedIndex == index
                            ? scheme.primary.withValues(alpha: .12)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(23),
                        child: InkWell(
                          onTap: () => onSelected(index),
                          borderRadius: BorderRadius.circular(23),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(
                              vertical: 8,
                              horizontal: 2,
                            ),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  selectedIndex == index
                                      ? _items[index].selected
                                      : _items[index].icon,
                                  size: 23,
                                  color: selectedIndex == index
                                      ? scheme.primary
                                      : scheme.onSurfaceVariant,
                                ),
                                const SizedBox(height: 3),
                                Text(
                                  _items[index].label,
                                  style: Theme.of(context).textTheme.labelSmall
                                      ?.copyWith(
                                        fontWeight: FontWeight.w600,
                                        color: selectedIndex == index
                                            ? scheme.primary
                                            : scheme.onSurfaceVariant,
                                      ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

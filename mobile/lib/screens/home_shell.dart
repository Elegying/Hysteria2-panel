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
    return SafeArea(
      top: false,
      minimum: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      child: SizedBox(
        height: 54,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var index = 0; index < _items.length; index++) ...[
              if (index > 0) const SizedBox(width: 8),
              Expanded(
                child: GlassSurface(
                  borderRadius: 16,
                  blurSigma: 12,
                  child: InkWell(
                    onTap: () => onSelected(index),
                    borderRadius: BorderRadius.circular(16),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 180),
                      color: selectedIndex == index
                          ? scheme.primary.withValues(alpha: .18)
                          : Colors.transparent,
                      child: Semantics(
                        button: true,
                        selected: selectedIndex == index,
                        label: _items[index].label,
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              selectedIndex == index
                                  ? _items[index].selected
                                  : _items[index].icon,
                              size: 22,
                              color: selectedIndex == index
                                  ? scheme.primary
                                  : scheme.onSurfaceVariant,
                            ),
                            const SizedBox(height: 1),
                            Text(
                              _items[index].label,
                              maxLines: 1,
                              style: Theme.of(context).textTheme.labelSmall
                                  ?.copyWith(
                                    height: 1,
                                    fontWeight: selectedIndex == index
                                        ? FontWeight.w700
                                        : FontWeight.w500,
                                    color: selectedIndex == index
                                        ? scheme.onSurface
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
          ],
        ),
      ),
    );
  }
}

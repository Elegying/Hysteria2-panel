import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart' as liquid;

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
      body: liquid.GlassScaffold(
        backgroundColor: Colors.transparent,
        contentAwareBrightness: true,
        bottomBarHeight: appDockExtent(context),
        body: IndexedStack(
          index: _index,
          children: [
            for (var i = 0; i < _pages.length; i++)
              TickerMode(
                enabled: _index == i,
                child: _pages[i],
              ),
          ],
        ),
        bottomBar: AppBottomDock(
          selectedIndex: _index,
          onSelected: (value) => setState(() => _index = value),
        ),
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
    return liquid.GlassTabBar.bottom(
      selectedIndex: selectedIndex,
      onTabSelected: onSelected,
      quality: liquid.GlassQuality.premium,
      backgroundQuality: liquid.GlassQuality.premium,
      adaptiveBrightness: true,
      settings: liquid.LiquidGlassSettings(
        glassColor: Theme.of(context).brightness == Brightness.dark
            ? const Color(0x241B304A)
            : const Color(0x60FFFFFF),
        thickness: 28,
        blur: 6,
        chromaticAberration: .025,
        refractiveIndex: 1.3,
      ),
      horizontalPadding: 16,
      verticalPadding: 12,
      barHeight: appDockExtent(context) - 40,
      selectedIconColor: scheme.primary,
      selectedLabelColor: scheme.primary,
      unselectedIconColor: scheme.onSurfaceVariant,
      unselectedLabelColor: scheme.onSurfaceVariant,
      indicatorPinchStrength: .5,
      magnification: 1.18,
      tabs: [
        for (var index = 0; index < _items.length; index++)
          liquid.GlassTab(
            label: _items[index].label,
            icon: Icon(
              selectedIndex == index
                  ? _items[index].selected
                  : _items[index].icon,
            ),
          ),
      ],
    );
  }
}

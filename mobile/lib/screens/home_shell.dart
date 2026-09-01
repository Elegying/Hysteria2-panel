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
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          IndexedStack(index: _index, children: _pages),
          Positioned(
            left: 12,
            right: 12,
            bottom: bottomInset + 8,
            child: GlassSurface(
              borderRadius: 24,
              blurSigma: 22,
              child: NavigationBar(
                backgroundColor: Colors.transparent,
                selectedIndex: _index,
                onDestinationSelected: (value) =>
                    setState(() => _index = value),
                destinations: const [
                  NavigationDestination(
                    icon: Icon(Icons.dashboard_outlined),
                    selectedIcon: Icon(Icons.dashboard_rounded),
                    label: '首页',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.people_outline_rounded),
                    selectedIcon: Icon(Icons.people_rounded),
                    label: '用户',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.dns_outlined),
                    selectedIcon: Icon(Icons.dns_rounded),
                    label: '节点',
                  ),
                  NavigationDestination(
                    icon: Icon(Icons.settings_outlined),
                    selectedIcon: Icon(Icons.settings_rounded),
                    label: '设置',
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

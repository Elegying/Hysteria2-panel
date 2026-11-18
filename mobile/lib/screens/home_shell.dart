import 'package:flutter/material.dart';

import 'home_screen.dart';
import 'nodes_screen.dart';
import 'settings_screen.dart';
import 'users_screen.dart';
import 'subscriptions_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key});
  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  static const _pages = [
    HomeScreen(),
    NodesScreen(),
    UsersScreen(),
    SubscriptionsScreen(),
    SettingsScreen(),
  ];
  @override
  Widget build(BuildContext context) => Scaffold(
    body: Stack(
      fit: StackFit.expand,
      children: [
        for (var i = 0; i < _pages.length; i++)
          Offstage(
            offstage: _index != i,
            child: ExcludeSemantics(
              excluding: _index != i,
              child: AnimatedOpacity(
                opacity: _index == i ? 1 : 0,
                duration: MediaQuery.disableAnimationsOf(context)
                    ? Duration.zero
                    : const Duration(milliseconds: 180),
                child: TickerMode(enabled: _index == i, child: _pages[i]),
              ),
            ),
          ),
      ],
    ),
    bottomNavigationBar: AppBottomDock(
      selectedIndex: _index,
      onSelected: (value) => setState(() => _index = value),
    ),
  );
}

class AppBottomDock extends StatelessWidget {
  const AppBottomDock({
    required this.selectedIndex,
    required this.onSelected,
    super.key,
  });
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      border: Border(
        top: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
      ),
    ),
    child: NavigationBar(
      selectedIndex: selectedIndex,
      onDestinationSelected: onSelected,
      backgroundColor: Theme.of(context).colorScheme.surface,
      destinations: const [
        NavigationDestination(icon: Icon(Icons.home_outlined), label: '总览'),
        NavigationDestination(icon: Icon(Icons.dns_outlined), label: '节点管理'),
        NavigationDestination(icon: Icon(Icons.people_outline), label: '用户管理'),
        NavigationDestination(
          icon: Icon(Icons.article_outlined),
          label: '订阅管理',
        ),
        NavigationDestination(icon: Icon(Icons.settings_outlined), label: '设置'),
      ],
    ),
  );
}

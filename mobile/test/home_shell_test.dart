import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/glass.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';

void main() {
  testWidgets('bottom dock groups tabs and reserves accessible layout space', (
    tester,
  ) async {
    var selectedIndex = 0;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(useMaterial3: true),
        home: StatefulBuilder(
          builder: (context, setState) => Scaffold(
            body: const ColoredBox(
              key: Key('page-body'),
              color: Colors.transparent,
            ),
            bottomNavigationBar: AppBottomDock(
              selectedIndex: selectedIndex,
              onSelected: (value) => setState(() => selectedIndex = value),
            ),
          ),
        ),
      ),
    );

    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(GlassSurface), findsOneWidget);
    for (final label in ['首页', '用户', '节点', '设置']) {
      expect(find.text(label), findsOneWidget);
    }

    final dock = tester.getRect(find.byType(GlassSurface));
    expect(dock.height, greaterThanOrEqualTo(66));
    expect(
      tester.getBottomLeft(find.byKey(const Key('page-body'))).dy,
      lessThanOrEqualTo(tester.getTopLeft(find.byType(AppBottomDock)).dy),
    );

    await tester.tap(find.text('节点'));
    await tester.pumpAndSettle();
    expect(selectedIndex, 2);
  });
}

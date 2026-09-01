import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/glass.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';

void main() {
  testWidgets('bottom dock is compact, segmented, and reserves layout space', (
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
    expect(find.byType(GlassSurface), findsNWidgets(4));
    for (final label in ['首页', '用户', '节点', '设置']) {
      expect(find.text(label), findsOneWidget);
    }

    final first = tester.getRect(find.byType(GlassSurface).at(0));
    final second = tester.getRect(find.byType(GlassSurface).at(1));
    expect(first.height, 54);
    expect(second.left - first.right, 8);
    expect(
      tester.getBottomLeft(find.byKey(const Key('page-body'))).dy,
      lessThanOrEqualTo(tester.getTopLeft(find.byType(AppBottomDock)).dy),
    );

    await tester.tapAt(Offset(first.right + 4, first.center.dy));
    await tester.pump();
    expect(selectedIndex, 0);

    await tester.tap(find.text('节点'));
    await tester.pumpAndSettle();
    expect(selectedIndex, 2);
  });
}

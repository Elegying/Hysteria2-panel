import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart' as liquid;
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
    expect(find.byType(liquid.GlassTabBar), findsOneWidget);
    for (final label in ['首页', '用户', '节点', '设置']) {
      expect(find.text(label), findsWidgets);
    }

    final dock = tester.getRect(find.byType(liquid.GlassTabBar));
    expect(dock.height, greaterThanOrEqualTo(66));
    expect(
      tester.getBottomLeft(find.byKey(const Key('page-body'))).dy,
      lessThanOrEqualTo(tester.getTopLeft(find.byType(AppBottomDock)).dy),
    );

    await tester.tap(find.text('节点').hitTestable().first);
    await tester.pumpAndSettle();
    expect(selectedIndex, 2);
  });

  for (final reduced in [false, true]) {
    testWidgets('dock retargets immediately, reduced motion=$reduced', (
      tester,
    ) async {
      var selected = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: StatefulBuilder(
            builder: (context, setState) => MediaQuery(
              data: MediaQueryData(disableAnimations: reduced),
              child: AppBottomDock(
                selectedIndex: selected,
                onSelected: (value) => setState(() => selected = value),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('节点').hitTestable().first);
      await tester.pump(const Duration(milliseconds: 40));
      expect(selected, 2);
      await tester.tap(find.text('用户').hitTestable().first);
      await tester.pumpAndSettle();
      expect(selected, 1);
      expect(
        tester
            .widget<liquid.GlassTabBar>(find.byType(liquid.GlassTabBar))
            .selectedIndex,
        1,
      );
      expect(
        tester
            .widget<liquid.GlassTabBar>(find.byType(liquid.GlassTabBar))
            .quality,
        liquid.GlassQuality.premium,
      );
      expect(tester.takeException(), isNull);
    });
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/glass.dart';

void main() {
  testWidgets('liquid glass surface renders one shared blur layer', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: LiquidBackdrop(
          child: Scaffold(
            backgroundColor: Colors.transparent,
            body: GlassCard(child: Text('内容')),
            bottomNavigationBar: GlassSurface(
              blurSigma: 22,
              child: SizedBox(height: 64),
            ),
          ),
        ),
      ),
    );

    expect(find.text('内容'), findsOneWidget);
    expect(find.byType(BackdropFilter), findsOneWidget);
  });

  testWidgets('dialogs and secondary sheets share the glass surface', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => Column(
              children: [
                TextButton(
                  onPressed: () => showDialog<void>(
                    context: context,
                    builder: (_) => GlassDialog(
                      title: const Text('玻璃弹窗'),
                      content: const Text('内容'),
                      actions: [
                        TextButton(onPressed: () {}, child: const Text('确定')),
                      ],
                    ),
                  ),
                  child: const Text('打开弹窗'),
                ),
                TextButton(
                  onPressed: () => showGlassModalBottomSheet<void>(
                    context: context,
                    builder: (_) => const SizedBox(
                      height: 180,
                      child: Center(child: Text('玻璃二级页')),
                    ),
                  ),
                  child: const Text('打开二级页'),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('打开弹窗'));
    await tester.pumpAndSettle();
    expect(find.text('玻璃弹窗'), findsOneWidget);
    expect(find.byType(BackdropFilter), findsOneWidget);
    await tester.tapAt(const Offset(4, 4));
    await tester.pumpAndSettle();

    await tester.tap(find.text('打开二级页'));
    await tester.pumpAndSettle();
    expect(find.text('玻璃二级页'), findsOneWidget);
    expect(find.byType(BackdropFilter), findsOneWidget);
  });
}

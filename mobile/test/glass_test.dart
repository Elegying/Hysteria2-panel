import 'package:flutter/material.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart' as liquid;
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/glass.dart';
import 'package:hysteria2_manager/core/h2_drifting_background.dart';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  setUp(
    () => binding.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: true),
  );
  tearDown(
    () => binding.platformDispatcher.clearAccessibilityFeaturesTestValue(),
  );
  testWidgets('content and floating surfaces both render liquid glass', (
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
    expect(find.byType(liquid.GlassContainer), findsNWidgets(2));
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
    expect(find.byType(liquid.GlassContainer), findsOneWidget);
    await tester.tapAt(const Offset(4, 4));
    await tester.pumpAndSettle();

    await tester.tap(find.text('打开二级页'));
    await tester.pumpAndSettle();
    expect(find.text('玻璃二级页'), findsOneWidget);
    expect(find.byType(liquid.GlassContainer), findsOneWidget);
  });
  testWidgets(
    'glass selection sheet selects and cancels without stale changes',
    (tester) async {
      String? selected = 'all';
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StatefulBuilder(
              builder: (context, setState) => GlassDropdownField<String>(
                initialValue: selected,
                decoration: const InputDecoration(labelText: '状态'),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('全部')),
                  DropdownMenuItem(value: 'online', child: Text('在线')),
                ],
                onChanged: (value) => setState(() => selected = value),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('全部'));
      await tester.pumpAndSettle();
      expect(find.byType(GlassDialog), findsOneWidget);
      await tester.tap(find.text('在线'));
      await tester.pumpAndSettle();
      expect(selected, 'online');
      await tester.tap(find.text('在线'));
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(2, 2));
      await tester.pumpAndSettle();
      expect(selected, 'online');
    },
  );

  testWidgets(
    'long lists preserve every row without sharing moving shader groups',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CustomScrollView(
              slivers: [
                GlassSliverList(
                  itemCount: 41,
                  itemBuilder: (_, i) => GlassCard(
                    child: SizedBox(height: 80, child: Text('row $i')),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
      await tester.scrollUntilVisible(
        find.text('row 40'),
        400,
        scrollable: find.byType(Scrollable).first,
        maxScrolls: 20,
      );
      expect(find.text('row 40'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('focused field label stays inside its glass clipping bounds', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: GlassControlSurface(
              child: TextField(
                decoration: InputDecoration(
                  labelText: '设备数限制',
                  border: OutlineInputBorder(),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.byType(TextField));
    await tester.pumpAndSettle();
    final label = tester.getRect(find.text('设备数限制'));
    final surface = tester.getRect(find.byType(GlassControlSurface));
    expect(label.top, greaterThanOrEqualTo(surface.top));
    expect(label.bottom, lessThanOrEqualTo(surface.bottom));
  });

  testWidgets('background drifts and pauses when the application is hidden', (
    tester,
  ) async {
    binding.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: false);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpWidget(
      const MaterialApp(home: LiquidBackdrop(child: SizedBox.expand())),
    );
    await tester.pump(const Duration(seconds: 1));
    final wallpaperTranslation = find.descendant(
      of: find.byType(H2DriftingBackground),
      matching: find.byType(FractionalTranslation),
    );
    final first = tester
        .widget<FractionalTranslation>(wallpaperTranslation)
        .translation;
    await tester.pump(const Duration(seconds: 8));
    expect(
      tester.widget<FractionalTranslation>(wallpaperTranslation).translation,
      isNot(first),
    );
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump();
    final paused = tester
        .widget<FractionalTranslation>(wallpaperTranslation)
        .translation;
    await tester.pump(const Duration(seconds: 8));
    expect(
      tester.widget<FractionalTranslation>(wallpaperTranslation).translation,
      paused,
    );
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}

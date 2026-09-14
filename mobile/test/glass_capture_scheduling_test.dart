import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart' as glass;
import 'package:hysteria2_manager/core/h2_glass_capture.dart';
import 'package:hysteria2_manager/core/h2_drifting_background.dart';

class _CaptureBinding extends AutomatedTestWidgetsFlutterBinding {
  int capturesQueued = 0;

  @override
  void addPostFrameCallback(
    FrameCallback callback, {
    String debugLabel = 'callback',
  }) {
    if (debugLabel == 'H2 glass capture') capturesQueued++;
    super.addPostFrameCallback(callback, debugLabel: debugLabel);
  }
}

void main() {
  final binding = _CaptureBinding();

  testWidgets('disabled capture queues no work and resumes with fresh pixels', (
    tester,
  ) async {
    final color = ValueNotifier<Color>(Colors.blue);
    addTearDown(color.dispose);
    H2GlassFrame? frame;
    Widget page({bool highContrast = true}) => MaterialApp(
      home: MediaQuery(
        data: MediaQueryData(highContrast: highContrast),
        child: glass.LiquidGlassScope(
          child: H2GlassCapture(
            captureSupported: true,
            child: Stack(
              fit: StackFit.expand,
              children: [
                H2GlassBackgroundSource(
                  child: ValueListenableBuilder<Color>(
                    valueListenable: color,
                    builder: (_, value, _) => ColoredBox(color: value),
                  ),
                ),
                Builder(
                  builder: (context) {
                    return ValueListenableBuilder<H2GlassFrame?>(
                      valueListenable: H2GlassFrame.listenableOf(context)!,
                      builder: (_, value, _) {
                        frame = value;
                        return const SizedBox();
                      },
                    );
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );

    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpWidget(page());
    for (var i = 0; i < 10; i++) {
      color.value = i.isEven ? Colors.red : Colors.blue;
      await tester.pump();
    }
    expect(binding.capturesQueued, 0);
    expect(frame, isNull);

    await tester.pumpWidget(page(highContrast: false));
    await tester.pump();
    expect(frame, isNotNull);
    final first = frame!.image;
    final count = binding.capturesQueued;
    binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    color.value = Colors.green;
    await tester.pump();
    expect(binding.capturesQueued, count);
    expect(frame!.image, same(first));

    binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    await tester.pump();
    expect(binding.capturesQueued, greaterThan(count));
    expect(frame!.image, isNot(same(first)));
    final pixels = await tester.runAsync(() => frame!.image.toByteData());
    expect(pixels!.getUint8(1), (Colors.green.toARGB32() >> 8) & 0xff);
    final resumed = frame!.image;
    await tester.pumpWidget(page());
    expect(resumed.debugDisposed, isFalse);
    await tester.pump();
    expect(frame, isNull);
    expect(resumed.debugDisposed, isTrue);
    final disabledCount = binding.capturesQueued;
    color.value = Colors.red;
    await tester.pump();
    expect(binding.capturesQueued, disabledCount);
    await tester.pumpWidget(page(highContrast: false));
    await tester.pump();
    expect(frame, isNotNull);
    expect(frame!.image.debugDisposed, isFalse);
    final restoredPixels = await tester.runAsync(
      () => frame!.image.toByteData(),
    );
    expect(restoredPixels!.getUint8(0), (Colors.red.toARGB32() >> 16) & 0xff);
    await tester.pumpWidget(const SizedBox());
    expect(first.debugDisposed, isTrue);
    binding.handleAppLifecycleStateChanged(AppLifecycleState.detached);
  });
  testWidgets(
    'drifting wallpaper reuses pixels while updating capture origin',
    (tester) async {
      H2GlassFrame? frame;
      binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpWidget(
        MaterialApp(
          home: glass.LiquidGlassScope(
            child: H2GlassCapture(
              captureSupported: true,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const H2DriftingBackground(
                    captureBackground: true,
                    child: ColoredBox(color: Colors.blue),
                  ),
                  Builder(
                    builder: (context) => ValueListenableBuilder<H2GlassFrame?>(
                      valueListenable: H2GlassFrame.listenableOf(context)!,
                      builder: (_, value, _) {
                        frame = value;
                        return const SizedBox();
                      },
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      final first = frame!;
      for (var i = 0; i < 12; i++) {
        await tester.pump(const Duration(milliseconds: 100));
        expect(frame!.image, same(first.image));
      }
      expect(frame!.origin, isNot(first.origin));
      expect(first.image.debugDisposed, isFalse);
      await tester.pumpWidget(const SizedBox());
      expect(first.image.debugDisposed, isTrue);
      binding.handleAppLifecycleStateChanged(AppLifecycleState.detached);
    },
  );
}

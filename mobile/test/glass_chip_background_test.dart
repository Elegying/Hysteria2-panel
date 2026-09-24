import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_theme.dart';
import 'package:hysteria2_manager/core/glass.dart';

void main() {
  for (final choice in [false, true]) {
    testWidgets(
      '${choice ? 'choice' : 'action'} chip lets the glass backdrop show through',
      (tester) async {
        final captureKey = GlobalKey();
        final chipKey = GlobalKey();
        var presses = 0;
        final chip = choice
            ? ChoiceChip(
                key: chipKey,
                selected: false,
                label: const SizedBox(width: 80, height: 24),
                onSelected: (_) => presses++,
              )
            : ActionChip(
                key: chipKey,
                backgroundColor: Colors.transparent,
                label: const SizedBox(width: 80, height: 24),
                onPressed: () => presses++,
              );
        await tester.pumpWidget(
          MaterialApp(
            theme: buildAppTheme(const Color(0xFF5F91F7), Brightness.dark),
            home: RepaintBoundary(
              key: captureKey,
              child: ColoredBox(
                color: const Color(0xFF409CDD),
                child: Center(child: GlassControlSurface(child: chip)),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        final boundary =
            captureKey.currentContext!.findRenderObject()!
                as RenderRepaintBoundary;
        final image = await tester.runAsync(() => boundary.toImage());
        final data = await tester.runAsync(
          () => image!.toByteData(format: ui.ImageByteFormat.rawRgba),
        );
        final center = tester.getCenter(find.byKey(chipKey));
        final offset =
            (center.dy.floor() * image!.width + center.dx.floor()) * 4;
        final pixels = data!.buffer.asUint8List();
        final red = pixels[offset];
        final green = pixels[offset + 1];
        final blue = pixels[offset + 2];
        image.dispose();
        expect(
          green,
          greaterThan(80),
          reason:
              'The blue backdrop must remain visible, not the dark canvas '
              '($red, $green, $blue).',
        );
        expect(blue, greaterThan(green));
        await tester.tap(find.byKey(chipKey));
        await tester.pumpAndSettle();
        expect(presses, 1);
        expect(tester.takeException(), isNull);
      },
    );
  }
}

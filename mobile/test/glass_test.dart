import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/glass.dart';

void main() {
  testWidgets('liquid glass renders one shared blurred navigation surface', (
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
}

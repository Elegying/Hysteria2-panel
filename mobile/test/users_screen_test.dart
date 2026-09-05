import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/users_screen.dart';
import 'package:hysteria2_manager/screens/home_screen.dart';

class UserFormController extends AppController {
  final requests = <Map<String, dynamic>>[];
  Completer<Map<String, dynamic>>? pendingRequest;

  @override
  Future<Map<String, dynamic>> getJson(String path) async => {
    'items': [
      {
        'id': 1,
        'name': 'form-test-user',
        'enabled': true,
        'generation': 0,
        'deviceLimit': 3,
        'trafficLimitBytes': 5 * 1073741824,
        'allowUdp443': false,
        'onlineDevices': 0,
        'usedBytes': 0,
        'txBytes': 0,
        'rxBytes': 0,
      },
    ],
  };

  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) async {
    requests.add(data);
    if (pendingRequest != null) return pendingRequest!.future;
    throw const ApiException('测试请求失败');
  }

  @override
  Future<Map<String, dynamic>> patchJson(
    String path,
    Map<String, dynamic> data,
  ) => postJson(path, data);
}

void main() {
  for (final kind in ['create', 'edit', 'enroll']) {
    for (final lateSuccess in [true, false]) {
      testWidgets(
        '$kind blocks duplicates and ignores late ${lateSuccess ? 'success' : 'failure'} after cancellation',
        (tester) async {
          final controller = UserFormController();
          controller.pendingRequest = Completer<Map<String, dynamic>>();
          await tester.pumpWidget(
            ProviderScope(
              overrides: [
                appControllerProvider.overrideWith((ref) => controller),
              ],
              child: MaterialApp(
                theme: ThemeData.dark(useMaterial3: true),
                home: Scaffold(
                  body: kind == 'enroll'
                      ? const HomeScreen()
                      : const UsersScreen(),
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          if (kind == 'edit') {
            await tester.tap(find.text('form-test-user').first);
            await tester.pumpAndSettle();
            final edit = find.widgetWithText(ActionChip, '编辑');
            await tester.ensureVisible(edit);
            await tester.tap(edit);
          } else {
            final open = find.text(kind == 'enroll' ? '一键对接' : '新增用户');
            if (kind == 'enroll') {
              await tester.scrollUntilVisible(
                open,
                250,
                scrollable: find.byType(Scrollable).first,
              );
            }
            await tester.pumpAndSettle();
            await tester.ensureVisible(open);
            await tester.pumpAndSettle();
            expect(open.hitTestable(), findsOneWidget);
            await tester.tap(open);
          }
          await tester.pumpAndSettle();
          Finder field(String label) => find.byWidgetPredicate(
            (widget) =>
                widget is TextField && widget.decoration?.labelText == label,
          );
          if (kind == 'create') {
            await tester.enterText(field('用户名'), 'pending-user');
          } else if (kind == 'enroll') {
            await tester.enterText(field('节点名称'), 'pending-node');
            await tester.enterText(field('目标服务器公网 IP'), '192.0.2.1');
          }
          final label = kind == 'create'
              ? '创建'
              : kind == 'edit'
              ? '保存'
              : '一键对接';
          final submit = find.descendant(
            of: find.byType(Dialog),
            matching: find.widgetWithText(FilledButton, label),
          );
          await tester.tap(submit);
          await tester.pump();
          // Tap the same position again, including while the busy label changes.
          await tester.tapAt(
            tester.getCenter(
              find.descendant(
                of: find.byType(Dialog),
                matching: find.byType(FilledButton),
              ),
            ),
          );
          await tester.pump();
          expect(controller.requests, hasLength(1));
          controller.pendingRequest!.completeError(
            const ApiException('测试请求失败'),
          );
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          expect(find.text('测试请求失败'), findsOneWidget);
          controller.pendingRequest = Completer<Map<String, dynamic>>();
          await tester.tap(submit);
          await tester.pump();
          expect(controller.requests, hasLength(2));
          await tester.tap(find.widgetWithText(TextButton, '取消'));
          if (lateSuccess) {
            controller.pendingRequest!.complete({'name': 'late-created'});
          } else {
            controller.pendingRequest!.completeError(
              const ApiException('迟到的失败'),
            );
          }
          await tester.pumpAndSettle();
          expect(find.text('迟到的失败'), findsNothing);
          expect(find.byType(Dialog), findsNothing);
          expect(
            find.byType(kind == 'enroll' ? HomeScreen : UsersScreen),
            findsOneWidget,
          );
          if (kind == 'edit') {
            expect(find.widgetWithText(ActionChip, '编辑'), findsOneWidget);
          }
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox.shrink());
          await tester.pumpAndSettle();
        },
      );
    }
  }
  for (final editing in [false, true]) {
    testWidgets(
      'user form validates input before ${editing ? 'edit' : 'create'}',
      (tester) async {
        tester.view.physicalSize = const Size(390, 844);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final controller = UserFormController();
        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              appControllerProvider.overrideWith((ref) => controller),
            ],
            child: MaterialApp(
              theme: ThemeData.dark(useMaterial3: true),
              home: const Scaffold(body: UsersScreen()),
            ),
          ),
        );
        await tester.pumpAndSettle();
        if (editing) {
          await tester.tap(find.text('form-test-user').first);
          await tester.pumpAndSettle();
          final edit = find.widgetWithText(ActionChip, '编辑');
          await tester.ensureVisible(edit);
          await tester.tap(edit);
        } else {
          await tester.tap(find.text('新增用户'));
        }
        await tester.pumpAndSettle();
        Finder field(String label) => find.byWidgetPredicate(
          (widget) =>
              widget is TextField && widget.decoration?.labelText == label,
        );
        tester.view.viewInsets = const FakeViewPadding(bottom: 300);
        addTearDown(tester.view.resetViewInsets);
        await tester.pumpAndSettle();
        final submit = find.widgetWithText(FilledButton, editing ? '保存' : '创建');
        if (!editing) await tester.enterText(field('用户名'), 'created-test-user');

        for (final invalid in ['', 'letters', '0', '101']) {
          await tester.enterText(field('设备数限制'), invalid);
          await tester.tap(submit);
          await tester.pump();
          expect(tester.takeException(), isNull);
          expect(controller.requests, isEmpty);
          expect(find.text('设备数须为 1–100 的整数'), findsOneWidget);
        }
        await tester.enterText(field('设备数限制'), '3');
        await tester.enterText(field('流量额度（GiB）'), '1.5');
        await tester.tap(submit);
        await tester.pump();
        expect(tester.takeException(), isNull);
        expect(controller.requests, isEmpty);
        expect(find.text('流量额度须为 1–1048576 GiB 的整数'), findsOneWidget);
        await tester.enterText(field('流量额度（GiB）'), '5');
        await tester.tap(submit);
        await tester.pumpAndSettle();
        expect(controller.requests.single['deviceLimit'], 3);
        expect(controller.requests.single['trafficLimitGb'], 5);
        expect(controller.requests.single['allowUdp443'], false);
        expect(find.text('测试请求失败'), findsOneWidget);
        await tester.pumpWidget(const SizedBox.shrink());
        await tester.pumpAndSettle();
      },
    );
  }
}

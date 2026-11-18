import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hysteria2_manager/app.dart';
import 'package:hysteria2_manager/core/app_controller.dart';
import 'package:hysteria2_manager/screens/home_shell.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'layout_capture_test.dart' show CaptureController;

class AuditController extends CaptureController {
  AuditController() {
    state = state.copyWith(
      panels: [
        PanelAccount(
          name: '管理面板',
          baseUrl: state.session!.baseUrl,
          username: state.session!.username,
          session: state.session,
        ),
        emptyPanels[1],
      ],
    );
  }
  final writes = <String>[];
  @override
  Future<Map<String, dynamic>> postJson(
    String path, [
    Map<String, dynamic> data = const {},
  ]) async {
    writes.add(path);
    return {};
  }
}

void main() {
  for (final scale in [1.0, 1.3]) {
    testWidgets('Xiaomi screen, expanded cards and keyboard dialogs $scale', (
      tester,
    ) async {
      Future<void> settle() async {
        for (var i = 0; i < 8; i++) {
          await tester.pump(const Duration(milliseconds: 100));
        }
      }

      SharedPreferences.setMockInitialValues({});
      PackageInfo.setMockInitialValues(
        appName: 'Panel',
        packageName: 'test',
        version: '0.5.7',
        buildNumber: '43',
        buildSignature: '',
      );
      if (const bool.fromEnvironment('CAPTURE_UI')) {
        await tester.runAsync(() async {
          await (FontLoader('MaterialIcons')
                ..addFont(rootBundle.load('fonts/MaterialIcons-Regular.otf')))
              .load();
          final bytes = ByteData.sublistView(
            await File('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
                .readAsBytes(),
          );
          for (final family in ['Roboto', 'Ahem']) {
            await (FontLoader(family)..addFont(Future.value(bytes))).load();
          }
        });
      }
      tester.view.physicalSize = const Size(1200, 2608);
      tester.view.devicePixelRatio = 3;
      tester.view.padding = FakeViewPadding(top: 84, bottom: 72);
      tester.view.viewPadding = FakeViewPadding(top: 84, bottom: 72);
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(() {
        tester.view.reset();
        tester.platformDispatcher.clearTextScaleFactorTestValue();
      });
      final controller = AuditController();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [appControllerProvider.overrideWith((_) => controller)],
          child: const Hysteria2ManagerApp(),
        ),
      );
      await settle();
      Future<void> capture(String name) async {
        expect(tester.takeException(), isNull, reason: name);
        if (const bool.fromEnvironment('CAPTURE_UI')) {
          await expectLater(
            find.byType(MaterialApp),
            matchesGoldenFile(
              '../../output/xiaomi-release-audit/$scale-$name.png',
            ),
          );
        }
      }

      Future<void> page(String label) async {
        await tester.tap(
          find.descendant(
            of: find.byType(AppBottomDock),
            matching: find.text(label),
          ),
        );
        await settle();
      }

      Future<void> keyboard(String name) async {
        await tester.tap(find.byType(EditableText).first);
        tester.view.viewInsets = FakeViewPadding(bottom: 960);
        await settle();
        await capture(name);
        tester.view.resetViewInsets();
        await settle();
        await tester.tap(find.text('取消').last);
        await settle();
        expect(tester.takeException(), isNull);
      }

      await capture('01-overview');
      await tester.tap(find.text('编辑预算').first);
      await settle();
      await keyboard('02-budget-keyboard');
      await page('节点管理');
      await tester.tap(find.text('私家车-美国-专线').first);
      await settle();
      await capture('03-node-expanded');
      await tester.tap(find.text('专线配置').first);
      await settle();
      await keyboard('04-profile-keyboard');
      await tester.tap(find.text('＋ 添加节点').first);
      await settle();
      await keyboard('05-enroll-keyboard');
      await page('用户管理');
      await tester.tap(find.text('示例用户 01').first);
      await settle();
      await capture('06-user-expanded');
      await tester.tap(find.text('新建用户').first);
      await settle();
      await keyboard('07-user-keyboard');
      await tester.tap(find.text('批量操作').first);
      await settle();
      await capture('14-batch-confirmation');
      await tester.tap(find.text('取消').last);
      await settle();
      await page('订阅管理');
      await tester.tap(find.text('示例用户 01').first);
      await settle();
      await tester.tap(find.text('更多⌄'));
      await settle();
      await capture('08-subscription-menu');
      await tester.tapAt(const Offset(5, 35));
      await settle();
      await tester.tap(find.text('导入外部节点').first);
      await settle();
      await capture('09-external-editor');
      await tester.tap(find.text('添加节点').first);
      await settle();
      await keyboard('10-external-keyboard');
      await tester.pageBack();
      await settle();
      await page('设置');
      await capture('11-settings');
      await tester.tap(find.text('停止服务').first);
      await settle();
      await capture('12-confirmation');
      await tester.tap(find.text('取消').last);
      await settle();
      await tester.scrollUntilVisible(
        find.text('检查 App 更新'),
        280,
        scrollable: find.byType(Scrollable).first,
      );
      await settle();
      final modes = ['跟随系统', '浅色', '深色']
          .map(
            (label) => tester.getRect(find.widgetWithText(ChoiceChip, label)),
          )
          .toList();
      final swatches = ['蓝色', '绿色', '紫色', '橙色', '粉色']
          .map((label) => tester.getRect(find.bySemanticsLabel('选择$label强调色')))
          .toList();
      final controls = [...modes, ...swatches];
      for (var i = 0; i < controls.length; i++) {
        for (var j = i + 1; j < controls.length; j++) {
          expect(controls[i].overlaps(controls[j]), isFalse);
        }
      }
      await capture('13-app-settings');
      await tester.tap(find.text('预览管理员').first);
      await settle();
      await capture('15-account-sheet');
      await tester.tap(find.text('重命名'));
      await settle();
      await keyboard('16-rename-keyboard');
      await tester.tap(find.text('预览管理员').first);
      await settle();
      await tester.tap(find.text('删除登录记忆'));
      await settle();
      await capture('17-account-delete-confirmation');
      await tester.tap(find.text('取消').last);
      await settle();
      expect(
        controller.writes,
        isEmpty,
        reason: 'Cancelling dialogs must not send write requests',
      );
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'core/app_controller.dart';
import 'core/glass.dart';
import 'core/theme_controller.dart';
import 'core/app_theme.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';

class Hysteria2ManagerApp extends ConsumerWidget {
  const Hysteria2ManagerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appState = ref.watch(appControllerProvider);
    final themeSettings = ref.watch(themeControllerProvider);
    return MaterialApp(
      title: 'Hysteria2管理',
      debugShowCheckedModeBanner: false,
      themeMode: themeSettings.mode,
      theme: buildAppTheme(themeSettings.seedColor, Brightness.light),
      darkTheme: buildAppTheme(themeSettings.seedColor, Brightness.dark),
      themeAnimationDuration: MediaQuery.disableAnimationsOf(context)
          ? Duration.zero
          : const Duration(milliseconds: 200),
      builder: (context, child) =>
          LiquidBackdrop(child: child ?? const SizedBox.shrink()),
      home: appState.initializing
          ? const _StartupScreen()
          : appState.session == null
          ? const LoginScreen()
          : const HomeShell(),
    );
  }
}

class _StartupScreen extends StatelessWidget {
  const _StartupScreen();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SvgPicture.asset('assets/h2-icon.svg', width: 82, height: 82),
            const SizedBox(height: 18),
            Text(
              'Hysteria2管理',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 20),
            const CircularProgressIndicator(),
          ],
        ),
      ),
    );
  }
}

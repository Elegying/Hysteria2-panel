import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'package:liquid_glass_widgets/liquid_glass_widgets.dart' as liquid;

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
      builder: (context, child) => liquid.LiquidGlassWidgets.wrap(
        brightnessResolver: Theme.maybeBrightnessOf,
        adaptiveQuality: false,
        theme: const liquid.GlassThemeData(
          light: liquid.GlassThemeVariant(
            quality: liquid.GlassQuality.premium,
            settings: liquid.GlassThemeSettings(
              glassColor: Color(0x60FFFFFF),
              thickness: 30,
              blur: 8,
              chromaticAberration: .025,
              lightIntensity: .8,
              refractiveIndex: 1.3,
            ),
          ),
          dark: liquid.GlassThemeVariant(
            quality: liquid.GlassQuality.premium,
            settings: liquid.GlassThemeSettings(
              glassColor: Color(0x241B304A),
              thickness: 34,
              blur: 8,
              chromaticAberration: .025,
              lightIntensity: .65,
              refractiveIndex: 1.3,
            ),
          ),
        ),
        child: LiquidBackdrop(child: child ?? const SizedBox.shrink()),
      ),
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

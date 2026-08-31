import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import 'core/app_controller.dart';
import 'core/theme_controller.dart';
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
      theme: _theme(themeSettings.seedColor, Brightness.light),
      darkTheme: _theme(themeSettings.seedColor, Brightness.dark),
      home: appState.initializing
          ? const _StartupScreen()
          : appState.session == null
          ? const LoginScreen()
          : const HomeShell(),
    );
  }

  ThemeData _theme(Color seed, Brightness brightness) {
    final scheme = ColorScheme.fromSeed(
      seedColor: seed,
      brightness: brightness,
    );
    final dark = brightness == Brightness.dark;
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: dark
          ? const Color(0xFF06111F)
          : const Color(0xFFF5F7FA),
      cardTheme: CardThemeData(
        elevation: 0,
        color: dark ? const Color(0xFF0B1A2C) : Colors.white,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(18),
          side: BorderSide(
            color: dark ? const Color(0xFF22364B) : const Color(0xFFE1E7EF),
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: dark ? const Color(0xFF101F31) : Colors.white,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 70,
        backgroundColor: dark ? const Color(0xFF0B1A2C) : Colors.white,
        indicatorColor: scheme.primaryContainer,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      ),
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: dark
            ? const Color(0xFF06111F)
            : const Color(0xFFF5F7FA),
      ),
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

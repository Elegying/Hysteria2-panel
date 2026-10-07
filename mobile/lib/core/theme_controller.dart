import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_controller.dart';

class ThemeSettings {
  const ThemeSettings({
    this.mode = ThemeMode.system,
    this.seedValue = 0xFF5F91F7,
  });

  final ThemeMode mode;
  final int seedValue;

  Color get seedColor => Color(seedValue);

  ThemeSettings copyWith({ThemeMode? mode, int? seedValue}) => ThemeSettings(
    mode: mode ?? this.mode,
    seedValue: seedValue ?? this.seedValue,
  );
}

final themeControllerProvider =
    StateNotifierProvider<ThemeController, ThemeSettings>((ref) {
      final panel = ref.watch(
        appControllerProvider.select((state) => state.activePanel),
      );
      final controller = ThemeController(panelIndex: panel);
      controller.load();
      return controller;
    });

class ThemeController extends StateNotifier<ThemeSettings> {
  ThemeController({this.panelIndex = 0}) : super(const ThemeSettings());

  final int panelIndex;

  String get _modeKey => panelIndex == 0 ? 'theme_mode' : 'theme_mode_panel_2';
  String get _seedKey => panelIndex == 0 ? 'theme_seed' : 'theme_seed_panel_2';

  Future<void> load() async {
    final preferences = await SharedPreferences.getInstance();
    final modeName = preferences.getString(_modeKey) ?? 'system';
    final mode = ThemeMode.values.firstWhere(
      (value) => value.name == modeName,
      orElse: () => ThemeMode.system,
    );
    if (!mounted) return;
    state = ThemeSettings(
      mode: mode,
      seedValue: preferences.getInt(_seedKey) ?? 0xFF5F91F7,
    );
  }

  Future<void> setMode(ThemeMode mode) async {
    state = state.copyWith(mode: mode);
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_modeKey, mode.name);
  }

  Future<void> setSeed(Color color) async {
    state = state.copyWith(seedValue: color.toARGB32());
    final preferences = await SharedPreferences.getInstance();
    await preferences.setInt(_seedKey, color.toARGB32());
  }
}

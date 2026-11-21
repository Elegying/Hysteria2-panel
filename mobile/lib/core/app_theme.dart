import 'package:flutter/material.dart';

/// Shared visual language; business screens keep their existing contracts.
ThemeData buildAppTheme(Color seed, Brightness brightness) {
  final dark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(seedColor: seed, brightness: brightness)
      .copyWith(
        primary: dark ? seed : ColorScheme.fromSeed(seedColor: seed).primary,
        secondary: dark ? const Color(0xFFBC9BEF) : const Color(0xFF644498),
        surface: dark ? const Color(0xFF071426) : const Color(0xFFF1F4F8),
        surfaceContainerLow: dark ? const Color(0xFF081D30) : Colors.white,
        surfaceContainerHighest: dark
            ? const Color(0xFF2C2C2E)
            : const Color(0xFFE5E5EA),
        onSurface: dark ? const Color(0xFFF5F5F7) : const Color(0xFF1C1C1E),
        onSurfaceVariant: dark
            ? const Color(0xFFBCCDE1)
            : const Color(0xFF63636B),
        outlineVariant: dark
            ? const Color(0xFF2D506A)
            : const Color(0xFFE0E0E5),
      );
  final base = ThemeData(useMaterial3: true, colorScheme: scheme);
  final text = base.textTheme;
  final shape = RoundedRectangleBorder(borderRadius: BorderRadius.circular(8));
  final fieldBorder = OutlineInputBorder(
    borderRadius: BorderRadius.circular(8),
    borderSide: BorderSide.none,
  );
  return base.copyWith(
    scaffoldBackgroundColor: Colors.transparent,
    splashFactory: InkSparkle.splashFactory,
    textTheme: text.copyWith(
      headlineLarge: text.headlineLarge?.copyWith(
        fontSize: 28,
        fontWeight: FontWeight.w700,
        letterSpacing: -.8,
      ),
      headlineMedium: text.headlineMedium?.copyWith(
        fontSize: 21,
        fontWeight: FontWeight.w700,
        letterSpacing: -.6,
      ),
      titleLarge: text.titleLarge?.copyWith(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        letterSpacing: -.3,
      ),
      bodyLarge: text.bodyLarge?.copyWith(fontSize: 14, height: 1.3),
      bodyMedium: text.bodyMedium?.copyWith(height: 1.3),
      bodySmall: text.bodySmall?.copyWith(
        color: scheme.onSurfaceVariant,
        height: 1.3,
      ),
    ),
    appBarTheme: AppBarTheme(
      actionsPadding: const EdgeInsetsDirectional.only(end: 16),
      centerTitle: false,
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: Colors.transparent,
      titleTextStyle: text.titleLarge?.copyWith(
        color: scheme.onSurface,
        fontSize: 21,
        fontWeight: FontWeight.w700,
      ),
      surfaceTintColor: Colors.transparent,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface.withValues(alpha: .24),
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      border: fieldBorder,
      enabledBorder: fieldBorder,
      focusedBorder: fieldBorder.copyWith(
        borderSide: BorderSide(color: scheme.primary, width: 2),
      ),
      errorBorder: fieldBorder.copyWith(
        borderSide: BorderSide(color: scheme.error),
      ),
      focusedErrorBorder: fieldBorder.copyWith(
        borderSide: BorderSide(color: scheme.error, width: 2),
      ),
      helperMaxLines: 3,
      errorMaxLines: 3,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: scheme.surfaceContainerLow,
        foregroundColor: scheme.onSurface,
        minimumSize: const Size(40, 32),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: shape,
        textStyle: text.labelLarge?.copyWith(
          fontSize: 14,
          fontWeight: FontWeight.w600,
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        backgroundColor: scheme.surfaceContainerLow,
        foregroundColor: scheme.onSurface,
        minimumSize: const Size(40, 32),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        shape: shape,
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(40, 32),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    ),
    iconButtonTheme: IconButtonThemeData(
      style: IconButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? const Color(0xFF6240B8)
              : Colors.transparent,
        ),
        foregroundColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? Colors.white
              : scheme.onSurface,
        ),
        side: WidgetStatePropertyAll(BorderSide(color: scheme.outlineVariant)),
        shape: WidgetStatePropertyAll(
          RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        visualDensity: VisualDensity.compact,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 64,
      indicatorColor: Colors.transparent,
      iconTheme: WidgetStateProperty.resolveWith(
        (states) => IconThemeData(
          size: 26,
          color: states.contains(WidgetState.selected)
              ? scheme.primary
              : scheme.onSurfaceVariant,
        ),
      ),
      labelTextStyle: WidgetStateProperty.resolveWith(
        (states) => TextStyle(
          fontSize: 12,
          color: states.contains(WidgetState.selected)
              ? scheme.primary
              : scheme.onSurfaceVariant,
        ),
      ),
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant,
      thickness: .5,
      indent: 16,
      endIndent: 16,
    ),
    listTileTheme: const ListTileThemeData(
      dense: true,
      contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 0),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      linearTrackColor: scheme.surfaceContainerHighest,
      borderRadius: BorderRadius.circular(8),
      linearMinHeight: 4,
    ),
    dialogTheme: const DialogThemeData(
      backgroundColor: Colors.transparent,
      elevation: 0,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
    ),
    popupMenuTheme: PopupMenuThemeData(
      elevation: 0,
      shadowColor: Colors.transparent,
      color: scheme.surfaceContainerLow,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: Colors.transparent,
      selectedColor: scheme.primary.withValues(alpha: .25),
      side: BorderSide(color: scheme.outlineVariant),
      shape: shape,
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
    ),
  );
}

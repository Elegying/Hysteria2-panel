import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class RefreshWarning extends StatelessWidget {
  const RefreshWarning({required this.message, super.key});
  final String message;

  @override
  Widget build(BuildContext context) => Material(
    color: Theme.of(context).colorScheme.errorContainer,
    borderRadius: BorderRadius.circular(12),
    child: Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_rounded),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    ),
  );
}

/// Static tinted backdrop makes the frosted surfaces visible without motion.
class LiquidBackdrop extends StatelessWidget {
  const LiquidBackdrop({required this.child, super.key});
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: (dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark)
          .copyWith(
            statusBarColor: Colors.transparent,
            systemNavigationBarColor: theme.colorScheme.surface,
            systemNavigationBarIconBrightness: dark
                ? Brightness.light
                : Brightness.dark,
          ),
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: dark
                ? [
                    const Color(0xFF0B111D),
                    Color.alphaBlend(
                      theme.colorScheme.primary.withValues(alpha: .09),
                      const Color(0xFF11151F),
                    ),
                    const Color(0xFF101B23),
                  ]
                : [
                    const Color(0xFFF2F6FB),
                    Color.alphaBlend(
                      theme.colorScheme.primary.withValues(alpha: .10),
                      const Color(0xFFF5F5FA),
                    ),
                    const Color(0xFFE8F3F1),
                  ],
          ),
        ),
        child: BackdropGroup(child: child),
      ),
    );
  }
}

class GlassSurface extends StatelessWidget {
  const GlassSurface({
    required this.child,
    this.borderRadius = 20,
    this.blurSigma = 0,
    this.margin,
    this.grouped = false,
    super.key,
  });

  final bool grouped;
  final Widget child;
  final double borderRadius;
  final double blurSigma;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final dark = Theme.of(context).brightness == Brightness.dark;
    final opaque = MediaQuery.highContrastOf(context);
    final floating = blurSigma > 0;
    final radius = BorderRadius.circular(borderRadius);
    final surface = DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: opaque
              ? [scheme.surfaceContainerLow, scheme.surfaceContainerLow]
              : dark
              ? [
                  const Color(0xFF293342).withValues(alpha: .72),
                  const Color(0xFF1B2533).withValues(alpha: .52),
                ]
              : [
                  Colors.white.withValues(alpha: .80),
                  Colors.white.withValues(alpha: .52),
                ],
        ),
      ),
      child: Material(type: MaterialType.transparency, child: child),
    );
    return Container(
      margin: margin,
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: MediaQuery.highContrastOf(context)
              ? scheme.outline
              : Colors.white.withValues(alpha: dark ? .16 : .75),
          width: MediaQuery.highContrastOf(context) ? 1.5 : .5,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: dark ? .20 : .055),
            blurRadius: floating ? 24 : 14,
            offset: const Offset(0, 6),
            spreadRadius: -4,
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: floating && !opaque
            ? grouped
                  ? BackdropFilter.grouped(
                      filter: ImageFilter.blur(
                        sigmaX: blurSigma,
                        sigmaY: blurSigma,
                      ),
                      child: surface,
                    )
                  : BackdropFilter(
                      filter: ImageFilter.blur(
                        sigmaX: blurSigma,
                        sigmaY: blurSigma,
                      ),
                      child: surface,
                    )
            : surface,
      ),
    );
  }
}

class GlassCard extends StatelessWidget {
  const GlassCard({
    required this.child,
    this.margin,
    this.blurSigma = 12,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry? margin;
  final double blurSigma;

  @override
  Widget build(BuildContext context) => GlassSurface(
    margin: margin,
    blurSigma: blurSigma,
    grouped: true,
    child: child,
  );
}

Color glassMenuColor(BuildContext context) {
  return Theme.of(context).colorScheme.surfaceContainerLow;
}

// Keep caller-owned input controllers alive until the closing animation ends.
Future<T?> showGlassFormDialog<T>({
  required BuildContext context,
  required WidgetBuilder builder,
}) async {
  ModalRoute<T>? route;
  final result = await showDialog<T>(
    context: context,
    builder: (context) {
      route = ModalRoute.of<T>(context);
      return builder(context);
    },
  );
  await route?.completed;
  return result;
}

class GlassDialog extends StatelessWidget {
  const GlassDialog({
    this.title,
    this.content,
    this.actions = const [],
    super.key,
  });

  final Widget? title;
  final Widget? content;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) => Dialog(
    backgroundColor: Colors.transparent,
    elevation: 0,
    shadowColor: Colors.transparent,
    child: GlassSurface(
      borderRadius: 24,
      blurSigma: 24,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(22, 22, 22, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (title != null)
                DefaultTextStyle.merge(
                  style: Theme.of(context).textTheme.titleLarge
                      ?.copyWith(fontWeight: FontWeight.w800),
                  child: title!,
                ),
              if (title != null && content != null) const SizedBox(height: 16),
              if (content != null)
                Flexible(
                  fit: FlexFit.loose,
                  child: DefaultTextStyle.merge(
                    style: Theme.of(context).textTheme.bodyMedium,
                    child: content!,
                  ),
                ),
              if (actions.isNotEmpty) const SizedBox(height: 18),
              if (actions.isNotEmpty)
                Wrap(
                  alignment: WrapAlignment.end,
                  spacing: 8,
                  runSpacing: 8,
                  children: actions,
                ),
            ],
          ),
        ),
      ),
    ),
  );
}

Future<T?> showGlassModalBottomSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
}) => showModalBottomSheet<T>(
  context: context,
  isScrollControlled: true,
  backgroundColor: Colors.transparent,
  barrierColor: Colors.black.withValues(alpha: .38),
  showDragHandle: false,
  builder: (sheetContext) => GlassSurface(
    borderRadius: 28,
    blurSigma: 24,
    child: Stack(
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 22),
          child: builder(sheetContext),
        ),
        Positioned(
          top: 9,
          left: 0,
          right: 0,
          child: Center(
            child: Container(
              width: 34,
              height: 4,
              decoration: BoxDecoration(
                color: Theme.of(sheetContext).colorScheme.onSurfaceVariant
                    .withValues(alpha: .45),
                borderRadius: BorderRadius.circular(99),
              ),
            ),
          ),
        ),
      ],
    ),
  ),
);

import 'dart:ui';

import 'package:flutter/material.dart';

/// Shared background and surfaces for the app's lightweight liquid-glass UI.
class LiquidBackdrop extends StatelessWidget {
  const LiquidBackdrop({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final dark = Theme.of(context).brightness == Brightness.dark;
    return ColoredBox(
      color: dark ? const Color(0xFF04101D) : const Color(0xFFEFF5FF),
      child: Stack(
        fit: StackFit.expand,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: dark
                    ? const [
                        Color(0xFF061526),
                        Color(0xFF0A1730),
                        Color(0xFF071A23),
                      ]
                    : const [
                        Color(0xFFF8FBFF),
                        Color(0xFFEDF4FF),
                        Color(0xFFF4FAF8),
                      ],
              ),
            ),
          ),
          _Glow(
            alignment: const Alignment(-1.15, -1.05),
            color: scheme.primary.withValues(alpha: dark ? .28 : .22),
          ),
          _Glow(
            alignment: const Alignment(1.15, -.05),
            color: scheme.tertiary.withValues(alpha: dark ? .20 : .16),
          ),
          _Glow(
            alignment: const Alignment(-.15, 1.25),
            color: scheme.secondary.withValues(alpha: dark ? .16 : .12),
          ),
          child,
        ],
      ),
    );
  }
}

class _Glow extends StatelessWidget {
  const _Glow({required this.alignment, required this.color});

  final Alignment alignment;
  final Color color;

  @override
  Widget build(BuildContext context) => IgnorePointer(
    child: DecoratedBox(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: alignment,
          radius: 1.15,
          colors: [color, color.withValues(alpha: 0)],
          stops: const [0, 1],
        ),
      ),
    ),
  );
}

class GlassSurface extends StatelessWidget {
  const GlassSurface({
    required this.child,
    this.borderRadius = 20,
    this.blurSigma = 0,
    this.margin,
    super.key,
  });

  final Widget child;
  final double borderRadius;
  final double blurSigma;
  final EdgeInsetsGeometry? margin;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final radius = BorderRadius.circular(borderRadius);
    final surface = DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: dark
              ? [
                  Colors.white.withValues(alpha: .105),
                  Colors.white.withValues(alpha: .045),
                ]
              : [
                  Colors.white.withValues(alpha: .84),
                  Colors.white.withValues(alpha: .48),
                ],
        ),
        border: Border.all(
          color: Colors.white.withValues(alpha: dark ? .17 : .82),
        ),
        borderRadius: radius,
      ),
      child: Material(type: MaterialType.transparency, child: child),
    );
    return Container(
      margin: margin,
      decoration: BoxDecoration(
        borderRadius: radius,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: dark ? .24 : .08),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
          BoxShadow(
            color: Colors.white.withValues(alpha: dark ? .025 : .45),
            blurRadius: 1,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: blurSigma > 0
            ? BackdropFilter(
                filter: ImageFilter.blur(sigmaX: blurSigma, sigmaY: blurSigma),
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
    this.blurSigma = 0,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry? margin;
  final double blurSigma;

  @override
  Widget build(BuildContext context) =>
      GlassSurface(margin: margin, blurSigma: blurSigma, child: child);
}

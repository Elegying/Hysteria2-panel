// Adapted from SSRVPN shared UI, local snapshot 2026-09-14.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'h2_glass_capture.dart';

/// Animate only the wallpaper; foreground controls remain still and reusable.
class H2DriftingBackground extends StatefulWidget {
  const H2DriftingBackground({
    super.key,
    required this.child,
    this.captureBackground = false,
  });
  final Widget child;
  final bool captureBackground;
  @override
  State<H2DriftingBackground> createState() => _H2DriftingBackgroundState();
}

class _H2DriftingBackgroundState extends State<H2DriftingBackground>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _motion = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 18),
  );
  bool _reducedMotion = true;
  bool _visible = true;
  ModalRoute<dynamic>? _route;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _motion.addListener(_updateCaptureOrigin);
  }

  void _updateCaptureOrigin() {
    if (widget.captureBackground) H2GlassFrame.requestOriginUpdate(context);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _reducedMotion = MediaQuery.disableAnimationsOf(context);
    final route = ModalRoute.of(context);
    if (_route != route) {
      _listenToRoute(false);
      _route = route;
      _listenToRoute(true);
    }
    // A translucent popup leaves the underlying route mounted. Pause its
    // decorative motion so every obscured glass card does not rasterize again.
    _visible =
        TickerMode.valuesOf(context).enabled &&
        (ModalRoute.isCurrentOf(context) ?? true);
    _updateMotion();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => _updateMotion();

  void _listenToRoute(bool add) {
    for (final animation in [_route?.animation, _route?.secondaryAnimation]) {
      if (add) {
        animation?.addStatusListener(_routeStatusChanged);
      } else {
        animation?.removeStatusListener(_routeStatusChanged);
      }
    }
  }

  void _routeStatusChanged(AnimationStatus _) => _updateMotion();

  void _updateMotion() {
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    final active =
        !_reducedMotion &&
        _visible &&
        lifecycle == AppLifecycleState.resumed &&
        (_route?.animation == null ||
            _route!.animation!.status == AnimationStatus.completed) &&
        (_route?.secondaryAnimation == null ||
            _route!.secondaryAnimation!.status == AnimationStatus.dismissed);
    if (active && !_motion.isAnimating) {
      _motion.repeat();
    } else if (!active) {
      _motion.stop();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _listenToRoute(false);
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ClipRect(
    child: LayoutBuilder(
      builder: (context, constraints) => OverflowBox(
        minWidth: constraints.maxWidth * 1.16,
        maxWidth: constraints.maxWidth * 1.16,
        minHeight: constraints.maxHeight * 1.16,
        maxHeight: constraints.maxHeight * 1.16,
        child: AnimatedBuilder(
          animation: _motion,
          // Capture pixels inside the translation: motion changes only origin.
          // Late image paints still invalidate the capture boundary itself.
          child: widget.captureBackground
              ? H2GlassBackgroundSource(
                  child: ExcludeSemantics(child: widget.child),
                )
              : ExcludeSemantics(child: widget.child),
          builder: (context, child) {
            final t = (1 - math.cos(_motion.value * 2 * math.pi)) / 2;
            return FractionalTranslation(
              translation: Offset((t - .5) * .11, (.5 - t) * .08),
              child: child,
            );
          },
        ),
      ),
    ),
  );
}

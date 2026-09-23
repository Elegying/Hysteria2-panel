import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:liquid_glass_widgets/liquid_glass_widgets.dart' as liquid;

import 'h2_glass_capture.dart';
import 'h2_drifting_background.dart';

double appDockExtent(BuildContext context) =>
    104 + (MediaQuery.textScalerOf(context).scale(12) - 12).clamp(0, 100) * 2;

class RefreshWarning extends StatelessWidget {
  const RefreshWarning({required this.message, super.key});
  final String message;

  @override
  Widget build(BuildContext context) => GlassSurface(
    tintColor: Theme.of(context).colorScheme.errorContainer
        .withValues(alpha: .65),
    borderRadius: 12,
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

/// Shared SSRVPN capture/paint lifecycle, with this app's artwork and palette.
class LiquidBackdrop extends StatelessWidget {
  const LiquidBackdrop({required this.child, super.key});
  final Widget child;
  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final shade = dark ? const Color(0x4005111F) : const Color(0xDDF0F5FA);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: (dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark)
          .copyWith(
            statusBarColor: Colors.transparent,
            systemNavigationBarColor: Colors.transparent,
          ),
      child: liquid.LiquidGlassScope(
        child: H2GlassCapture(
          child: Stack(
            fit: StackFit.expand,
            children: [
              Positioned.fill(
                child: IgnorePointer(
                  child: H2DriftingBackground(
                    captureBackground: true,
                    child: SizedBox.expand(
                      child: Image.asset(
                        'assets/liquid-tech-background.png',
                        fit: BoxFit.cover,
                        filterQuality: FilterQuality.medium,
                        color: shade,
                        colorBlendMode: BlendMode.srcATop,
                        frameBuilder: (_, image, frame, synchronous) =>
                            frame != null || synchronous
                            ? image
                            : ColoredBox(color: shade, child: image),
                      ),
                    ),
                  ),
                ),
              ),
              child,
            ],
          ),
        ),
      ),
    );
  }
}

/// Keep native focus, validation and semantics inside the optical surface.
class GlassControlSurface extends StatelessWidget {
  const GlassControlSurface({required this.child, super.key});
  final Widget child;
  @override
  Widget build(BuildContext context) => GlassSurface(
    borderRadius: 16,
    blurSigma: 5,
    child: child is TextField || child is TextFormField
        ? Padding(
            padding: const EdgeInsets.only(top: 10, bottom: 2),
            child: child,
          )
        : child,
  );
}

/// Keep scrolling cards in independent layers. Shared moving shader groups can
/// sample a stale backdrop when a sliver crosses the viewport on Impeller.
class GlassSliverList extends StatelessWidget {
  const GlassSliverList({
    required this.itemCount,
    required this.itemBuilder,
    this.spacing = 8,
    super.key,
  });
  final int itemCount;
  final IndexedWidgetBuilder itemBuilder;
  final double spacing;
  @override
  Widget build(BuildContext context) => SliverList.separated(
    itemCount: itemCount,
    itemBuilder: itemBuilder,
    separatorBuilder: (_, _) => SizedBox(height: spacing),
  );
}

class GlassSurface extends StatelessWidget {
  const GlassSurface({
    required this.child,
    this.borderRadius = 20,
    this.blurSigma = 8,
    this.margin,
    this.grouped = false,
    this.tintColor,
    super.key,
  });

  final bool grouped;
  final Color? tintColor;
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
    if (floating && !opaque) {
      final shape = liquid.LiquidRoundedSuperellipse(
        borderRadius: borderRadius,
      );
      final settings = liquid.LiquidGlassSettings(
        thickness: 24,
        blur: blurSigma,
        chromaticAberration: .025,
        lightIntensity: dark ? .65 : .8,
        refractiveIndex: 1.3,
        glassColor:
            tintColor ??
            (dark ? const Color(0x241B304A) : const Color(0x60FFFFFF)),
      );
      final content = Material(type: MaterialType.transparency, child: child);
      final frames = H2GlassFrame.listenableOf(context);
      final useCapture =
          ui.ImageFilter.isShaderFilterSupported && frames != null;
      final surface = liquid.GlassContainer(
        margin: margin,
        shape: shape,
        quality: liquid.GlassQuality.premium,
        useOwnLayer: !useCapture,
        clipBehavior: Clip.antiAlias,
        settings: settings,
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: radius,
            border: Border.all(color: Colors.white.withValues(alpha: .18)),
          ),
          child: content,
        ),
      );
      if (!useCapture) return surface;
      return ValueListenableBuilder<H2GlassFrame?>(
        valueListenable: frames,
        child: liquid.LiquidGlassBlendGroup(
          blend: 0,
          child: liquid.GlassIsolationScope(isolated: false, child: surface),
        ),
        builder: (context, captured, child) => liquid.LiquidGlassLayer(
          settings: settings,
          captureOnly: true,
          captureImage: captured?.image,
          captureOriginInScreenSpace: captured?.origin ?? Offset.zero,
          child: child!,
        ),
      );
    }
    return Container(
      margin: margin,
      decoration: BoxDecoration(
        color: tintColor == null
            ? scheme.surfaceContainerLow
            : Color.alphaBlend(tintColor!, scheme.surfaceContainerLow),
        borderRadius: radius,
        border: Border.all(
          color: opaque
              ? scheme.outline
              : scheme.outlineVariant.withValues(alpha: .45),
          width: opaque ? 1.5 : .5,
        ),
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: Material(type: MaterialType.transparency, child: child),
      ),
    );
  }
}

class GlassCard extends StatelessWidget {
  const GlassCard({
    required this.child,
    this.margin,
    this.blurSigma = 8,
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

/// Keep action errors above the modal route that initiated the request.
Future<void> showGlassError(BuildContext context, String message) =>
    showDialog<void>(
      context: context,
      builder: (dialogContext) => GlassDialog(
        title: const Text('操作未完成'),
        content: SingleChildScrollView(child: Text(message)),
        actions: [
          GlassControlSurface(
            child: TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('关闭'),
            ),
          ),
        ],
      ),
    );

/// A glass selection sheet replaces the platform's opaque dropdown popup.
class GlassDropdownField<T> extends StatelessWidget {
  const GlassDropdownField({
    required this.items,
    required this.onChanged,
    required this.decoration,
    this.initialValue,
    this.hint,
    super.key,
  });
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?>? onChanged;
  final InputDecoration decoration;
  final T? initialValue;
  final Widget? hint;

  @override
  Widget build(BuildContext context) {
    Widget? selected;
    for (final item in items) {
      if (item.value == initialValue) selected = item.child;
    }
    return GlassControlSurface(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onChanged == null
            ? null
            : () async {
                final result = await showGlassFormDialog<T>(
                  context: context,
                  builder: (dialogContext) => GlassDialog(
                    title: Text(decoration.labelText ?? '请选择'),
                    content: SingleChildScrollView(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          for (final item in items)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 8),
                              child: GlassControlSurface(
                                child: ListTile(
                                  title: item.child,
                                  selected: item.value == initialValue,
                                  trailing: item.value == initialValue
                                      ? const Icon(Icons.check_rounded)
                                      : null,
                                  onTap: item.enabled
                                      ? () => Navigator.pop(
                                          dialogContext,
                                          item.value,
                                        )
                                      : null,
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                );
                if (context.mounted && result != null) onChanged?.call(result);
              },
        child: InputDecorator(
          decoration: decoration.copyWith(
            floatingLabelBehavior: FloatingLabelBehavior.never,
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (decoration.labelText != null)
                      Text(
                        decoration.labelText!,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    selected ?? hint ?? const Text('请选择'),
                  ],
                ),
              ),
              const Icon(Icons.expand_more_rounded),
            ],
          ),
        ),
      ),
    );
  }
}

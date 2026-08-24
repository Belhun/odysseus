import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../theme/ody_theme.dart';

final _money = NumberFormat.currency(symbol: r'$', decimalDigits: 2);

String money(int cents, {bool privacy = false}) {
  if (privacy) return '••••';
  return _money.format(cents / 100.0);
}

Color parseHexColor(String? hex, [Color fallback = OdyColors.accent]) {
  if (hex == null || hex.isEmpty) return fallback;
  var s = hex.replaceAll('#', '');
  if (s.length == 3) {
    s = s.split('').map((c) => '$c$c').join();
  }
  if (s.length == 6) s = 'FF$s';
  final value = int.tryParse(s, radix: 16);
  if (value == null) return fallback;
  return Color(value);
}

class OdyCard extends StatelessWidget {
  const OdyCard({super.key, required this.child, this.onTap, this.padding});

  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final body = Padding(
      padding: padding ?? const EdgeInsets.all(14),
      child: child,
    );
    return Card(
      clipBehavior: Clip.antiAlias,
      child: onTap == null
          ? body
          : InkWell(onTap: onTap, child: body),
    );
  }
}

class ErrorBody extends StatelessWidget {
  const ErrorBody({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: OdyColors.red, size: 36),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            if (onRetry != null) ...[
              const SizedBox(height: 16),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ],
        ),
      ),
    );
  }
}

class MonthPickerButton extends StatelessWidget {
  const MonthPickerButton({
    super.key,
    required this.month,
    required this.onChanged,
  });

  final String month;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: () async {
        final parts = month.split('-');
        final initial = DateTime(int.parse(parts[0]), int.parse(parts[1]));
        final picked = await showDatePicker(
          context: context,
          initialDate: initial,
          firstDate: DateTime(2018),
          lastDate: DateTime.now().add(const Duration(days: 366)),
          helpText: 'Pick a day in the month',
        );
        if (picked == null) return;
        onChanged(
          '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}',
        );
      },
      icon: const Icon(Icons.calendar_month, size: 18),
      label: Text(month),
    );
  }
}

Future<void> showBusyError(BuildContext context, Object error) {
  return showDialog<void>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: const Text('Request failed'),
      content: Text('$error'),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK')),
      ],
    ),
  );
}

class PlaceholderScreen extends StatelessWidget {
  const PlaceholderScreen({
    super.key,
    required this.title,
    required this.reason,
    this.closest,
  });

  final String title;
  final String reason;
  final String? closest;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: OdyCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(reason),
              if (closest != null) ...[
                const SizedBox(height: 12),
                Text('Closest working screen: $closest',
                    style: const TextStyle(color: OdyColors.subheader)),
              ],
              const SizedBox(height: 8),
              const Text(
                'This is a labeled placeholder. It does not store a local ledger.',
                style: TextStyle(color: OdyColors.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

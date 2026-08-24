import 'package:flutter/material.dart';

import '../api/models.dart';
import '../api/sankey_client.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'transactions_screen.dart';

class SankeyScreen extends StatefulWidget {
  const SankeyScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<SankeyScreen> createState() => _SankeyScreenState();
}

class _SankeyScreenState extends State<SankeyScreen> {
  String _month = currentMonthKey();
  bool _loading = true;
  String? _error;
  SankeyReport? _report;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final report = await SankeyClient(widget.controller.odyHttp).forMonth(_month);
      if (!mounted) return;
      setState(() {
        _report = report;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  void _openCategory(SankeyNode node) {
    final uncategorized =
        node.id == 'uncategorized' || node.categoryId == null || node.categoryId!.isEmpty;
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => TransactionsScreen(
          controller: widget.controller,
          initialCategoryId: uncategorized ? null : node.categoryId,
          initialMonth: _month,
          uncategorized: uncategorized,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.controller,
      builder: (context, _) {
        final privacy = widget.controller.privacyMode;
        return Scaffold(
          appBar: AppBar(title: const Text('Cashflow map')),
          body: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? ErrorBody(message: _error!, onRetry: _load)
                  : RefreshIndicator(onRefresh: _load, child: _body(privacy)),
        );
      },
    );
  }

  Widget _body(bool privacy) {
    final report = _report;
    if (report == null) return const SizedBox.shrink();
    final flows = report.nodes.where((n) => n.kind == 'category' || n.kind == 'leftover').toList();
    final empty = report.incomeCents == 0 && report.links.isEmpty;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      children: [
        MonthPickerButton(
          month: _month,
          onChanged: (m) {
            _month = m;
            _load();
          },
        ),
        const SizedBox(height: 8),
        if (report.incomplete)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: OdyCard(
              child: Text(
                'This month is incomplete — ${report.unclassifiedCount} unclassified row(s), '
                '${money(report.unclassifiedOutflowCents, privacy: privacy)} outflow counted by sign. '
                'Not fully true spend.',
                style: const TextStyle(color: OdyColors.warn),
              ),
            ),
          ),
        OdyCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Income', style: TextStyle(color: OdyColors.subheader)),
              Text(
                money(report.incomeCents, privacy: privacy),
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              const Text(
                'True income → true spend by category. Transfers are not spend.',
                style: TextStyle(fontSize: 12, color: OdyColors.muted),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        if (empty)
          const OdyCard(child: Text('No cashflow this month.'))
        else ...[
          SizedBox(
            height: (flows.length * 44.0).clamp(120, 280),
            child: CustomPaint(
              painter: _SankeyPainter(report: report),
              child: const SizedBox.expand(),
            ),
          ),
          const SizedBox(height: 10),
          OdyCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Flows', style: TextStyle(color: OdyColors.subheader)),
                ...flows.map((n) {
                  return InkWell(
                    onTap: n.kind == 'category' ? () => _openCategory(n) : null,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Row(
                        children: [
                          Expanded(child: Text('Income → ${n.label}')),
                          Text(money(n.cents, privacy: privacy)),
                        ],
                      ),
                    ),
                  );
                }),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

class _SankeyPainter extends CustomPainter {
  _SankeyPainter({required this.report});

  final SankeyReport report;

  @override
  void paint(Canvas canvas, Size size) {
    final flows = report.nodes.where((n) => n.kind == 'category' || n.kind == 'leftover').toList();
    if (flows.isEmpty) return;
    final total = flows.fold<int>(0, (s, n) => s + n.cents);
    if (total <= 0) return;
    const leftW = 72.0;
    final rightW = size.width * 0.42;
    final rightX = size.width - rightW;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(0, 8, leftW, size.height - 16),
        const Radius.circular(6),
      ),
      Paint()..color = OdyColors.green.withValues(alpha: 0.85),
    );
    var y = 8.0;
    for (final n in flows) {
      final h = ((n.cents / total) * (size.height - 16)).clamp(16.0, size.height);
      final color = n.kind == 'leftover' ? OdyColors.green : parseHexColor(n.color, OdyColors.accent);
      canvas.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(rightX, y, rightW, h - 6),
          const Radius.circular(6),
        ),
        Paint()..color = color.withValues(alpha: 0.9),
      );
      final path = Path()
        ..moveTo(leftW, size.height / 2)
        ..cubicTo(
          leftW + 48,
          size.height / 2,
          rightX - 48,
          y + (h - 6) / 2,
          rightX,
          y + (h - 6) / 2,
        );
      canvas.drawPath(
        path,
        Paint()
          ..color = color.withValues(alpha: 0.35)
          ..style = PaintingStyle.stroke
          ..strokeWidth = (h / 3).clamp(3, 18),
      );
      y += h;
    }
  }

  @override
  bool shouldRepaint(covariant _SankeyPainter oldDelegate) => oldDelegate.report != report;
}

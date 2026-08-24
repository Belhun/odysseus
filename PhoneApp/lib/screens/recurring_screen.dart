import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class RecurringScreen extends StatefulWidget {
  const RecurringScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<RecurringScreen> createState() => _RecurringScreenState();
}

class _RecurringScreenState extends State<RecurringScreen> {
  bool _loading = true;
  String? _error;
  List<RecurringSeries> _series = [];

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
      final series = await widget.controller.finance!.recurring();
      if (!mounted) return;
      setState(() {
        _series = series;
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

  Future<void> _setStatus(RecurringSeries row, String status) async {
    try {
      await widget.controller.finance!.patchRecurring(row.id, {'status': status});
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(title: const Text('Recurring')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 24),
                    children: [
                      const Text(
                        'Odysseus detects subscriptions from payee history. This is the same series list as the web Recurring tab.',
                        style: TextStyle(color: OdyColors.subheader),
                      ),
                      const SizedBox(height: 12),
                      if (_series.isEmpty)
                        const OdyCard(
                          child: Text('No series yet. Import a few months of spend and pull to refresh.'),
                        )
                      else
                        ..._series.map(
                          (s) => Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: OdyCard(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          s.displayPayee,
                                          style: const TextStyle(fontWeight: FontWeight.w600),
                                        ),
                                      ),
                                      Text(money(s.medianAmountCents.abs(), privacy: privacy)),
                                    ],
                                  ),
                                  Text(
                                    '${s.cadence} · next ${s.nextDueDate ?? '—'} · ~${money(s.monthlyNormalizedCents, privacy: privacy)}/mo',
                                    style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                                  ),
                                  const SizedBox(height: 8),
                                  Wrap(
                                    spacing: 8,
                                    children: [
                                      for (final st in ['active', 'paused', 'ignored'])
                                        ChoiceChip(
                                          label: Text(st),
                                          selected: s.status == st,
                                          onSelected: (_) => _setStatus(s, st),
                                        ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
    );
  }
}

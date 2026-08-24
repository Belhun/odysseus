import 'package:flutter/material.dart';

import '../api/models.dart';
import '../api/recurring_status.dart';
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
  List<FinanceCategory> _categories = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load({bool showSpinner = true}) async {
    if (showSpinner) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final api = widget.controller.finance!;
      final results = await Future.wait([
        api.recurring(),
        api.listCategories(),
      ]);
      final series = visibleRecurringSeries(results[0] as List<RecurringSeries>);
      final cats = results[1] as List<FinanceCategory>;
      if (!mounted) return;
      widget.controller.cachedRecurring = series;
      setState(() {
        _series = series;
        _categories = cats;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  Future<void> _setStatus(RecurringSeries row, RecurringStatusChip chip) async {
    if (chip.apiStatus == 'automatic' && !row.canMarkAutomatic) return;
    try {
      final body = recurringStatusPatchBody(
        apiStatus: chip.apiStatus,
        categories: _categories,
      );
      if (chip.apiStatus == 'automatic' && body['category_id'] == null) {
        if (mounted) {
          await showBusyError(context, 'Automatic recurring needs a category');
        }
        return;
      }
      await widget.controller.finance!.patchRecurring(row.id, body);
      if (!mounted) return;
      if (chip.apiStatus == 'dismissed') {
        setState(() => _series.removeWhere((s) => s.id == row.id));
      }
      await _load(showSpinner: false);
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
                      const SizedBox(height: 6),
                      const Text(
                        'Automatic is a label, not a posted bill. Ignore dismisses a series and removes it from this list.',
                        style: TextStyle(color: OdyColors.muted, fontSize: 12),
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
                                      for (final chip in kRecurringStatusChips)
                                        ChoiceChip(
                                          label: Text(chip.label),
                                          selected: s.status == chip.apiStatus,
                                          onSelected: chip.apiStatus == 'automatic' &&
                                                  !s.canMarkAutomatic
                                              ? null
                                              : (_) => _setStatus(s, chip),
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

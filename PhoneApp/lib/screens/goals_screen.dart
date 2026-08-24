import 'package:flutter/material.dart';

import '../api/goals_client.dart';
import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class GoalsScreen extends StatefulWidget {
  const GoalsScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<GoalsScreen> createState() => _GoalsScreenState();
}

class _GoalsScreenState extends State<GoalsScreen> {
  bool _loading = true;
  String? _error;
  List<FinanceGoal> _goals = [];
  List<FinanceAccount> _accounts = [];
  List<FinanceCategory> _categories = [];

  GoalsClient get _api => GoalsClient(widget.controller.odyHttp);

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
      final finance = widget.controller.finance;
      final goals = await _api.list();
      var accounts = <FinanceAccount>[];
      var categories = <FinanceCategory>[];
      if (finance != null) {
        accounts = await finance.listAccounts();
        categories = await finance.listCategories();
      }
      if (!mounted) return;
      setState(() {
        _goals = goals;
        _accounts = accounts;
        _categories = categories;
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

  Future<void> _edit({FinanceGoal? existing}) async {
    final name = TextEditingController(text: existing?.name ?? '');
    final target = TextEditingController(
      text: existing == null ? '' : (existing.targetCents / 100).toStringAsFixed(2),
    );
    final baseline = TextEditingController(
      text: existing == null || existing.baselineCents == 0
          ? ''
          : (existing.baselineCents / 100).toStringAsFixed(2),
    );
    var kind = existing?.kind ?? 'account';
    var accountId = existing?.accountId;
    var categoryId = existing?.categoryId;
    var dateStr = existing?.targetDate;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: Text(existing == null ? 'New goal' : 'Edit goal'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
                TextField(
                  controller: target,
                  decoration: const InputDecoration(labelText: 'Target dollars'),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                ),
                TextField(
                  controller: baseline,
                  decoration: const InputDecoration(labelText: 'Baseline dollars (optional)'),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                ),
                DropdownButton<String>(
                  value: kind,
                  isExpanded: true,
                  items: const [
                    DropdownMenuItem(value: 'account', child: Text('Account-linked')),
                    DropdownMenuItem(value: 'loan', child: Text('Loan payoff')),
                    DropdownMenuItem(value: 'category', child: Text('Category')),
                  ],
                  onChanged: (v) => setLocal(() => kind = v ?? 'account'),
                ),
                if (kind != 'category')
                  DropdownButton<String>(
                    value: _accounts.any((a) => a.id == accountId) ? accountId : null,
                    hint: const Text('Account'),
                    isExpanded: true,
                    items: [
                      const DropdownMenuItem<String>(value: null, child: Text('None')),
                      ..._accounts.map(
                        (a) => DropdownMenuItem(value: a.id, child: Text(a.name)),
                      ),
                    ],
                    onChanged: (v) => setLocal(() => accountId = v),
                  ),
                if (kind == 'category')
                  DropdownButton<String>(
                    value: _categories.any((c) => c.id == categoryId) ? categoryId : null,
                    hint: const Text('Category'),
                    isExpanded: true,
                    items: [
                      const DropdownMenuItem<String>(value: null, child: Text('None')),
                      ..._categories.map(
                        (c) => DropdownMenuItem(value: c.id, child: Text(c.displayName)),
                      ),
                    ],
                    onChanged: (v) => setLocal(() => categoryId = v),
                  ),
                TextButton(
                  onPressed: () async {
                    final now = DateTime.now();
                    final picked = await showDatePicker(
                      context: ctx,
                      initialDate: dateStr == null
                          ? now
                          : DateTime.tryParse(dateStr!) ?? now,
                      firstDate: DateTime(now.year - 1),
                      lastDate: DateTime(now.year + 20),
                    );
                    if (picked != null) {
                      setLocal(() {
                        dateStr =
                            '${picked.year.toString().padLeft(4, '0')}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
                      });
                    }
                  },
                  child: Text(dateStr == null ? 'Target date (optional)' : 'Date $dateStr'),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
          ],
        ),
      ),
    );
    if (ok != true) return;
    final dollars = double.tryParse(target.text.replaceAll(',', '')) ?? 0;
    final baseDollars = double.tryParse(baseline.text.replaceAll(',', '')) ?? 0;
    final body = <String, dynamic>{
      'name': name.text.trim().isEmpty ? 'Goal' : name.text.trim(),
      'kind': kind,
      'target_cents': (dollars * 100).round(),
      'baseline_cents': (baseDollars * 100).round(),
      'target_date': dateStr,
      'account_id': kind == 'category' ? null : accountId,
      'category_id': kind == 'category' ? categoryId : null,
    };
    try {
      if (existing == null) {
        await _api.create(body);
      } else {
        await _api.patch(existing.id, body);
      }
      await _load();
    } catch (e) {
      if (mounted) await showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(title: const Text('Goals')),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _edit(),
        child: const Icon(Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: _goals.isEmpty
                      ? ListView(
                          children: const [
                            SizedBox(height: 80),
                            Center(child: Text('No goals yet')),
                            Padding(
                              padding: EdgeInsets.all(24),
                              child: Text(
                                'Link a savings account or loan. Progress uses posted balances, not envelopes.',
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ],
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
                          itemCount: _goals.length,
                          itemBuilder: (ctx, i) {
                            final g = _goals[i];
                            return Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: OdyCard(
                                onTap: () => _edit(existing: g),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(g.name, style: Theme.of(context).textTheme.titleMedium),
                                    Text('${g.kind}${g.targetDate != null ? ' · ${g.targetDate}' : ''}'),
                                    const SizedBox(height: 8),
                                    LinearProgressIndicator(
                                      value: (g.percent / 100).clamp(0, 1),
                                      color: parseHexColor(g.color),
                                      backgroundColor: OdyColors.border.withValues(alpha: 0.4),
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      '${money(g.currentCents, privacy: privacy)} / ${money(g.targetCents, privacy: privacy)} · ${g.percent}%',
                                    ),
                                    Text(
                                      'Left ${money(g.remainingCents, privacy: privacy)}',
                                      style: const TextStyle(color: OdyColors.muted),
                                    ),
                                    if (g.suggestedMonthlyCents != null)
                                      Text(
                                        'Suggested ${money(g.suggestedMonthlyCents!, privacy: privacy)} / mo',
                                        style: const TextStyle(color: OdyColors.muted),
                                      ),
                                    Align(
                                      alignment: Alignment.centerRight,
                                      child: TextButton(
                                        onPressed: () async {
                                          try {
                                            await _api.delete(g.id);
                                            await _load();
                                          } catch (e) {
                                            if (!context.mounted) return;
                                            await showBusyError(context, e);
                                          }
                                        },
                                        child: const Text('Delete'),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                ),
    );
  }
}

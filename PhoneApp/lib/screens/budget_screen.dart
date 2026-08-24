import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class BudgetScreen extends StatefulWidget {
  const BudgetScreen({super.key, required this.controller, this.monthClose = false});

  final AppController controller;
  final bool monthClose;

  @override
  State<BudgetScreen> createState() => _BudgetScreenState();
}

class _BudgetScreenState extends State<BudgetScreen> {
  late String _month;
  BudgetSnapshot? _snap;
  List<FinanceCategory> _cats = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _month = widget.monthClose ? previousMonthKey(currentMonthKey()) : currentMonthKey();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = widget.controller.finance!;
      final snap = await api.budgets(month: _month);
      final cats = await api.listCategories();
      if (!mounted) return;
      setState(() {
        _snap = snap;
        _cats = cats;
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

  Future<void> _editLimit(BudgetCategoryRow row) async {
    if (row.categoryId == null) return;
    final ctl = TextEditingController(
      text: row.limitCents == null ? '' : (row.limitCents! / 100).toStringAsFixed(2),
    );
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Limit · ${row.categoryName}'),
        content: TextField(
          controller: ctl,
          decoration: const InputDecoration(labelText: 'Monthly limit'),
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok != true) return;
    final dollars = double.tryParse(ctl.text.replaceAll(',', '')) ?? 0;
    try {
      await widget.controller.finance!.setBudget(
        categoryId: row.categoryId!,
        month: _month,
        limitCents: (dollars * 100).round().clamp(0, 1 << 31),
      );
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  Future<void> _copyFromPrevious() async {
    try {
      await widget.controller.finance!.copyBudgets(
        fromMonth: previousMonthKey(_month),
        toMonth: _month,
      );
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  Future<void> _setIncomeTarget() async {
    final ctl = TextEditingController(
      text: _snap?.incomeTargetCents == null
          ? ''
          : ((_snap!.incomeTargetCents ?? 0) / 100).toStringAsFixed(2),
    );
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Income target'),
        content: TextField(
          controller: ctl,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok != true) return;
    final dollars = double.tryParse(ctl.text.replaceAll(',', '')) ?? 0;
    try {
      await widget.controller.finance!.setIncomeTarget(
        month: _month,
        cents: (dollars * 100).round().clamp(0, 1 << 31),
      );
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  Future<void> _addCategory() async {
    final ctl = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New category'),
        content: TextField(controller: ctl, decoration: const InputDecoration(labelText: 'Name')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Add')),
        ],
      ),
    );
    if (ok != true || ctl.text.trim().isEmpty) return;
    try {
      await widget.controller.finance!.createCategory(name: ctl.text.trim());
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    final title = widget.monthClose ? 'Budget (test: month-close)' : 'Budget';
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
            tooltip: 'Add category',
            onPressed: _addCategory,
            icon: const Icon(Icons.category_outlined),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
                    children: [
                      if (widget.monthClose)
                        const Padding(
                          padding: EdgeInsets.only(bottom: 8),
                          child: Text(
                            'A/B test variant: review last month, then copy limits forward. Same API as Budget.',
                            style: TextStyle(color: OdyColors.subheader),
                          ),
                        ),
                      Row(
                        children: [
                          MonthPickerButton(
                            month: _month,
                            onChanged: (m) {
                              _month = m;
                              _load();
                            },
                          ),
                          const Spacer(),
                          TextButton(onPressed: _copyFromPrevious, child: const Text('Copy last month')),
                        ],
                      ),
                      if (_snap != null) ...[
                        OdyCard(
                          onTap: _setIncomeTarget,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Income ${_snap!.month}',
                                  style: const TextStyle(color: OdyColors.subheader)),
                              Text(money(_snap!.incomeCents, privacy: privacy),
                                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                              Text(
                                'Target ${money(_snap!.incomeTargetCents ?? 0, privacy: privacy)} · spend ${money(_snap!.netSpendCents, privacy: privacy)}',
                                style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        ..._snap!.categories.map((row) {
                          final limit = row.limitCents;
                          final frac = limit == null || limit == 0
                              ? 0.0
                              : (row.spentCents / limit).clamp(0.0, 1.0);
                          return Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: OdyCard(
                              onTap: () => _editLimit(row),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(child: Text(row.categoryName)),
                                      Text(money(row.spentCents, privacy: privacy)),
                                    ],
                                  ),
                                  Text(
                                    limit == null
                                        ? 'No limit · tap to set'
                                        : 'Limit ${money(limit, privacy: privacy)} · left ${money(row.remainingCents ?? 0, privacy: privacy)}',
                                    style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                                  ),
                                  if (limit != null)
                                    LinearProgressIndicator(
                                      value: frac.toDouble(),
                                      color: frac >= 1 ? OdyColors.red : OdyColors.accent,
                                      backgroundColor: OdyColors.border,
                                    ),
                                ],
                              ),
                            ),
                          );
                        }),
                        if (_snap!.categories.isEmpty)
                          Text(
                            _cats.isEmpty
                                ? 'No categories yet.'
                                : 'No spend in this month. Categories exist for limits.',
                          ),
                      ],
                    ],
                  ),
                ),
    );
  }
}

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../widgets/common.dart';

class TransactionEditScreen extends StatefulWidget {
  const TransactionEditScreen({
    super.key,
    required this.controller,
    this.existing,
  });

  final AppController controller;
  final FinanceTransaction? existing;

  @override
  State<TransactionEditScreen> createState() => _TransactionEditScreenState();
}

class _TransactionEditScreenState extends State<TransactionEditScreen> {
  final _payee = TextEditingController();
  final _memo = TextEditingController();
  final _amount = TextEditingController();
  String? _accountId;
  String? _categoryId;
  String _status = 'cleared';
  String? _movementClass;
  String? _originalMovementClass;
  DateTime _date = DateTime.now();
  bool _income = false;
  bool _loading = true;
  List<FinanceAccount> _accounts = [];
  List<FinanceCategory> _categories = [];

  @override
  void initState() {
    super.initState();
    final tx = widget.existing;
    if (tx != null) {
      _payee.text = tx.payee;
      _memo.text = tx.memo;
      _amount.text = (tx.amountCents.abs() / 100).toStringAsFixed(2);
      _accountId = tx.accountId;
      _categoryId = tx.categoryId;
      _status = dropdownValueIn(tx.status, kTxStatuses) ?? 'cleared';
      _originalMovementClass = tx.movementClass;
      _movementClass = dropdownValueIn(
        uiMovementClass(tx.movementClass),
        kUiMovementClasses,
      );
      _income = tx.amountCents > 0;
      if (tx.date != null && tx.date!.length >= 10) {
        _date = DateTime.tryParse(tx.date!) ?? _date;
      }
    }
    _loadLookups();
  }

  Future<void> _loadLookups() async {
    try {
      final api = widget.controller.finance!;
      final accounts = await api.listAccounts();
      final cats = await api.listCategories();
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _categories = cats;
        _accountId ??= accounts.isEmpty ? null : accounts.first.id;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showBusyError(context, e);
    }
  }

  @override
  void dispose() {
    _payee.dispose();
    _memo.dispose();
    _amount.dispose();
    super.dispose();
  }

  int _cents() {
    final dollars = double.tryParse(_amount.text.replaceAll(',', '')) ?? 0;
    final cents = (dollars * 100).round();
    return _income ? cents.abs() : -cents.abs();
  }

  Future<void> _save() async {
    if (_accountId == null) {
      await showBusyError(context, 'Create an account first.');
      return;
    }
    final api = widget.controller.finance!;
    final date =
        '${_date.year.toString().padLeft(4, '0')}-${_date.month.toString().padLeft(2, '0')}-${_date.day.toString().padLeft(2, '0')}';
    try {
      if (widget.existing == null) {
        await api.createTransaction({
          'account_id': _accountId,
          'date': date,
          'amount_cents': _cents(),
          'payee': _payee.text.trim(),
          'memo': _memo.text.trim(),
          if (_categoryId != null) 'category_id': _categoryId,
          'status': _status,
          if (_movementClass != null)
            'movement_class': storedMovementClass(
              _movementClass,
              original: _originalMovementClass,
            ),
        });
      } else {
        await api.patchTransaction(widget.existing!.id, {
          'account_id': _accountId,
          'date': date,
          'amount_cents': _cents(),
          'payee': _payee.text.trim(),
          'memo': _memo.text.trim(),
          'category_id': _categoryId,
          'status': _status,
          'movement_class': storedMovementClass(
            _movementClass,
            original: _originalMovementClass,
          ),
        });
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  Future<void> _delete() async {
    final tx = widget.existing;
    if (tx == null) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete transaction?'),
        content: const Text('Manual rows can be deleted. Imported rows may need void instead.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.controller.finance!.deleteTransaction(tx.id);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  List<DropdownMenuItem<T>> _ensureValue<T>(
    List<DropdownMenuItem<T>> items,
    T? value,
    String missingLabel,
  ) {
    if (value != null && !items.any((item) => item.value == value)) {
      return [
        DropdownMenuItem(value: value, child: Text(missingLabel)),
        ...items,
      ];
    }
    return items;
  }

  @override
  Widget build(BuildContext context) {
    final accountItems = _ensureValue(
      _accounts.map((a) => DropdownMenuItem(value: a.id, child: Text(a.name))).toList(),
      _accountId,
      'Unknown account',
    );
    final categoryItems = _ensureValue<String?>(
      [
        const DropdownMenuItem(value: null, child: Text('Uncategorized')),
        ..._categories.map(
          (c) => DropdownMenuItem(value: c.id, child: Text(c.displayName)),
        ),
      ],
      _categoryId,
      'Unknown category',
    );
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.existing == null ? 'Add transaction' : 'Edit transaction'),
        actions: [
          if (widget.existing != null)
            IconButton(onPressed: _delete, icon: const Icon(Icons.delete_outline)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                SwitchListTile(
                  title: const Text('Income'),
                  subtitle: const Text('Off = spend (negative cents)'),
                  value: _income,
                  onChanged: (v) => setState(() => _income = v),
                ),
                TextField(
                  controller: _amount,
                  decoration: const InputDecoration(labelText: 'Amount'),
                  keyboardType: const TextInputType.numberWithOptions(decimal: true),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _payee,
                  decoration: const InputDecoration(labelText: 'Payee'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _memo,
                  decoration: const InputDecoration(labelText: 'Memo'),
                ),
                const SizedBox(height: 12),
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Date'),
                  subtitle: Text(_date.toIso8601String().split('T').first),
                  trailing: const Icon(Icons.event),
                  onTap: () async {
                    final picked = await showDatePicker(
                      context: context,
                      initialDate: _date,
                      firstDate: DateTime(2015),
                      lastDate: DateTime.now().add(const Duration(days: 365)),
                    );
                    if (picked != null) setState(() => _date = picked);
                  },
                ),
                DropdownButtonFormField<String>(
                  value: dropdownValueIn(_accountId, accountItems.map((item) => item.value)),
                  decoration: const InputDecoration(labelText: 'Account'),
                  items: accountItems,
                  onChanged: (v) => setState(() => _accountId = v),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String?>(
                  value: dropdownValueIn(
                    _categoryId,
                    categoryItems.map((item) => item.value),
                  ),
                  decoration: const InputDecoration(labelText: 'Category'),
                  items: categoryItems,
                  onChanged: (v) => setState(() => _categoryId = v),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: dropdownValueIn(_status, kTxStatuses) ?? 'cleared',
                  decoration: const InputDecoration(labelText: 'Status'),
                  items: const [
                    DropdownMenuItem(value: 'cleared', child: Text('Cleared')),
                    DropdownMenuItem(value: 'pending', child: Text('Pending')),
                    DropdownMenuItem(value: 'reconciled', child: Text('Reconciled')),
                    DropdownMenuItem(value: 'void', child: Text('Void')),
                  ],
                  onChanged: (v) => setState(() => _status = v ?? 'cleared'),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String?>(
                  key: const Key('tx-movement-class'),
                  value: dropdownValueIn(_movementClass, kUiMovementClasses),
                  decoration: const InputDecoration(labelText: 'Movement class'),
                  items: const [
                    DropdownMenuItem(value: null, child: Text('—')),
                    DropdownMenuItem(value: 'spend', child: Text('Spend')),
                    DropdownMenuItem(value: 'income', child: Text('Income')),
                    DropdownMenuItem(value: 'transfer', child: Text('Transfer')),
                    DropdownMenuItem(value: 'reimbursement', child: Text('Reimbursement')),
                  ],
                  onChanged: (v) => setState(() => _movementClass = v),
                ),
                const SizedBox(height: 24),
                FilledButton(onPressed: _save, child: const Text('Save')),
              ],
            ),
    );
  }
}

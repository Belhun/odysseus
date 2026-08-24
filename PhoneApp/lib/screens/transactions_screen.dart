import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'transaction_edit_screen.dart';

class TransactionsScreen extends StatefulWidget {
  const TransactionsScreen({
    super.key,
    required this.controller,
    this.initialCategoryId,
    this.initialCategoryName,
    this.initialMonth,
    this.uncategorized = false,
  });

  final AppController controller;
  final String? initialCategoryId;
  final String? initialCategoryName;
  final String? initialMonth;
  final bool uncategorized;

  @override
  State<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends State<TransactionsScreen> {
  static const _uncategorizedValue = '__uncategorized__';

  final _search = TextEditingController();
  bool _loading = true;
  String? _error;
  List<FinanceTransaction> _txs = [];
  List<FinanceAccount> _accounts = [];
  List<FinanceCategory> _categories = [];
  String? _accountId;
  String? _categoryId;
  String? _month;
  bool _uncategorized = false;
  int _total = 0;

  @override
  void initState() {
    super.initState();
    _categoryId = widget.initialCategoryId;
    _month = widget.initialMonth;
    _uncategorized = widget.uncategorized;
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = widget.controller.finance!;
      final accounts = await api.listAccounts();
      final cats = await api.listCategories();
      final page = await api.listTransactions(
        accountId: _accountId,
        categoryId: _uncategorized ? null : _categoryId,
        month: _month,
        search: _search.text.trim(),
        uncategorized: _uncategorized,
        limit: 150,
      );
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _categories = cats;
        _txs = page.transactions;
        _total = page.total;
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

  String _accountName(String id) {
    for (final a in _accounts) {
      if (a.id == id) return a.name;
    }
    return 'Account';
  }

  String? get _categoryLabel {
    if (_uncategorized) {
      return widget.initialCategoryName ?? 'Uncategorized';
    }
    if (_categoryId == null) return widget.initialCategoryName;
    for (final c in _categories) {
      if (c.id == _categoryId) return c.displayName;
    }
    return widget.initialCategoryName;
  }

  String get _title {
    final cat = _categoryLabel;
    if (cat != null && _month != null) return '$cat · $_month ($_total)';
    if (_month != null) return 'Transactions · $_month ($_total)';
    if (cat != null) return '$cat ($_total)';
    return 'Transactions ($_total)';
  }

  String get _emptyMessage {
    final cat = _categoryLabel;
    if (_month != null && cat != null) {
      return 'No transactions in $_month for $cat.';
    }
    if (_month != null) return 'No transactions in $_month.';
    if (cat != null) return 'No transactions for $cat.';
    return 'No transactions.';
  }

  String? get _categoryDropdownValue {
    if (_uncategorized) return _uncategorizedValue;
    return dropdownValueIn(_categoryId, [null, ..._categories.map((c) => c.id)]);
  }

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(
        title: Text(_title, overflow: TextOverflow.ellipsis),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: TextField(
              controller: _search,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Search payee or memo',
              ),
              onSubmitted: (_) => _load(),
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: Row(
              children: [
                DropdownButton<String?>(
                  value: dropdownValueIn(_accountId, [null, ..._accounts.map((a) => a.id)]),
                  hint: const Text('All accounts'),
                  items: [
                    const DropdownMenuItem(value: null, child: Text('All accounts')),
                    ..._accounts.map(
                      (a) => DropdownMenuItem(value: a.id, child: Text(a.name)),
                    ),
                  ],
                  onChanged: (v) {
                    setState(() => _accountId = v);
                    _load();
                  },
                ),
                const SizedBox(width: 12),
                DropdownButton<String?>(
                  value: _categoryDropdownValue,
                  hint: const Text('All categories'),
                  items: [
                    const DropdownMenuItem(value: null, child: Text('All categories')),
                    if (_uncategorized)
                      const DropdownMenuItem(
                        value: _uncategorizedValue,
                        child: Text('Uncategorized'),
                      ),
                    ..._categories.map(
                      (c) => DropdownMenuItem(value: c.id, child: Text(c.displayName)),
                    ),
                  ],
                  onChanged: (v) {
                    setState(() {
                      if (v == _uncategorizedValue) {
                        _uncategorized = true;
                        _categoryId = null;
                      } else {
                        _uncategorized = false;
                        _categoryId = v;
                      }
                    });
                    _load();
                  },
                ),
                if (_month != null) ...[
                  const SizedBox(width: 12),
                  MonthPickerButton(
                    month: _month!,
                    onChanged: (m) {
                      setState(() => _month = m);
                      _load();
                    },
                  ),
                ],
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? ErrorBody(message: _error!, onRetry: _load)
                    : RefreshIndicator(
                        onRefresh: _load,
                        child: ListView.builder(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.fromLTRB(8, 0, 8, 88),
                          itemCount: _txs.isEmpty ? 1 : _txs.length,
                          itemBuilder: (context, i) {
                            if (_txs.isEmpty) {
                              return Padding(
                                padding: const EdgeInsets.fromLTRB(24, 48, 24, 24),
                                child: Text(
                                  _emptyMessage,
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(color: OdyColors.muted),
                                ),
                              );
                            }
                            final tx = _txs[i];
                            final spend = tx.amountCents < 0;
                            return ListTile(
                              title: Text(tx.payee.isEmpty ? '(no payee)' : tx.payee),
                              subtitle: Text(
                                '${tx.date ?? ''} · ${_accountName(tx.accountId)}'
                                '${tx.categoryName != null ? ' · ${tx.categoryName}' : ''}',
                              ),
                              trailing: Text(
                                money(tx.amountCents, privacy: privacy),
                                style: TextStyle(
                                  color: spend ? OdyColors.red : OdyColors.green,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              onTap: () async {
                                await Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) => TransactionEditScreen(
                                      controller: widget.controller,
                                      existing: tx,
                                    ),
                                  ),
                                );
                                _load();
                              },
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}

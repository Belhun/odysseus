import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'transaction_edit_screen.dart';

class TransactionsScreen extends StatefulWidget {
  const TransactionsScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<TransactionsScreen> createState() => _TransactionsScreenState();
}

class _TransactionsScreenState extends State<TransactionsScreen> {
  final _search = TextEditingController();
  bool _loading = true;
  String? _error;
  List<FinanceTransaction> _txs = [];
  List<FinanceAccount> _accounts = [];
  List<FinanceCategory> _categories = [];
  String? _accountId;
  String? _categoryId;
  int _total = 0;

  @override
  void initState() {
    super.initState();
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
        categoryId: _categoryId,
        search: _search.text.trim(),
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

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(title: Text('Transactions ($_total)')),
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
                  value: _accountId,
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
                  value: _categoryId,
                  hint: const Text('All categories'),
                  items: [
                    const DropdownMenuItem(value: null, child: Text('All categories')),
                    ..._categories.map(
                      (c) => DropdownMenuItem(value: c.id, child: Text(c.displayName)),
                    ),
                  ],
                  onChanged: (v) {
                    setState(() => _categoryId = v);
                    _load();
                  },
                ),
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
                          padding: const EdgeInsets.fromLTRB(8, 0, 8, 88),
                          itemCount: _txs.length,
                          itemBuilder: (context, i) {
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

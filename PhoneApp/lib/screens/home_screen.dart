import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'accounts_screen.dart';
import 'transactions_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.controller, required this.onOpenTab});

  final AppController controller;
  final void Function(String tab) onOpenTab;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _loading = true;
  String? _error;
  List<FinanceAccount> _accounts = [];
  BudgetSnapshot? _budget;
  NetWorth? _net;
  List<RecurringSeries> _upcoming = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final cached = widget.controller.homePrefetched;
    if (cached) {
      setState(() {
        _accounts = widget.controller.cachedAccounts;
        _budget = widget.controller.cachedBudget;
        _net = widget.controller.cachedNetWorth;
        _upcoming = widget.controller.cachedRecurring
            .where((s) => s.status == 'active')
            .take(5)
            .toList();
        _loading = false;
        _error = null;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final api = widget.controller.finance!;
      final month = currentMonthKey();
      final accounts = await api.listAccounts();
      final budget = await api.budgets(month: month);
      NetWorth? net;
      try {
        net = await api.netWorth();
      } catch (_) {}
      var recurring = <RecurringSeries>[];
      try {
        recurring = await api.recurring();
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _budget = budget;
        _net = net;
        _upcoming = recurring
            .where((s) => s.status == 'active')
            .take(5)
            .toList();
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

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Home'),
        actions: [
          IconButton(
            tooltip: privacy ? 'Show balances' : 'Hide balances',
            onPressed: () => widget.controller.setPrivacy(!privacy),
            icon: Icon(privacy ? Icons.visibility_off : Icons.visibility),
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
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 88),
                    children: [
                      if (_net != null)
                        OdyCard(
                          onTap: () => widget.onOpenTab('reports'),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Net worth', style: TextStyle(color: OdyColors.subheader)),
                              const SizedBox(height: 6),
                              Text(
                                money(_net!.netWorthCents, privacy: privacy),
                                style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                'Assets ${money(_net!.assetsCents, privacy: privacy)} · Liabilities ${money(_net!.liabilitiesCents, privacy: privacy)}',
                                style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 10),
                      if (_budget != null)
                        OdyCard(
                          onTap: () => widget.onOpenTab('budget'),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Spend · ${_budget!.month}',
                                  style: const TextStyle(color: OdyColors.subheader)),
                              const SizedBox(height: 6),
                              Text(
                                money(_budget!.netSpendCents, privacy: privacy),
                                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                'Income ${money(_budget!.incomeCents, privacy: privacy)}'
                                '${_budget!.unclassifiedCount > 0 ? ' · ${_budget!.unclassifiedCount} unclassified' : ''}',
                                style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                      const SizedBox(height: 10),
                      OdyCard(
                        onTap: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => AccountsScreen(controller: widget.controller),
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Accounts', style: TextStyle(color: OdyColors.subheader)),
                            const SizedBox(height: 8),
                            if (_accounts.isEmpty)
                              const Text('No accounts yet. Tap to add one.')
                            else
                              ..._accounts.take(6).map(
                                    (a) => Padding(
                                      padding: const EdgeInsets.symmetric(vertical: 4),
                                      child: Row(
                                        children: [
                                          Expanded(child: Text(a.name)),
                                          Text(money(a.balanceCents, privacy: privacy)),
                                        ],
                                      ),
                                    ),
                                  ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 10),
                      OdyCard(
                        onTap: () => widget.onOpenTab('recurring'),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Upcoming / subscriptions',
                                style: TextStyle(color: OdyColors.subheader)),
                            const SizedBox(height: 8),
                            if (_upcoming.isEmpty)
                              const Text('No recurring series yet. Import history and Odysseus will detect them.')
                            else
                              ..._upcoming.map(
                                (s) => Padding(
                                  padding: const EdgeInsets.symmetric(vertical: 4),
                                  child: Row(
                                    children: [
                                      Expanded(child: Text(s.displayPayee)),
                                      Text(s.nextDueDate ?? s.cadence),
                                    ],
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                      if (_budget != null && _budget!.categories.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        OdyCard(
                          onTap: () => widget.onOpenTab('budget'),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Budget snapshot',
                                  style: TextStyle(color: OdyColors.subheader)),
                              const SizedBox(height: 8),
                              ..._budget!.categories.take(5).map((row) {
                                final limit = row.limitCents;
                                final frac = limit == null || limit == 0
                                    ? 0.0
                                    : (row.spentCents / limit).clamp(0.0, 1.0);
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 8),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Expanded(child: Text(row.categoryName)),
                                          Text(money(row.spentCents, privacy: privacy)),
                                        ],
                                      ),
                                      if (limit != null)
                                        LinearProgressIndicator(
                                          value: frac.toDouble(),
                                          color: frac >= 1 ? OdyColors.red : OdyColors.accent,
                                          backgroundColor: OdyColors.border,
                                        ),
                                    ],
                                  ),
                                );
                              }),
                            ],
                          ),
                        ),
                      ],
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: () => Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => TransactionsScreen(controller: widget.controller),
                          ),
                        ),
                        child: const Text('View all transactions'),
                      ),
                    ],
                  ),
                ),
    );
  }
}

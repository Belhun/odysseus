import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> {
  String _month = currentMonthKey();
  bool _loading = true;
  String? _error;
  BudgetSnapshot? _spend;
  List<TrendPoint> _trends = [];
  Map<String, dynamic> _cashflow = {};
  List<Map<String, dynamic>> _byAccount = [];
  NetWorth? _net;

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
      final api = widget.controller.finance!;
      final spend = await api.reportSpending(month: _month);
      final trends = await api.reportTrends();
      final cash = await api.reportCashflow(month: _month);
      final byAcct = await api.spendByAccount(month: _month);
      final net = await api.netWorth();
      if (!mounted) return;
      setState(() {
        _spend = spend;
        _trends = trends;
        _cashflow = cash;
        _byAccount = byAcct;
        _net = net;
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
      appBar: AppBar(title: const Text('Reports')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
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
                      if (_net != null)
                        OdyCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Net worth', style: TextStyle(color: OdyColors.subheader)),
                              Text(money(_net!.netWorthCents, privacy: privacy),
                                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                            ],
                          ),
                        ),
                      const SizedBox(height: 10),
                      OdyCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Cashflow', style: TextStyle(color: OdyColors.subheader)),
                            Text(
                              'Income ${money(asInt(_cashflow['income_cents']), privacy: privacy)}',
                            ),
                            Text(
                              'Net spend ${money(asInt(_cashflow['net_spend_cents'] ?? _cashflow['spending_cents']), privacy: privacy)}',
                            ),
                            Text(
                              'Personal ${money(asInt(_cashflow['personal_spend_cents']), privacy: privacy)}',
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 10),
                      OdyCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Trends', style: TextStyle(color: OdyColors.subheader)),
                            if (_trends.isEmpty)
                              const Text('Not enough months yet.')
                            else
                              ..._trends.map(
                                (t) => Padding(
                                  padding: const EdgeInsets.symmetric(vertical: 3),
                                  child: Row(
                                    children: [
                                      SizedBox(width: 72, child: Text(t.month)),
                                      Expanded(
                                        child: LinearProgressIndicator(
                                          value: _bar(t.spendCents),
                                          color: OdyColors.red,
                                          backgroundColor: OdyColors.border,
                                        ),
                                      ),
                                      const SizedBox(width: 8),
                                      Text(money(t.spendCents, privacy: privacy)),
                                    ],
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 10),
                      OdyCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Spend by category',
                                style: TextStyle(color: OdyColors.subheader)),
                            ...(_spend?.categories ?? []).take(12).map(
                                  (row) => Padding(
                                    padding: const EdgeInsets.symmetric(vertical: 3),
                                    child: Row(
                                      children: [
                                        Expanded(child: Text(row.categoryName)),
                                        Text(money(row.spentCents, privacy: privacy)),
                                      ],
                                    ),
                                  ),
                                ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 10),
                      OdyCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Spend by account',
                                style: TextStyle(color: OdyColors.subheader)),
                            ..._byAccount.map(
                              (row) => Padding(
                                padding: const EdgeInsets.symmetric(vertical: 3),
                                child: Row(
                                  children: [
                                    Expanded(child: Text('${row['name'] ?? row['account_name'] ?? 'Account'}')),
                                    Text(
                                      money(
                                        asInt(row['personal_spend_cents'] ?? row['spent_cents'] ?? row['net_spend_cents'] ?? row['amount_cents']),
                                        privacy: privacy,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }

  double _bar(int spend) {
    var max = 1;
    for (final t in _trends) {
      if (t.spendCents > max) max = t.spendCents;
    }
    return (spend / max).clamp(0.0, 1.0);
  }
}

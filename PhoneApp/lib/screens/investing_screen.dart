import 'package:flutter/material.dart';

import '../api/investing_client.dart';
import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

const _kinds = [
  ('stock', 'Stock'),
  ('etf', 'ETF'),
  ('fund', 'Fund'),
  ('crypto', 'Crypto'),
  ('cash', 'Cash'),
  ('other', 'Other'),
];

String _kindLabel(String kind) {
  for (final row in _kinds) {
    if (row.$1 == kind) return row.$2;
  }
  return kind;
}

class InvestingScreen extends StatefulWidget {
  const InvestingScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<InvestingScreen> createState() => _InvestingScreenState();
}

class _InvestingScreenState extends State<InvestingScreen> {
  bool _loading = true;
  String? _error;
  InvestSummary? _summary;
  List<InvestAsset> _assets = [];
  List<FinanceAccount> _accounts = [];

  InvestingClient? get _client {
    final finance = widget.controller.finance;
    if (finance == null) return null;
    return InvestingClient(finance.httpClient);
  }

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
    final api = _client;
    if (api == null) {
      setState(() {
        _error = 'Not connected';
        _loading = false;
      });
      return;
    }
    try {
      final summary = await api.summary();
      final assets = await api.listAssets();
      var accounts = <FinanceAccount>[];
      try {
        accounts = await widget.controller.finance!.listAccounts();
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _summary = summary;
        _assets = assets;
        _accounts = accounts;
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

  Future<void> _edit({InvestAsset? existing}) async {
    final api = _client;
    if (api == null) return;
    final name = TextEditingController(text: existing?.name ?? '');
    final symbol = TextEditingController(text: existing?.symbol ?? '');
    final shares = TextEditingController(text: existing?.shares ?? '');
    final cost = TextEditingController(
      text: existing == null ? '' : (existing.costBasisCents / 100).toStringAsFixed(2),
    );
    final value = TextEditingController(
      text: existing == null ? '' : (existing.currentValueCents / 100).toStringAsFixed(2),
    );
    final notes = TextEditingController(text: existing?.notes ?? '');
    var kind = existing?.assetKind ?? 'other';
    String? accountId = existing?.accountId;
    if (accountId != null && !_accounts.any((a) => a.id == accountId)) {
      accountId = null;
    }
    final saved = await showDialog<String>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          title: Text(existing == null ? 'Add holding' : 'Edit holding'),
          content: SizedBox(
            width: 360,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text(
                    'Type the value from your broker. Odysseus does not fetch quotes.',
                    style: TextStyle(color: OdyColors.muted, fontSize: 12),
                  ),
                  TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
                  TextField(controller: symbol, decoration: const InputDecoration(labelText: 'Symbol')),
                  DropdownButtonFormField<String>(
                    value: kind,
                    decoration: const InputDecoration(labelText: 'Kind'),
                    items: [
                      for (final row in _kinds)
                        DropdownMenuItem(value: row.$1, child: Text(row.$2)),
                    ],
                    onChanged: (v) => setLocal(() => kind = v ?? 'other'),
                  ),
                  DropdownButtonFormField<String?>(
                    value: accountId,
                    decoration: const InputDecoration(labelText: 'Account (label only)'),
                    items: [
                      const DropdownMenuItem<String?>(value: null, child: Text('(none)')),
                      for (final a in _accounts)
                        DropdownMenuItem<String?>(value: a.id, child: Text(a.name)),
                    ],
                    onChanged: (v) => setLocal(() => accountId = v),
                  ),
                  TextField(
                    controller: shares,
                    decoration: const InputDecoration(labelText: 'Shares'),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  ),
                  TextField(
                    controller: cost,
                    decoration: const InputDecoration(labelText: 'Cost basis'),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  ),
                  TextField(
                    controller: value,
                    decoration: const InputDecoration(labelText: 'Current value'),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                  ),
                  TextField(controller: notes, decoration: const InputDecoration(labelText: 'Notes')),
                ],
              ),
            ),
          ),
          actions: [
            if (existing != null)
              TextButton(
                onPressed: () => Navigator.pop(ctx, 'archive'),
                child: const Text('Archive'),
              ),
            TextButton(onPressed: () => Navigator.pop(ctx, 'cancel'), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(ctx, 'save'), child: const Text('Save')),
          ],
        ),
      ),
    );
    if (saved == 'archive' && existing != null) {
      try {
        await api.patchAsset(existing.id, {'archived': true});
        await _load();
      } catch (e) {
        if (mounted) showBusyError(context, e);
      }
      return;
    }
    if (saved != 'save') return;
    final costCents = dollarsToCents(cost.text);
    final valueCents = dollarsToCents(value.text);
    if (costCents == null || valueCents == null) {
      if (mounted) showBusyError(context, 'Amounts must be 0 or more');
      return;
    }
    final body = {
      'name': name.text.trim(),
      'symbol': symbol.text.trim(),
      'asset_kind': kind,
      'account_id': accountId,
      'shares': shares.text.trim().isEmpty ? '0' : shares.text.trim(),
      'cost_basis_cents': costCents,
      'current_value_cents': valueCents,
      'notes': notes.text.trim(),
    };
    try {
      if (existing == null) {
        await api.createAsset(body);
      } else {
        await api.patchAsset(existing.id, body);
      }
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  Future<void> _updateValue(InvestAsset asset) async {
    final api = _client;
    if (api == null) return;
    final value = TextEditingController(
      text: (asset.currentValueCents / 100).toStringAsFixed(2),
    );
    final asOf = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Update value · ${asset.name}'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Type the value from your broker. Odysseus does not fetch quotes.',
              style: TextStyle(color: OdyColors.muted, fontSize: 12),
            ),
            TextField(
              controller: value,
              decoration: const InputDecoration(labelText: 'Current value'),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
            ),
            TextField(
              controller: asOf,
              decoration: const InputDecoration(labelText: 'As of (YYYY-MM-DD)'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok != true) return;
    final cents = dollarsToCents(value.text);
    if (cents == null) {
      if (mounted) showBusyError(context, 'Current value must be 0 or more');
      return;
    }
    try {
      await api.updateValue(asset.id, currentValueCents: cents, asOf: asOf.text.trim());
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(title: const Text('Investing')),
      floatingActionButton: FloatingActionButton(
        onPressed: _edit,
        child: const Icon(Icons.add),
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
                      if (_summary != null) ...[
                        OdyCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Current value',
                                  style: TextStyle(color: OdyColors.subheader)),
                              Text(
                                money(_summary!.totalCurrentValueCents, privacy: privacy),
                                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                              ),
                              Text(
                                'Cost ${money(_summary!.totalCostBasisCents, privacy: privacy)}',
                                style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 10),
                        OdyCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Unrealized gain',
                                  style: TextStyle(color: OdyColors.subheader)),
                              Text(
                                money(_summary!.unrealizedGainCents, privacy: privacy),
                                style: TextStyle(
                                  fontSize: 20,
                                  fontWeight: FontWeight.w700,
                                  color: _summary!.unrealizedGainCents > 0
                                      ? OdyColors.green
                                      : _summary!.unrealizedGainCents < 0
                                          ? OdyColors.red
                                          : null,
                                ),
                              ),
                              if (_summary!.unrealizedGainPct != null)
                                Text(
                                  '${_summary!.unrealizedGainPct}%',
                                  style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                                ),
                            ],
                          ),
                        ),
                        if (_summary!.allocation.isNotEmpty) ...[
                          const SizedBox(height: 10),
                          Wrap(
                            spacing: 8,
                            runSpacing: 4,
                            children: [
                              for (final row in _summary!.allocation)
                                Chip(
                                  label: Text(
                                    '${_kindLabel(row.assetKind)} ${row.pct.toStringAsFixed(0)}%',
                                  ),
                                ),
                            ],
                          ),
                        ],
                        const SizedBox(height: 12),
                      ],
                      if (_assets.isEmpty)
                        const Padding(
                          padding: EdgeInsets.only(top: 12),
                          child: Text(
                            'No holdings yet. Add an asset and type its current value. Odysseus does not fetch quotes.',
                          ),
                        )
                      else
                        ..._assets.map(
                          (asset) => Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: OdyCard(
                              onTap: () => _edit(existing: asset),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          asset.symbol.isEmpty
                                              ? asset.name
                                              : '${asset.name} (${asset.symbol})',
                                          style: const TextStyle(fontWeight: FontWeight.w600),
                                        ),
                                        Text(
                                          '${_kindLabel(asset.assetKind)} · ${asset.shares} sh',
                                          style: const TextStyle(
                                              color: OdyColors.muted, fontSize: 12),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Column(
                                    crossAxisAlignment: CrossAxisAlignment.end,
                                    children: [
                                      Text(money(asset.currentValueCents, privacy: privacy)),
                                      Text(
                                        money(asset.unrealizedGainCents, privacy: privacy),
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: asset.unrealizedGainCents >= 0
                                              ? OdyColors.green
                                              : OdyColors.red,
                                        ),
                                      ),
                                    ],
                                  ),
                                  IconButton(
                                    tooltip: 'Update value',
                                    onPressed: () => _updateValue(asset),
                                    icon: const Icon(Icons.edit_note),
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

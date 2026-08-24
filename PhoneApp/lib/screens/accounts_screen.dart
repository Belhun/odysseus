import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class AccountsScreen extends StatefulWidget {
  const AccountsScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<AccountsScreen> createState() => _AccountsScreenState();
}

class _AccountsScreenState extends State<AccountsScreen> {
  bool _loading = true;
  String? _error;
  List<FinanceAccount> _accounts = [];

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
      final accounts = await widget.controller.finance!.listAccounts(includeClosed: true);
      if (!mounted) return;
      setState(() {
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

  Future<void> _edit({FinanceAccount? existing}) async {
    final name = TextEditingController(text: existing?.name ?? '');
    final institution = TextEditingController(text: existing?.institution ?? '');
    var type = existing?.accountType ?? 'checking';
    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(existing == null ? 'Add account' : 'Edit account'),
        content: SizedBox(
          width: 360,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
              TextField(
                controller: institution,
                decoration: const InputDecoration(labelText: 'Institution'),
              ),
              DropdownButtonFormField<String>(
                value: type,
                decoration: const InputDecoration(labelText: 'Type'),
                items: const [
                  DropdownMenuItem(value: 'checking', child: Text('Checking')),
                  DropdownMenuItem(value: 'savings', child: Text('Savings')),
                  DropdownMenuItem(value: 'credit_card', child: Text('Credit card')),
                  DropdownMenuItem(value: 'loan', child: Text('Loan')),
                  DropdownMenuItem(value: 'cash', child: Text('Cash')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (v) => type = v ?? 'checking',
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (saved != true) return;
    try {
      final api = widget.controller.finance!;
      if (existing == null) {
        await api.createAccount({
          'name': name.text.trim(),
          'institution': institution.text.trim(),
          'account_type': type,
        });
      } else {
        await api.patchAccount(existing.id, {
          'name': name.text.trim(),
          'institution': institution.text.trim(),
          'account_type': type,
        });
      }
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final privacy = widget.controller.privacyMode;
    return Scaffold(
      appBar: AppBar(title: const Text('Accounts')),
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
                  child: ListView.builder(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 88),
                    itemCount: _accounts.length,
                    itemBuilder: (context, i) {
                      final a = _accounts[i];
                      return OdyCard(
                        onTap: () => _edit(existing: a),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(a.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                                  Text(
                                    '${a.institution.isEmpty ? a.accountType : a.institution} · ${a.accountType}'
                                    '${a.isClosed ? ' · closed' : ''}',
                                    style: const TextStyle(color: OdyColors.muted, fontSize: 12),
                                  ),
                                ],
                              ),
                            ),
                            Text(money(a.balanceCents, privacy: privacy)),
                          ],
                        ),
                      );
                    },
                  ),
                ),
    );
  }
}

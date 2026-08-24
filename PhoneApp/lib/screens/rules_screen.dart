import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../widgets/common.dart';

class RulesScreen extends StatefulWidget {
  const RulesScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<RulesScreen> createState() => _RulesScreenState();
}

class _RulesScreenState extends State<RulesScreen> {
  List<CategorizationRule> _rules = [];
  List<FinanceCategory> _cats = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = widget.controller.finance!;
      final rules = await api.rules();
      final cats = await api.listCategories();
      if (!mounted) return;
      setState(() {
        _rules = rules;
        _cats = cats;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showBusyError(context, e);
    }
  }

  String _catName(String? id) {
    for (final c in _cats) {
      if (c.id == id) return c.displayName;
    }
    return '—';
  }

  Future<void> _add() async {
    final pattern = TextEditingController();
    String? categoryId = _cats.isEmpty ? null : _cats.first.id;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Payee rule'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: pattern,
              decoration: const InputDecoration(
                labelText: 'Pattern',
                helperText: 'Substring match. Closest thing to Cashew associated titles.',
              ),
            ),
            DropdownButtonFormField<String?>(
              value: categoryId,
              items: [
                const DropdownMenuItem(value: null, child: Text('No category')),
                ..._cats.map((c) => DropdownMenuItem(value: c.id, child: Text(c.displayName))),
              ],
              onChanged: (v) => categoryId = v,
              decoration: const InputDecoration(labelText: 'Category'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok != true || pattern.text.trim().isEmpty) return;
    try {
      await widget.controller.finance!.createRule(
        pattern: pattern.text.trim(),
        categoryId: categoryId,
      );
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Rules')),
      floatingActionButton: FloatingActionButton(
        onPressed: _add,
        child: const Icon(Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                padding: const EdgeInsets.fromLTRB(8, 8, 8, 88),
                itemCount: _rules.length,
                itemBuilder: (context, i) {
                  final r = _rules[i];
                  return ListTile(
                    title: Text(r.pattern),
                    subtitle: Text('${_catName(r.categoryId)} · ${r.movementClass ?? 'any'}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: () async {
                        try {
                          await widget.controller.finance!.deleteRule(r.id);
                          await _load();
                        } catch (e) {
                          if (!context.mounted) return;
                          showBusyError(context, e);
                        }
                      },
                    ),
                  );
                },
              ),
            ),
    );
  }
}

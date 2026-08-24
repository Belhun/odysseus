import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class ImportScreen extends StatefulWidget {
  const ImportScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<ImportScreen> createState() => _ImportScreenState();
}

class _ImportScreenState extends State<ImportScreen> {
  List<FinanceAccount> _accounts = [];
  List<ImportBatch> _batches = [];
  String? _accountId;
  ImportPreview? _preview;
  String? _status;
  bool _loading = true;
  final _paste = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _paste.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final api = widget.controller.finance!;
      final accounts = await api.listAccounts();
      final batches = await api.importBatches();
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _batches = batches;
        _accountId ??= accounts.isEmpty ? null : accounts.first.id;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
      showBusyError(context, e);
    }
  }

  Future<void> _previewBytes(String filename, List<int> bytes) async {
    if (_accountId == null) {
      await showBusyError(context, 'Create an account first.');
      return;
    }
    setState(() => _status = 'Building preview…');
    try {
      final preview = await widget.controller.finance!.importPreview(
        accountId: _accountId!,
        filename: filename,
        bytes: bytes,
      );
      if (!mounted) return;
      setState(() {
        _preview = preview;
        _status = null;
      });
    } catch (e) {
      if (mounted) {
        setState(() => _status = null);
        showBusyError(context, e);
      }
    }
  }

  Future<void> _pickFile() async {
    final result = await FilePicker.platform.pickFiles(
      withData: true,
      type: FileType.custom,
      allowedExtensions: const ['csv', 'ofx', 'qfx', 'txt'],
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    final bytes = file.bytes;
    if (bytes == null) {
      if (!mounted) return;
      await showBusyError(
        // File picker already returned; this State is still mounted.
        // ignore: use_build_context_synchronously
        context,
        'Could not read the file. Paste CSV below on web.',
      );
      return;
    }
    await _previewBytes(file.name, bytes);
  }

  Future<void> _previewPaste() async {
    final text = _paste.text;
    if (text.trim().isEmpty) return;
    await _previewBytes('pasted.csv', utf8.encode(text));
  }

  Future<void> _commit() async {
    final preview = _preview;
    if (preview == null) return;
    try {
      final result = await widget.controller.finance!.importCommit(preview.previewId);
      if (!mounted) return;
      setState(() {
        _preview = null;
        _status = 'Imported ${result['imported_count'] ?? 0} rows.';
      });
      await _load();
    } catch (e) {
      if (mounted) showBusyError(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Import')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                const Text(
                  'CSV / OFX import talks to /api/finance/import/preview then commit. Same ledger as the web UI.',
                  style: TextStyle(color: OdyColors.subheader),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: _accountId,
                  decoration: const InputDecoration(labelText: 'Account'),
                  items: _accounts
                      .map((a) => DropdownMenuItem(value: a.id, child: Text(a.name)))
                      .toList(),
                  onChanged: (v) => setState(() => _accountId = v),
                ),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _pickFile,
                  icon: const Icon(Icons.upload_file),
                  label: const Text('Choose file'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _paste,
                  minLines: 4,
                  maxLines: 8,
                  decoration: const InputDecoration(
                    labelText: 'Or paste CSV',
                    alignLabelWithHint: true,
                  ),
                ),
                const SizedBox(height: 8),
                OutlinedButton(onPressed: _previewPaste, child: const Text('Preview pasted CSV')),
                if (_status != null) ...[
                  const SizedBox(height: 12),
                  Text(_status!),
                ],
                if (_preview != null) ...[
                  const SizedBox(height: 16),
                  OdyCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Preview ${_preview!.format ?? ''}',
                            style: const TextStyle(fontWeight: FontWeight.w600)),
                        Text(
                          '${_preview!.newCount} new · ${_preview!.duplicateCount} duplicates · ${_preview!.errorCount} errors',
                        ),
                        if (_preview!.warning != null) Text(_preview!.warning!),
                        if (_preview!.errors.isNotEmpty)
                          Text(_preview!.errors.take(5).join('\n'),
                              style: const TextStyle(color: OdyColors.red, fontSize: 12)),
                        const SizedBox(height: 8),
                        FilledButton(onPressed: _commit, child: const Text('Commit import')),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                const Text('Recent batches', style: TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                ..._batches.map(
                  (b) => ListTile(
                    title: Text(b.filename),
                    subtitle: Text('${b.importedCount} imported · ${b.createdAt ?? ''}'),
                    trailing: IconButton(
                      icon: const Icon(Icons.undo),
                      tooltip: 'Rollback',
                      onPressed: () async {
                        try {
                          await widget.controller.finance!.rollbackBatch(b.id);
                          await _load();
                        } catch (e) {
                          if (!context.mounted) return;
                          showBusyError(context, e);
                        }
                      },
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

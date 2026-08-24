import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api/email_client.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'email_compose_screen.dart';
import 'email_read_screen.dart';

class EmailListScreen extends StatefulWidget {
  const EmailListScreen({super.key, required this.controller, this.client});

  final AppController controller;
  final EmailClient? client;

  @override
  State<EmailListScreen> createState() => _EmailListScreenState();
}

class _EmailListScreenState extends State<EmailListScreen> {
  final _search = TextEditingController();
  bool _loading = true;
  String? _error;
  List<EmailAccount> _accounts = [];
  List<String> _folders = const ['INBOX'];
  List<EmailHeader> _emails = [];
  String? _accountId;
  String _folder = 'INBOX';
  String _filter = 'all';

  EmailClient get _api =>
      widget.client ?? EmailClient(widget.controller.odyHttp);

  @override
  void initState() {
    super.initState();
    _load(bustCache: false);
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load({bool bustCache = true}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final accounts = await _api.listAccounts();
      String? accountId = _accountId;
      if (accountId == null || !accounts.any((a) => a.id == accountId)) {
        accountId = accounts.where((a) => a.isDefault).map((a) => a.id).cast<String?>().firstWhere(
              (id) => id != null,
              orElse: () => accounts.isEmpty ? null : accounts.first.id,
            );
      }
      var folders = <String>['INBOX'];
      if (accounts.isNotEmpty) {
        try {
          final listed = await _api.listFolders(accountId: accountId);
          if (listed.isNotEmpty) folders = listed;
        } catch (_) {}
        if (!folders.contains(_folder)) {
          _folder = folders.contains('INBOX') ? 'INBOX' : folders.first;
        }
      }
      final q = _search.text.trim();
      List<EmailHeader> emails = [];
      if (accounts.isNotEmpty) {
        if (q.length >= 2) {
          emails = await _api.search(query: q, folder: _folder, accountId: accountId);
          if (_filter == 'unread') {
            emails = emails.where((e) => e.unread).toList();
          }
        } else {
          emails = await _api.listMessages(
            folder: _folder,
            accountId: accountId,
            filter: _filter,
            bustCache: bustCache,
          );
        }
      }
      if (!mounted) return;
      setState(() {
        _accounts = accounts;
        _accountId = accountId;
        _folders = folders;
        _emails = emails;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = emailErrorMessage(e);
        _loading = false;
      });
    }
  }

  String _formatDate(EmailHeader m) {
    DateTime? dt;
    if (m.dateEpoch > 0) {
      dt = DateTime.fromMillisecondsSinceEpoch((m.dateEpoch * 1000).round(), isUtc: true)
          .toLocal();
    } else {
      dt = DateTime.tryParse(m.date)?.toLocal();
    }
    if (dt == null) return m.date;
    final now = DateTime.now();
    if (dt.year == now.year && dt.month == now.month && dt.day == now.day) {
      return DateFormat.jm().format(dt);
    }
    if (dt.year == now.year) return DateFormat.MMMd().format(dt);
    return DateFormat.yMMMd().format(dt);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Email')),
      floatingActionButton: _accounts.isEmpty
          ? null
          : FloatingActionButton(
              tooltip: 'Compose',
              onPressed: () async {
                await Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => EmailComposeScreen(
                      controller: widget.controller,
                      client: widget.client,
                      accountId: _accountId,
                    ),
                  ),
                );
                await _load();
              },
              child: const Icon(Icons.edit),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: () { _load(); })
              : RefreshIndicator(
                  onRefresh: () => _load(),
                  child: _accounts.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: const [
                            SizedBox(height: 48),
                            Padding(
                              padding: EdgeInsets.all(24),
                              child: Text(
                                'No email accounts on this Odysseus user.\n\n'
                                'Add IMAP or Google under Settings → Email on the web. '
                                'Google OAuth is browser-only; it is not in this app.',
                                textAlign: TextAlign.center,
                              ),
                            ),
                          ],
                        )
                      : ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.fromLTRB(0, 0, 0, 88),
                          children: [
                            Padding(
                              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                              child: Wrap(
                                spacing: 12,
                                runSpacing: 8,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                children: [
                                  DropdownButton<String>(
                                    value: _accountId,
                                    hint: const Text('Account'),
                                    items: _accounts
                                        .map(
                                          (a) => DropdownMenuItem(
                                            value: a.id,
                                            child: Text(a.label, overflow: TextOverflow.ellipsis),
                                          ),
                                        )
                                        .toList(),
                                    onChanged: (id) {
                                      if (id == null) return;
                                      _accountId = id;
                                      _folder = 'INBOX';
                                      _load();
                                    },
                                  ),
                                  DropdownButton<String>(
                                    value: _folders.contains(_folder) ? _folder : _folders.first,
                                    items: _folders
                                        .map(
                                          (f) => DropdownMenuItem(value: f, child: Text(f)),
                                        )
                                        .toList(),
                                    onChanged: (f) {
                                      if (f == null) return;
                                      _folder = f;
                                      _load();
                                    },
                                  ),
                                  FilterChip(
                                    label: const Text('All'),
                                    selected: _filter == 'all',
                                    onSelected: (_) {
                                      _filter = 'all';
                                      _load();
                                    },
                                  ),
                                  FilterChip(
                                    label: const Text('Unread'),
                                    selected: _filter == 'unread',
                                    onSelected: (_) {
                                      _filter = 'unread';
                                      _load();
                                    },
                                  ),
                                ],
                              ),
                            ),
                            Padding(
                              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
                              child: TextField(
                                controller: _search,
                                decoration: const InputDecoration(
                                  hintText: 'Search this folder',
                                  prefixIcon: Icon(Icons.search),
                                  isDense: true,
                                ),
                                textInputAction: TextInputAction.search,
                                onSubmitted: (_) => _load(),
                              ),
                            ),
                            if (_emails.isEmpty)
                              const Padding(
                                padding: EdgeInsets.all(32),
                                child: Center(
                                  child: Text(
                                    'No messages',
                                    style: TextStyle(color: OdyColors.muted),
                                  ),
                                ),
                              )
                            else
                              ..._emails.map(
                                (m) => ListTile(
                                  leading: Icon(
                                    m.unread ? Icons.markunread : Icons.drafts_outlined,
                                    color: m.unread ? OdyColors.accent : OdyColors.muted,
                                  ),
                                  title: Text(
                                    m.subject,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontWeight: m.unread ? FontWeight.w700 : FontWeight.w400,
                                    ),
                                  ),
                                  subtitle: Text(
                                    '${m.fromLabel} · ${_formatDate(m)}',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                  trailing: m.hasAttachments
                                      ? const Icon(Icons.attach_file, size: 18)
                                      : null,
                                  onTap: () async {
                                    await Navigator.of(context).push(
                                      MaterialPageRoute(
                                        builder: (_) => EmailReadScreen(
                                          controller: widget.controller,
                                          client: widget.client,
                                          uid: m.uid,
                                          accountId: _accountId,
                                          folder: m.folder.isNotEmpty ? m.folder : _folder,
                                        ),
                                      ),
                                    );
                                    await _load();
                                  },
                                ),
                              ),
                          ],
                        ),
                ),
    );
  }
}

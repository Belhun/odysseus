import 'package:flutter/material.dart';

import '../api/email_client.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'email_compose_screen.dart';

class EmailReadScreen extends StatefulWidget {
  const EmailReadScreen({
    super.key,
    required this.controller,
    required this.uid,
    this.client,
    this.accountId,
    this.folder = 'INBOX',
  });

  final AppController controller;
  final EmailClient? client;
  final String uid;
  final String? accountId;
  final String folder;

  @override
  State<EmailReadScreen> createState() => _EmailReadScreenState();
}

class _EmailReadScreenState extends State<EmailReadScreen> {
  bool _loading = true;
  String? _error;
  EmailMessage? _mail;

  EmailClient get _api =>
      widget.client ?? EmailClient(widget.controller.odyHttp);

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
      final mail = await _api.read(
        widget.uid,
        accountId: widget.accountId,
        folder: widget.folder,
        markSeen: true,
      );
      if (!mounted) return;
      setState(() {
        _mail = mail;
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

  String _quote(EmailMessage mail) {
    final quoted = mail.plainBody
        .split('\n')
        .map((line) => line.isEmpty ? '>' : '> $line')
        .join('\n');
    return '\n\nOn ${mail.date}, ${mail.fromLabel} wrote:\n$quoted';
  }

  String _replySubject(String subject) {
    final t = subject.trim();
    if (t.toLowerCase().startsWith('re:')) return t;
    return 'Re: $t';
  }

  String _replyReferences(EmailMessage mail) {
    final bits = <String>[];
    if (mail.references.trim().isNotEmpty) bits.add(mail.references.trim());
    if (mail.messageId.trim().isNotEmpty) bits.add(mail.messageId.trim());
    return bits.join(' ');
  }

  Future<void> _markUnread() async {
    try {
      await _api.markUnread(
        widget.uid,
        accountId: widget.accountId,
        folder: widget.folder,
      );
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) await showBusyError(context, emailErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final mail = _mail;
    return Scaffold(
      appBar: AppBar(
        title: Text(mail == null || mail.subject.isEmpty ? 'Message' : mail.subject),
        actions: [
          if (mail != null)
            IconButton(
              tooltip: 'Mark unread',
              onPressed: _markUnread,
              icon: const Icon(Icons.mark_email_unread_outlined),
            ),
          if (mail != null)
            IconButton(
              tooltip: 'Reply',
              icon: const Icon(Icons.reply),
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => EmailComposeScreen(
                      controller: widget.controller,
                      client: widget.client,
                      accountId: widget.accountId,
                      to: mail.fromAddress,
                      subject: _replySubject(mail.subject),
                      inReplyTo: mail.messageId,
                      references: _replyReferences(mail),
                      initialBody: _quote(mail),
                    ),
                  ),
                );
              },
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: _load)
              : mail == null
                  ? const ErrorBody(message: 'Message missing')
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        Text(mail.fromLabel, style: Theme.of(context).textTheme.titleSmall),
                        if (mail.to.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text('To: ${mail.to}', style: const TextStyle(color: OdyColors.muted)),
                        ],
                        if (mail.date.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(mail.date, style: const TextStyle(color: OdyColors.muted)),
                        ],
                        if (mail.attachments.isNotEmpty) ...[
                          const SizedBox(height: 12),
                          Text(
                            'Attachments (open on the web to download):',
                            style: Theme.of(context).textTheme.labelLarge,
                          ),
                          ...mail.attachments.map(
                            (a) => ListTile(
                              dense: true,
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.attach_file, size: 18),
                              title: Text(a.filename),
                            ),
                          ),
                        ],
                        const SizedBox(height: 16),
                        SelectableText(
                          mail.plainBody.isEmpty ? '(no text body)' : mail.plainBody,
                        ),
                      ],
                    ),
    );
  }
}

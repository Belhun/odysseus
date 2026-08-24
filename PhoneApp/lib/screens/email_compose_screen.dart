import 'package:flutter/material.dart';

import '../api/email_client.dart';
import '../state/app_controller.dart';
import '../widgets/common.dart';

class EmailComposeScreen extends StatefulWidget {
  const EmailComposeScreen({
    super.key,
    required this.controller,
    this.client,
    this.accountId,
    this.to = '',
    this.cc = '',
    this.subject = '',
    this.initialBody = '',
    this.inReplyTo,
    this.references,
  });

  final AppController controller;
  final EmailClient? client;
  final String? accountId;
  final String to;
  final String cc;
  final String subject;
  final String initialBody;
  final String? inReplyTo;
  final String? references;

  @override
  State<EmailComposeScreen> createState() => _EmailComposeScreenState();
}

class _EmailComposeScreenState extends State<EmailComposeScreen> {
  late final TextEditingController _to;
  late final TextEditingController _cc;
  late final TextEditingController _subject;
  late final TextEditingController _body;
  bool _sending = false;
  bool _showCc = false;

  EmailClient get _api =>
      widget.client ?? EmailClient(widget.controller.odyHttp);

  @override
  void initState() {
    super.initState();
    _to = TextEditingController(text: widget.to);
    _cc = TextEditingController(text: widget.cc);
    _subject = TextEditingController(text: widget.subject);
    _body = TextEditingController(text: widget.initialBody);
    _showCc = widget.cc.trim().isNotEmpty;
  }

  @override
  void dispose() {
    _to.dispose();
    _cc.dispose();
    _subject.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final to = _to.text.trim();
    if (to.isEmpty) {
      await showBusyError(context, 'To is required');
      return;
    }
    setState(() => _sending = true);
    try {
      await _api.send(
        to: to,
        subject: _subject.text.trim(),
        body: _body.text,
        cc: _cc.text.trim().isEmpty ? null : _cc.text.trim(),
        accountId: widget.accountId,
        inReplyTo: widget.inReplyTo,
        references: widget.references,
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) await showBusyError(context, emailErrorMessage(e));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  Future<void> _saveDraft() async {
    setState(() => _sending = true);
    try {
      await _api.saveDraft(
        to: _to.text.trim(),
        subject: _subject.text.trim(),
        body: _body.text,
        cc: _cc.text.trim().isEmpty ? null : _cc.text.trim(),
        accountId: widget.accountId,
        inReplyTo: widget.inReplyTo,
        references: widget.references,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Draft saved on the server')),
        );
      }
    } catch (e) {
      if (mounted) await showBusyError(context, emailErrorMessage(e));
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.inReplyTo == null || widget.inReplyTo!.isEmpty ? 'Compose' : 'Reply'),
        actions: [
          IconButton(
            tooltip: 'Save draft',
            onPressed: _sending ? null : _saveDraft,
            icon: const Icon(Icons.save_outlined),
          ),
          IconButton(
            tooltip: 'Send',
            onPressed: _sending ? null : _send,
            icon: _sending
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.send),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _to,
            keyboardType: TextInputType.emailAddress,
            decoration: InputDecoration(
              labelText: 'To',
              suffixIcon: IconButton(
                tooltip: 'Cc',
                onPressed: () => setState(() => _showCc = !_showCc),
                icon: const Icon(Icons.group_add_outlined),
              ),
            ),
          ),
          if (_showCc) ...[
            const SizedBox(height: 8),
            TextField(
              controller: _cc,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Cc'),
            ),
          ],
          const SizedBox(height: 8),
          TextField(controller: _subject, decoration: const InputDecoration(labelText: 'Subject')),
          const SizedBox(height: 8),
          TextField(
            controller: _body,
            minLines: 10,
            maxLines: 20,
            decoration: const InputDecoration(labelText: 'Body'),
          ),
        ],
      ),
    );
  }
}

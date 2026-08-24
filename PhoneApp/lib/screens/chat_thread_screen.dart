import 'package:flutter/material.dart';

import '../api/chat_client.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class ChatThreadScreen extends StatefulWidget {
  const ChatThreadScreen({
    super.key,
    required this.controller,
    required this.sessionId,
    required this.title,
  });

  final AppController controller;
  final String sessionId;
  final String title;

  @override
  State<ChatThreadScreen> createState() => _ChatThreadScreenState();
}

class _ChatThreadScreenState extends State<ChatThreadScreen> {
  final _composer = TextEditingController();
  final _scroll = ScrollController();
  bool _loading = true;
  bool _sending = false;
  String? _error;
  List<ChatLine> _lines = [];

  ChatClient get _api => ChatClient(widget.controller.odyHttp);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _composer.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final lines = await _api.history(widget.sessionId);
      if (!mounted) return;
      setState(() {
        _lines = lines;
        _loading = false;
      });
      _jumpToEnd();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = '$e';
        _loading = false;
      });
    }
  }

  void _jumpToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  Future<void> _send() async {
    final text = _composer.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() {
      _sending = true;
      _lines = [
        ..._lines,
        ChatLine(role: 'user', content: text),
        ChatLine(role: 'assistant', content: ''),
      ];
    });
    _composer.clear();
    _jumpToEnd();
    try {
      await _api.sendStream(
        sessionId: widget.sessionId,
        message: text,
        onDelta: (delta) {
          if (!mounted) return;
          setState(() {
            final last = _lines.last;
            _lines = [
              ..._lines.sublist(0, _lines.length - 1),
              ChatLine(role: last.role, content: last.content + delta),
            ];
          });
          _jumpToEnd();
        },
      );
      if (!mounted) return;
      setState(() => _sending = false);
    } catch (e) {
      if (!mounted) return;
      setState(() => _sending = false);
      await showBusyError(context, e);
    }
  }

  Future<void> _stop() async {
    try {
      await _api.stop(widget.sessionId);
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: Column(
        children: [
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? ErrorBody(message: _error!, onRetry: _load)
                    : _lines.isEmpty
                        ? const Center(
                            child: Padding(
                              padding: EdgeInsets.all(24),
                              child: Text(
                                'Send a message to start this chat.',
                                textAlign: TextAlign.center,
                                style: TextStyle(color: OdyColors.muted),
                              ),
                            ),
                          )
                        : ListView.builder(
                            controller: _scroll,
                            padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
                            itemCount: _lines.length,
                            itemBuilder: (ctx, i) {
                              final line = _lines[i];
                              final mine = line.role == 'user';
                              final emptyAssistant =
                                  !mine && line.content.isEmpty && _sending && i == _lines.length - 1;
                              return Align(
                                alignment: mine
                                    ? Alignment.centerRight
                                    : Alignment.centerLeft,
                                child: Container(
                                  margin: const EdgeInsets.only(bottom: 8),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                    vertical: 10,
                                  ),
                                  constraints: BoxConstraints(
                                    maxWidth: MediaQuery.of(context).size.width * 0.82,
                                  ),
                                  decoration: BoxDecoration(
                                    color: mine ? OdyColors.hlBg : OdyColors.panel,
                                    border: Border.all(color: OdyColors.border),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Text(
                                    emptyAssistant ? 'Thinking…' : line.content,
                                    style: TextStyle(
                                      color: emptyAssistant ? OdyColors.muted : null,
                                    ),
                                  ),
                                ),
                              );
                            },
                          ),
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _composer,
                      minLines: 1,
                      maxLines: 5,
                      textInputAction: TextInputAction.send,
                      decoration: const InputDecoration(hintText: 'Message'),
                      onSubmitted: (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    onPressed: _sending ? _stop : _send,
                    style: IconButton.styleFrom(
                      backgroundColor: _sending ? OdyColors.red : OdyColors.accent,
                      foregroundColor: Colors.white,
                    ),
                    tooltip: _sending ? 'Stop' : 'Send',
                    icon: Icon(_sending ? Icons.stop : Icons.send),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

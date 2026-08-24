import 'package:flutter/material.dart';

import '../api/chat_client.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'chat_thread_screen.dart';

class ChatListScreen extends StatefulWidget {
  const ChatListScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<ChatListScreen> createState() => _ChatListScreenState();
}

class _ChatListScreenState extends State<ChatListScreen> {
  bool _loading = true;
  String? _error;
  List<ChatSession> _sessions = [];

  ChatClient get _api => ChatClient(widget.controller.odyHttp);

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
      final sessions = await _api.sessions();
      if (!mounted) return;
      setState(() {
        _sessions = sessions;
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

  Future<void> _openThread({required String id, required String title}) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ChatThreadScreen(
          controller: widget.controller,
          sessionId: id,
          title: title,
        ),
      ),
    );
    if (mounted) await _load();
  }

  Future<void> _newChat() async {
    try {
      final id = await _api.createSession();
      if (!mounted) return;
      await _openThread(id: id, title: 'Phone');
    } catch (e) {
      if (mounted) await showBusyError(context, e);
    }
  }

  String _subtitle(ChatSession session) {
    final when = session.updatedAt;
    if (when != null && when.isNotEmpty) return when;
    if (session.messageCount > 0) {
      return '${session.messageCount} messages';
    }
    return 'New chat';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Chat')),
      floatingActionButton: FloatingActionButton(
        onPressed: _newChat,
        tooltip: 'New chat',
        child: const Icon(Icons.add),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? ErrorBody(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: _sessions.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: const EdgeInsets.all(24),
                          children: [
                            const SizedBox(height: 48),
                            const Icon(Icons.chat_bubble_outline,
                                size: 40, color: OdyColors.muted),
                            const SizedBox(height: 16),
                            const Text(
                              'No chats yet',
                              textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 18),
                            ),
                            const SizedBox(height: 8),
                            const Text(
                              'Same conversations as the Odysseus sidebar. Start one here.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: OdyColors.muted),
                            ),
                            const SizedBox(height: 20),
                            Center(
                              child: FilledButton.icon(
                                onPressed: _newChat,
                                icon: const Icon(Icons.add),
                                label: const Text('New chat'),
                              ),
                            ),
                          ],
                        )
                      : ListView.separated(
                          physics: const AlwaysScrollableScrollPhysics(),
                          itemCount: _sessions.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (ctx, i) {
                            final s = _sessions[i];
                            return ListTile(
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 16,
                                vertical: 6,
                              ),
                              title: Text(
                                s.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                              subtitle: Text(
                                _subtitle(s),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(color: OdyColors.muted),
                              ),
                              trailing: const Icon(Icons.chevron_right),
                              onTap: () => _openThread(id: s.id, title: s.name),
                            );
                          },
                        ),
                ),
    );
  }
}

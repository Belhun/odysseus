import 'package:flutter/material.dart';

import '../api/notes_client.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'note_editor_screen.dart';

class NotesListScreen extends StatefulWidget {
  const NotesListScreen({
    super.key,
    this.controller,
    this.client,
  }) : assert(controller != null || client != null);

  /// AppController from More. Typed as Object so tests can pass a NotesClient
  /// without importing app_controller.
  final Object? controller;
  final NotesClient? client;

  @override
  State<NotesListScreen> createState() => _NotesListScreenState();
}

class _NotesListScreenState extends State<NotesListScreen> {
  final _search = TextEditingController();
  bool _loading = true;
  bool _archived = false;
  String? _error;
  String? _labelFilter;
  List<Note> _notes = [];

  NotesClient get _api => widget.client ?? notesClientFrom(widget.controller!);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final notes = await _api.listNotes(archived: _archived);
      if (!mounted) return;
      setState(() {
        _notes = notes;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = notesErrorMessage(e);
        _loading = false;
      });
    }
  }

  List<Note> get _visible {
    var list = _notes;
    final label = _labelFilter;
    if (label != null && label.isNotEmpty) {
      list = list.where((n) => n.tags.contains(label)).toList();
    }
    final q = _search.text.trim().toLowerCase();
    if (q.isEmpty) return list;
    return list.where((n) {
      if (n.title.toLowerCase().contains(q)) return true;
      if (n.content.toLowerCase().contains(q)) return true;
      if (n.label.toLowerCase().contains(q)) return true;
      return n.items.any((i) => i.text.toLowerCase().contains(q));
    }).toList();
  }

  List<String> get _allTags {
    final tags = <String>{};
    for (final n in _notes) {
      tags.addAll(n.tags);
    }
    final sorted = tags.toList()..sort();
    return sorted;
  }

  Future<void> _openEditor({Note? existing}) async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => NoteEditorScreen(client: _api, note: existing),
      ),
    );
    if (saved == true) await _load();
  }

  Future<void> _toggleItem(Note note, int index) async {
    try {
      final items = await _api.toggleItem(note.id, index);
      if (!mounted) return;
      setState(() {
        _notes = [
          for (final n in _notes)
            if (n.id == note.id) n.copyWith(items: items) else n,
        ];
      });
    } catch (e) {
      if (mounted) showBusyError(context, notesErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_archived ? 'Archived notes' : 'Notes'),
        actions: [
          IconButton(
            tooltip: _archived ? 'Active notes' : 'Archive',
            onPressed: () {
              setState(() {
                _archived = !_archived;
                _labelFilter = null;
              });
              _load();
            },
            icon: Icon(_archived ? Icons.unarchive : Icons.archive_outlined),
          ),
        ],
      ),
      floatingActionButton: _archived
          ? null
          : FloatingActionButton(
              onPressed: () => _openEditor(),
              tooltip: 'New note',
              child: const Icon(Icons.add),
            ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: TextField(
              controller: _search,
              decoration: const InputDecoration(
                hintText: 'Search notes',
                prefixIcon: Icon(Icons.search),
                isDense: true,
              ),
              onChanged: (_) => setState(() {}),
            ),
          ),
          if (_allTags.isNotEmpty)
            SizedBox(
              height: 44,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                children: [
                  for (final tag in _allTags)
                    Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text(tag),
                        selected: _labelFilter == tag,
                        onSelected: (on) => setState(() {
                          _labelFilter = on ? tag : null;
                        }),
                      ),
                    ),
                ],
              ),
            ),
          Expanded(child: _body()),
        ],
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return ErrorBody(message: _error!, onRetry: _load);
    }
    final visible = _visible;
    if (visible.isEmpty) {
      final empty = _search.text.trim().isNotEmpty || _labelFilter != null
          ? 'No matches'
          : _archived
              ? 'No archived notes'
              : 'No notes yet';
      return RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            const SizedBox(height: 80),
            Center(
              child: Text(empty, style: const TextStyle(color: OdyColors.muted)),
            ),
          ],
        ),
      );
    }
    final pinned = visible.where((n) => n.pinned).toList();
    final rest = visible.where((n) => !n.pinned).toList();
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 88),
        children: [
          if (pinned.isNotEmpty) ...[
            const Padding(
              padding: EdgeInsets.fromLTRB(4, 4, 4, 8),
              child: Text('Pinned', style: TextStyle(color: OdyColors.subheader)),
            ),
            for (final n in pinned) _card(n),
            if (rest.isNotEmpty)
              const Padding(
                padding: EdgeInsets.fromLTRB(4, 12, 4, 8),
                child: Text('Others', style: TextStyle(color: OdyColors.subheader)),
              ),
          ],
          for (final n in rest) _card(n),
        ],
      ),
    );
  }

  Widget _card(Note note) {
    final stripe = kNoteColorPresets[note.color];
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: OdyCard(
        onTap: () => _openEditor(existing: note),
        padding: EdgeInsets.zero,
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                width: 8,
                color: stripe == null ? Colors.transparent : Color(stripe),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(12, 12, 8, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              note.displayTitle,
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                          if (note.pinned)
                            const Icon(Icons.push_pin, size: 16, color: OdyColors.accent),
                        ],
                      ),
                      if (note.snippet.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(
                          note.snippet,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(color: OdyColors.muted, fontSize: 13),
                        ),
                      ],
                      if (note.dueDate.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          note.dueDate.replaceFirst('T', ' '),
                          style: const TextStyle(color: OdyColors.warn, fontSize: 12),
                        ),
                      ],
                      if (note.isChecklist && note.items.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        for (var i = 0; i < note.items.length && i < 6; i++)
                          InkWell(
                            onTap: () => _toggleItem(note, i),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(vertical: 2),
                              child: Row(
                                children: [
                                  Icon(
                                    note.items[i].done
                                        ? Icons.check_box
                                        : Icons.check_box_outline_blank,
                                    size: 18,
                                    color: note.items[i].done
                                        ? OdyColors.green
                                        : OdyColors.muted,
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      note.items[i].text,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        decoration: note.items[i].done
                                            ? TextDecoration.lineThrough
                                            : null,
                                        color: note.items[i].done
                                            ? OdyColors.muted
                                            : null,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

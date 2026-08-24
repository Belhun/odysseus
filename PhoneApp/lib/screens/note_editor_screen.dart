import 'package:flutter/material.dart';

import '../api/notes_client.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class NoteEditorScreen extends StatefulWidget {
  const NoteEditorScreen({
    super.key,
    required this.client,
    this.note,
  });

  final NotesClient client;
  final Note? note;

  @override
  State<NoteEditorScreen> createState() => _NoteEditorScreenState();
}

class _NoteEditorScreenState extends State<NoteEditorScreen> {
  final _title = TextEditingController();
  final _content = TextEditingController();
  final _label = TextEditingController();
  final List<TextEditingController> _itemTexts = [];
  late List<bool> _itemDone;
  late bool _checklist;
  late bool _pinned;
  late bool _archived;
  String _color = '';
  String _dueDate = '';
  bool _saving = false;
  String? _id;

  NotesClient get _api => widget.client;

  @override
  void initState() {
    super.initState();
    final note = widget.note;
    _id = note?.id;
    _title.text = note?.title ?? '';
    _content.text = note?.content ?? '';
    _label.text = note?.label ?? '';
    _checklist = note?.isChecklist ?? false;
    _pinned = note?.pinned ?? false;
    _archived = note?.archived ?? false;
    _color = note?.color ?? '';
    if (_color.isNotEmpty && !kNoteColorPresets.containsKey(_color)) {
      _color = '';
    }
    _dueDate = note?.dueDate ?? '';
    final items = note?.items ?? const <NoteItem>[];
    _itemDone = [];
    if (_checklist) {
      if (items.isEmpty) {
        _itemTexts.add(TextEditingController());
        _itemDone.add(false);
      } else {
        for (final item in items) {
          _itemTexts.add(TextEditingController(text: item.text));
          _itemDone.add(item.done);
        }
      }
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _content.dispose();
    _label.dispose();
    for (final c in _itemTexts) {
      c.dispose();
    }
    super.dispose();
  }

  void _addItem({String text = '', bool done = false}) {
    setState(() {
      _itemTexts.add(TextEditingController(text: text));
      _itemDone.add(done);
    });
  }

  void _removeItem(int index) {
    setState(() {
      _itemTexts.removeAt(index).dispose();
      _itemDone.removeAt(index);
      if (_itemTexts.isEmpty) {
        _itemTexts.add(TextEditingController());
        _itemDone.add(false);
      }
    });
  }

  void _setChecklist(bool value) {
    setState(() {
      _checklist = value;
      if (value && _itemTexts.isEmpty) {
        _itemTexts.add(TextEditingController(text: _content.text.trim()));
        _itemDone.add(false);
      }
    });
  }

  Map<String, dynamic> _body() {
    final items = <Map<String, dynamic>>[
      for (var i = 0; i < _itemTexts.length; i++)
        if (_itemTexts[i].text.trim().isNotEmpty)
          {'text': _itemTexts[i].text.trim(), 'done': _itemDone[i]},
    ];
    return {
      'title': _title.text.trim(),
      'content': _checklist ? null : _content.text,
      'note_type': _checklist ? 'checklist' : 'note',
      'items': _checklist ? items : null,
      'color': _color,
      'label': _label.text.trim(),
      'pinned': _pinned,
      'archived': _archived,
      'due_date': _dueDate,
    };
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      if (_id == null || _id!.isEmpty) {
        await _api.createNote(_body());
      } else {
        await _api.updateNote(_id!, _body());
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) {
        setState(() => _saving = false);
        await showBusyError(context, notesErrorMessage(e));
      }
    }
  }

  Future<void> _togglePin() async {
    final id = _id;
    if (id == null || id.isEmpty) {
      setState(() => _pinned = !_pinned);
      return;
    }
    try {
      final pinned = await _api.togglePin(id);
      if (mounted) setState(() => _pinned = pinned);
    } catch (e) {
      if (mounted) await showBusyError(context, notesErrorMessage(e));
    }
  }

  Future<void> _toggleArchive() async {
    final id = _id;
    if (id == null || id.isEmpty) {
      setState(() => _archived = !_archived);
      return;
    }
    try {
      final archived = await _api.toggleArchive(id);
      if (mounted) setState(() => _archived = archived);
    } catch (e) {
      if (mounted) await showBusyError(context, notesErrorMessage(e));
    }
  }

  Future<void> _toggleItemRemote(int index) async {
    final id = _id;
    setState(() => _itemDone[index] = !_itemDone[index]);
    if (id == null || id.isEmpty) return;
    try {
      final items = await _api.toggleItem(id, index);
      if (!mounted) return;
      setState(() {
        for (var i = 0; i < items.length && i < _itemDone.length; i++) {
          _itemDone[i] = items[i].done;
          if (_itemTexts[i].text != items[i].text) {
            _itemTexts[i].text = items[i].text;
          }
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _itemDone[index] = !_itemDone[index]);
      await showBusyError(context, notesErrorMessage(e));
    }
  }

  Future<void> _delete() async {
    final id = _id;
    if (id == null || id.isEmpty) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete note'),
        content: const Text('This removes the same row the web Notes panel uses.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await _api.deleteNote(id);
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) await showBusyError(context, notesErrorMessage(e));
    }
  }

  Future<void> _pickDueDate() async {
    final now = DateTime.now();
    DateTime initial = now;
    if (_dueDate.isNotEmpty) {
      initial = DateTime.tryParse(_dueDate) ?? now;
    }
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2018),
      lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(initial),
    );
    if (time == null || !mounted) return;
    setState(() {
      _dueDate = formatNoteDueDate(DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      ));
    });
  }

  @override
  Widget build(BuildContext context) {
    final isNew = _id == null || _id!.isEmpty;
    return Scaffold(
      appBar: AppBar(
        title: Text(isNew ? 'New note' : 'Edit note'),
        actions: [
          IconButton(
            tooltip: _pinned ? 'Unpin' : 'Pin',
            onPressed: _togglePin,
            icon: Icon(_pinned ? Icons.push_pin : Icons.push_pin_outlined),
          ),
          IconButton(
            tooltip: _archived ? 'Unarchive' : 'Archive',
            onPressed: _toggleArchive,
            icon: Icon(_archived ? Icons.unarchive : Icons.archive_outlined),
          ),
          if (!isNew)
            IconButton(
              tooltip: 'Delete',
              onPressed: _delete,
              icon: const Icon(Icons.delete_outline),
            ),
          TextButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Save'),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          TextField(
            controller: _title,
            decoration: const InputDecoration(labelText: 'Title'),
            textCapitalization: TextCapitalization.sentences,
          ),
          const SizedBox(height: 12),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Checklist'),
            value: _checklist,
            onChanged: _setChecklist,
          ),
          if (_checklist) ...[
            for (var i = 0; i < _itemTexts.length; i++)
              Row(
                children: [
                  IconButton(
                    onPressed: () => _toggleItemRemote(i),
                    icon: Icon(
                      _itemDone[i] ? Icons.check_box : Icons.check_box_outline_blank,
                      color: _itemDone[i] ? OdyColors.green : OdyColors.muted,
                    ),
                  ),
                  Expanded(
                    child: TextField(
                      controller: _itemTexts[i],
                      decoration: InputDecoration(
                        hintText: 'Item ${i + 1}',
                        isDense: true,
                      ),
                    ),
                  ),
                  IconButton(
                    onPressed: () => _removeItem(i),
                    icon: const Icon(Icons.close, size: 18),
                  ),
                ],
              ),
            TextButton.icon(
              onPressed: () => _addItem(),
              icon: const Icon(Icons.add),
              label: const Text('Add item'),
            ),
          ] else
            TextField(
              controller: _content,
              decoration: const InputDecoration(labelText: 'Note'),
              minLines: 8,
              maxLines: 16,
              textCapitalization: TextCapitalization.sentences,
            ),
          const SizedBox(height: 16),
          const Text('Color', style: TextStyle(color: OdyColors.subheader)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              _colorDot('', OdyColors.border),
              for (final entry in kNoteColorPresets.entries)
                _colorDot(entry.key, Color(entry.value)),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _label,
            decoration: const InputDecoration(
              labelText: 'Labels',
              hintText: 'work personal',
            ),
          ),
          const SizedBox(height: 12),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Due'),
            subtitle: Text(
              _dueDate.isEmpty ? 'None (reminders stay on the web panel)' : _dueDate.replaceFirst('T', ' '),
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (_dueDate.isNotEmpty)
                  IconButton(
                    tooltip: 'Clear due date',
                    onPressed: () => setState(() => _dueDate = ''),
                    icon: const Icon(Icons.clear),
                  ),
                IconButton(
                  onPressed: _pickDueDate,
                  icon: const Icon(Icons.event),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _colorDot(String name, Color color) {
    final selected = _color == name;
    return GestureDetector(
      onTap: () => setState(() => _color = name),
      child: Container(
        width: 32,
        height: 32,
        decoration: BoxDecoration(
          color: name.isEmpty ? Colors.transparent : color,
          shape: BoxShape.circle,
          border: Border.all(
            color: selected ? OdyColors.accent : OdyColors.border,
            width: selected ? 2 : 1,
          ),
        ),
        child: name.isEmpty
            ? const Icon(Icons.block, size: 16, color: OdyColors.muted)
            : null,
      ),
    );
  }
}

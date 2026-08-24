import 'models.dart';
import 'ody_http.dart';

/// Web Keep presets (`static/js/notes.js` COLOR_HEX). Stored as names, not hex.
const kNoteColorPresets = <String, int>{
  'red': 0xFFF0B5BA,
  'orange': 0xFFE8CCB2,
  'yellow': 0xFFF2DFBD,
  'green': 0xFFCCE0BC,
  'blue': 0xFFB0D7F7,
  'purple': 0xFFE2BCEE,
};

class NoteItem {
  NoteItem({required this.text, required this.done});

  final String text;
  final bool done;

  factory NoteItem.fromJson(Map<String, dynamic> json) {
    return NoteItem(
      text: asString(json['text']),
      done: asBool(json['done'] ?? json['checked']),
    );
  }

  Map<String, dynamic> toJson() => {'text': text, 'done': done};

  NoteItem copyWith({String? text, bool? done}) {
    return NoteItem(text: text ?? this.text, done: done ?? this.done);
  }
}

class Note {
  Note({
    required this.id,
    required this.title,
    required this.content,
    required this.items,
    required this.noteType,
    required this.color,
    required this.label,
    required this.pinned,
    required this.archived,
    required this.dueDate,
    this.owner,
    this.sortOrder = 0,
    this.updatedAt,
  });

  final String id;
  final String title;
  final String content;
  final List<NoteItem> items;
  final String noteType;
  final String color;
  final String label;
  final bool pinned;
  final bool archived;
  final String dueDate;
  final String? owner;
  final int sortOrder;
  final String? updatedAt;

  bool get isChecklist =>
      noteType == 'todo' || noteType == 'goal' || noteType == 'checklist';

  List<String> get tags =>
      label.trim().isEmpty ? const [] : label.trim().split(RegExp(r'\s+'));

  String get snippet {
    if (isChecklist) {
      if (items.isEmpty) return 'Empty checklist';
      final done = items.where((i) => i.done).length;
      return '$done/${items.length} done';
    }
    return content.trim();
  }

  String get displayTitle {
    if (title.trim().isNotEmpty) return title.trim();
    if (isChecklist && items.isNotEmpty) {
      final first = items.first.text.trim();
      if (first.isNotEmpty) return first;
    }
    final line = content.trim().split('\n').first.trim();
    if (line.isNotEmpty) return line;
    return 'Untitled';
  }

  factory Note.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    final items = <NoteItem>[];
    if (rawItems is List) {
      for (final item in rawItems) {
        if (item is Map) {
          items.add(NoteItem.fromJson(Map<String, dynamic>.from(item)));
        }
      }
    }
    return Note(
      id: asString(json['id']),
      title: asString(json['title']),
      content: asString(json['content']),
      items: items,
      noteType: asString(json['note_type'], 'note'),
      color: asString(json['color']),
      label: asString(json['label']),
      pinned: asBool(json['pinned']),
      archived: asBool(json['archived']),
      dueDate: asString(json['due_date']),
      owner: json['owner']?.toString(),
      sortOrder: asInt(json['sort_order']),
      updatedAt: json['updated_at']?.toString(),
    );
  }

  Note copyWith({
    String? title,
    String? content,
    List<NoteItem>? items,
    String? noteType,
    String? color,
    String? label,
    bool? pinned,
    bool? archived,
    String? dueDate,
  }) {
    return Note(
      id: id,
      title: title ?? this.title,
      content: content ?? this.content,
      items: items ?? this.items,
      noteType: noteType ?? this.noteType,
      color: color ?? this.color,
      label: label ?? this.label,
      pinned: pinned ?? this.pinned,
      archived: archived ?? this.archived,
      dueDate: dueDate ?? this.dueDate,
      owner: owner,
      sortOrder: sortOrder,
      updatedAt: updatedAt,
    );
  }
}

String notesErrorMessage(Object error) {
  if (error is ApiException && error.statusCode == 403) {
    return 'This token needs notes:read and notes:write. Cookie login works. '
        'A phone_finance token is not enough.';
  }
  return '$error';
}

/// Formats a local due date the way the web datetime-local field stores it.
String formatNoteDueDate(DateTime dt) {
  String two(int n) => n.toString().padLeft(2, '0');
  return '${dt.year}-${two(dt.month)}-${two(dt.day)}T${two(dt.hour)}:${two(dt.minute)}';
}

NotesClient notesClientFrom(Object controller) {
  final asClient = controller is NotesClient ? controller : null;
  if (asClient != null) return asClient;
  final dynamic bag = controller;
  final httpLayer = bag.httpLayer;
  if (httpLayer is OdyHttp) return NotesClient(httpLayer);
  final finance = bag.finance;
  final nested = finance?.httpClient;
  if (nested is OdyHttp) return NotesClient(nested);
  throw StateError('No Odysseus HTTP client on controller');
}

class NotesClient {
  NotesClient(this.httpClient);

  final OdyHttp httpClient;

  Future<List<Note>> listNotes({bool archived = false, String? label}) async {
    final data = await httpClient.get('/api/notes', query: {
      'archived': '$archived',
      if (label != null && label.isNotEmpty) 'label': label,
    });
    final map = _asMap(data);
    return (map['notes'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Note.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<Note> getNote(String id) async {
    final data = await httpClient.get('/api/notes/$id');
    return Note.fromJson(_asMap(data));
  }

  Future<Note> createNote(Map<String, dynamic> body) async {
    final data = await httpClient.sendJson('POST', '/api/notes', body: body);
    return Note.fromJson(_asMap(data));
  }

  Future<Note> updateNote(String id, Map<String, dynamic> body) async {
    final data = await httpClient.sendJson('PUT', '/api/notes/$id', body: body);
    return Note.fromJson(_asMap(data));
  }

  Future<void> deleteNote(String id) async {
    await httpClient.sendJson('DELETE', '/api/notes/$id');
  }

  Future<bool> togglePin(String id) async {
    final data = await httpClient.sendJson('POST', '/api/notes/$id/pin');
    return asBool(_asMap(data)['pinned']);
  }

  Future<bool> toggleArchive(String id) async {
    final data = await httpClient.sendJson('POST', '/api/notes/$id/archive');
    return asBool(_asMap(data)['archived']);
  }

  Future<List<NoteItem>> toggleItem(String id, int index) async {
    final data = await httpClient.sendJson(
      'POST',
      '/api/notes/$id/items/$index/toggle',
    );
    final raw = _asMap(data)['items'];
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((e) => NoteItem.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return <String, dynamic>{};
  }
}

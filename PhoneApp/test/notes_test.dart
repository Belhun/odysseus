import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/notes_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/note_editor_screen.dart';
import 'package:odysseus_phone/screens/notes_list_screen.dart';

class NotesHttp extends http.BaseClient {
  NotesHttp({
    this.notes = const [],
    this.statusCode = 200,
    this.errorBody,
  });

  List<Map<String, dynamic>> notes;
  int statusCode;
  String? errorBody;
  final List<String> paths = [];
  Map<String, dynamic>? lastBody;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    paths.add('${request.method} ${request.url.path}');
    if (request is http.Request && request.body.isNotEmpty) {
      lastBody = jsonDecode(request.body) as Map<String, dynamic>;
    }
    Object payload;
    if (statusCode >= 400) {
      payload = errorBody ?? {'detail': 'boom'};
    } else if (request.url.path.endsWith('/api/notes') && request.method == 'GET') {
      final archived = request.url.queryParameters['archived'] == 'true';
      payload = {
        'notes': notes.where((n) => (n['archived'] == true) == archived).toList(),
      };
    } else if (request.url.path.endsWith('/api/notes') && request.method == 'POST') {
      payload = {
        'id': 'new-1',
        ...?lastBody,
        'pinned': lastBody?['pinned'] ?? false,
        'archived': lastBody?['archived'] ?? false,
        'items': lastBody?['items'] ?? [],
      };
    } else if (request.url.path.contains('/items/') && request.url.path.endsWith('/toggle')) {
      payload = {
        'ok': true,
        'items': [
          {'text': 'Milk', 'done': true},
        ],
      };
    } else if (request.url.path.endsWith('/pin')) {
      payload = {'ok': true, 'pinned': true};
    } else if (request.url.path.endsWith('/archive')) {
      payload = {'ok': true, 'archived': true};
    } else if (request.method == 'DELETE') {
      payload = {'ok': true};
    } else if (request.method == 'PUT') {
      final id = request.url.path.split('/').last;
      payload = {'id': id, ...?lastBody};
    } else {
      payload = {'ok': true};
    }
    final bytes = utf8.encode(jsonEncode(payload));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}

Map<String, dynamic> _noteJson({
  String id = 'n1',
  String title = 'Groceries',
  String content = 'Buy milk',
  bool pinned = false,
  bool archived = false,
  String color = 'yellow',
  String label = 'home',
  String noteType = 'note',
  List<Map<String, dynamic>>? items,
  String dueDate = '',
}) {
  return {
    'id': id,
    'title': title,
    'content': content,
    'pinned': pinned,
    'archived': archived,
    'color': color,
    'label': label,
    'note_type': noteType,
    'items': items,
    'due_date': dueDate,
    'sort_order': 0,
  };
}

NotesClient _client(http.Client raw) {
  return NotesClient(OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('Note.fromJson reads Keep fields and checklist items', () {
    final note = Note.fromJson(_noteJson(
      noteType: 'checklist',
      items: [
        {'text': 'Milk', 'done': false},
        {'text': 'Eggs', 'done': true, 'checked': true},
      ],
      dueDate: '2026-08-24T09:00',
    ));
    expect(note.id, 'n1');
    expect(note.isChecklist, isTrue);
    expect(note.items, hasLength(2));
    expect(note.items.first.text, 'Milk');
    expect(note.items.last.done, isTrue);
    expect(note.tags, ['home']);
    expect(note.snippet, '1/2 done');
    expect(note.dueDate, '2026-08-24T09:00');
  });

  test('formatNoteDueDate matches web datetime-local', () {
    expect(
      formatNoteDueDate(DateTime(2026, 8, 23, 18, 5)),
      '2026-08-23T18:05',
    );
  });

  test('notesErrorMessage maps 403 to notes scopes', () {
    expect(
      notesErrorMessage(ApiException(403, 'Forbidden')),
      contains('notes:read'),
    );
  });

  test('NotesClient.listNotes hits /api/notes and parses rows', () async {
    final raw = NotesHttp(notes: [
      _noteJson(id: 'p1', title: 'Pinned', pinned: true),
      _noteJson(id: 'a1', title: 'Later'),
    ]);
    final listed = await _client(raw).listNotes();
    expect(raw.paths, contains('GET /api/notes'));
    expect(listed.map((n) => n.id).toList(), ['p1', 'a1']);
    expect(listed.first.pinned, isTrue);
  });

  test('NotesClient.createNote POSTs title body color', () async {
    final raw = NotesHttp();
    final created = await _client(raw).createNote({
      'title': 'Hello',
      'content': 'World',
      'color': 'blue',
      'note_type': 'note',
    });
    expect(raw.paths, contains('POST /api/notes'));
    expect(raw.lastBody!['title'], 'Hello');
    expect(raw.lastBody!['color'], 'blue');
    expect(created.id, 'new-1');
  });

  test('NotesClient.toggleItem hits index path', () async {
    final raw = NotesHttp();
    final items = await _client(raw).toggleItem('n1', 0);
    expect(raw.paths.single, 'POST /api/notes/n1/items/0/toggle');
    expect(items.single.done, isTrue);
  });

  testWidgets('list shows empty copy', (tester) async {
    final raw = NotesHttp(notes: []);
    await tester.pumpWidget(
      MaterialApp(home: NotesListScreen(client: _client(raw))),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('No notes yet'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  testWidgets('list shows pinned first and filters search', (tester) async {
    final raw = NotesHttp(notes: [
      _noteJson(id: 'p1', title: 'Pinned idea', pinned: true, content: 'alpha'),
      _noteJson(id: 'a1', title: 'Shopping', content: 'bananas'),
    ]);
    await tester.pumpWidget(
      MaterialApp(home: NotesListScreen(client: _client(raw))),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Pinned'), findsOneWidget);
    expect(find.text('Pinned idea'), findsOneWidget);
    expect(find.text('Shopping'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'bananas');
    await tester.pump();
    expect(find.text('Shopping'), findsOneWidget);
    expect(find.text('Pinned idea'), findsNothing);
    expect(find.text('Pinned'), findsNothing);
  });

  testWidgets('list error shows retry and 403 copy', (tester) async {
    final raw = NotesHttp(statusCode: 403, errorBody: '{"detail":"nope"}');
    await tester.pumpWidget(
      MaterialApp(home: NotesListScreen(client: _client(raw))),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('notes:read'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('checklist card toggles via existing endpoint', (tester) async {
    final raw = NotesHttp(notes: [
      _noteJson(
        id: 'c1',
        title: 'Store',
        noteType: 'checklist',
        items: [
          {'text': 'Milk', 'done': false},
        ],
      ),
    ]);
    await tester.pumpWidget(
      MaterialApp(home: NotesListScreen(client: _client(raw))),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('Milk'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(raw.paths, contains('POST /api/notes/c1/items/0/toggle'));
  });

  testWidgets('editor shows title body pin archive', (tester) async {
    final raw = NotesHttp();
    await tester.pumpWidget(
      MaterialApp(
        home: NoteEditorScreen(
          client: _client(raw),
          note: Note.fromJson(_noteJson(title: 'Hello', content: 'World')),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('Edit note'), findsOneWidget);
    expect(find.text('Hello'), findsOneWidget);
    expect(find.text('World'), findsOneWidget);
    expect(find.byTooltip('Pin'), findsOneWidget);
    expect(find.byTooltip('Archive'), findsOneWidget);
    expect(find.byTooltip('Delete'), findsOneWidget);
  });

  testWidgets('new editor save POSTs a note', (tester) async {
    final raw = NotesHttp();
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (ctx) => TextButton(
            onPressed: () {
              Navigator.of(ctx).push(
                MaterialPageRoute(
                  builder: (_) => NoteEditorScreen(client: _client(raw)),
                ),
              );
            },
            child: const Text('go'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('go'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, 'From phone');
    await tester.tap(find.text('Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(raw.paths, contains('POST /api/notes'));
    expect(raw.lastBody!['title'], 'From phone');
    expect(raw.lastBody!['note_type'], 'note');
  });
}

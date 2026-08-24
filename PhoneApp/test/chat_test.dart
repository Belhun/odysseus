import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/chat_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/chat_list_screen.dart';
import 'package:odysseus_phone/screens/chat_thread_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:odysseus_phone/theme/ody_theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ChatHttp extends http.BaseClient {
  ChatHttp({
    this.sessions = const [],
    this.history = const [],
    this.listStatus = 200,
    this.detail,
    this.streamChunks,
  });

  final List<Map<String, dynamic>> sessions;
  final List<Map<String, dynamic>> history;
  final int listStatus;
  final String? detail;
  final List<String>? streamChunks;
  final List<String> paths = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    paths.add('${request.method} ${request.url.path}');
    final path = request.url.path;
    Object body = {'ok': true};
    var status = 200;
    var contentType = 'application/json';
    String? raw;

    if (path.endsWith('/api/mobile/chat/sessions') && request.method == 'GET') {
      status = listStatus;
      if (listStatus >= 400) {
        body = {'detail': detail ?? 'API token requires chat scope'};
      } else {
        body = {'sessions': sessions};
      }
    } else if (path.endsWith('/api/mobile/chat/sessions') && request.method == 'POST') {
      body = {'id': 'new1', 'name': 'Phone', 'model': 'local'};
    } else if (path.contains('/api/history/')) {
      body = {'history': history};
    } else if (path.endsWith('/api/chat')) {
      body = {'response': 'pong'};
    } else if (path.endsWith('/api/chat_stream')) {
      contentType = 'text/event-stream';
      raw = (streamChunks ??
              [
                'data: {"delta":"Hello "}\n\n',
                'data: {"delta":"from Odysseus"}\n\n',
                'data: [DONE]\n\n',
              ])
          .join();
    } else if (path.contains('/api/chat/stop/')) {
      body = {'stopped': true};
    }

    final bytes = utf8.encode(raw ?? jsonEncode(body));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      status,
      headers: {'content-type': contentType},
    );
  }
}

Future<AppController> _controller(http.Client raw) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: raw);
  controller.httpLayer = OdyHttp(
    baseUrl: 'http://test:7000',
    token: 'ody_test',
    client: raw,
  );
  return controller;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('ChatSession.fromJson reads list rows', () {
    final s = ChatSession.fromJson({
      'id': 's1',
      'name': 'Budget help',
      'last_message_at': '2026-08-23T12:00:00',
      'message_count': 4,
    });
    expect(s.id, 's1');
    expect(s.name, 'Budget help');
    expect(s.updatedAt, contains('2026-08-23'));
    expect(s.messageCount, 4);
  });

  test('parseChatSseData reads delta and ignores DONE', () {
    expect(parseChatSseData('{"delta":"Hi"}'), 'Hi');
    expect(parseChatSseData('[DONE]'), isNull);
    expect(parseChatSseData('{"delta":"x","thinking":true}'), '');
  });

  test('ChatClient.sessions reads wrapped mobile JSON', () async {
    final raw = ChatHttp(sessions: [
      {'id': 's1', 'name': 'Hello', 'message_count': 2},
    ]);
    final api = ChatClient(OdyHttp(
      baseUrl: 'http://test:7000',
      token: 'ody_chat',
      client: raw,
    ));
    final sessions = await api.sessions();
    expect(sessions, hasLength(1));
    expect(sessions.first.name, 'Hello');
  });

  test('ChatClient.sessions maps 403 to chat-scope copy', () async {
    final raw = ChatHttp(listStatus: 403);
    final api = ChatClient(OdyHttp(
      baseUrl: 'http://test:7000',
      token: 'ody_finance',
      client: raw,
    ));
    try {
      await api.sessions();
      fail('expected 403');
    } on ApiException catch (e) {
      expect(e.statusCode, 403);
      expect(e.message.toLowerCase(), contains('chat'));
    }
  });

  test('ChatClient.sendStream concatenates SSE deltas', () async {
    final raw = ChatHttp();
    final api = ChatClient(OdyHttp(
      baseUrl: 'http://test:7000',
      token: 'ody_chat',
      client: raw,
    ));
    final pieces = <String>[];
    final text = await api.sendStream(
      sessionId: 's1',
      message: 'hi',
      onDelta: pieces.add,
    );
    expect(text, 'Hello from Odysseus');
    expect(pieces.join(), 'Hello from Odysseus');
  });

  testWidgets('empty chat list shows new-chat CTA', (tester) async {
    final raw = ChatHttp();
    final controller = await _controller(raw);
    await tester.pumpWidget(MaterialApp(
      theme: OdyTheme.dark(),
      home: ChatListScreen(controller: controller),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('No chats yet'), findsOneWidget);
    expect(find.text('New chat'), findsOneWidget);
  });

  testWidgets('403 shows retry', (tester) async {
    final raw = ChatHttp(listStatus: 403, detail: 'API token requires chat scope');
    final controller = await _controller(raw);
    await tester.pumpWidget(MaterialApp(
      theme: OdyTheme.dark(),
      home: ChatListScreen(controller: controller),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('chat'), findsWidgets);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('thread renders history bubbles', (tester) async {
    final raw = ChatHttp(history: [
      {'role': 'user', 'content': 'Hello'},
      {'role': 'assistant', 'content': 'Hi there'},
    ]);
    final controller = await _controller(raw);
    await tester.pumpWidget(MaterialApp(
      theme: OdyTheme.dark(),
      home: ChatThreadScreen(
        controller: controller,
        sessionId: 's1',
        title: 'Hello',
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Hello'), findsWidgets);
    expect(find.text('Hi there'), findsOneWidget);
  });
}

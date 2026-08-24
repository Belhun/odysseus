import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/email_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/email_compose_screen.dart';
import 'package:odysseus_phone/screens/email_list_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class EmailHttp extends http.BaseClient {
  EmailHttp({
    this.accounts = const [],
    this.folders = const ['INBOX', 'Sent'],
    this.emails = const [],
    this.readBody,
    this.statusCode = 200,
    this.errorBody,
  });

  List<Map<String, dynamic>> accounts;
  List<String> folders;
  List<Map<String, dynamic>> emails;
  Map<String, dynamic>? readBody;
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
    final path = request.url.path;
    if (statusCode >= 400) {
      payload = errorBody ?? {'detail': 'boom'};
    } else if (path.endsWith('/api/email/accounts')) {
      payload = {'accounts': accounts};
    } else if (path.endsWith('/api/email/folders')) {
      payload = {'folders': folders};
    } else if (path.endsWith('/api/email/list') || path.endsWith('/api/email/search')) {
      payload = {'emails': emails, 'total': emails.length, 'folder': 'INBOX'};
    } else if (path.contains('/api/email/read/')) {
      payload = readBody ??
          {
            'uid': '1',
            'subject': 'Hello',
            'from_name': 'Ada',
            'from_address': 'ada@example.com',
            'to': 'me@example.com',
            'body': 'Plain body',
            'body_html': '',
            'message_id': '<m1@example.com>',
            'attachments': [
              {'filename': 'invoice.pdf', 'size': 1200},
            ],
          };
    } else if (path.contains('/api/email/mark-read/') ||
        path.contains('/api/email/mark-unread/')) {
      payload = {'success': true};
    } else if (path.endsWith('/api/email/send') || path.endsWith('/api/email/draft')) {
      payload = {'success': true, 'queued': true};
    } else {
      payload = {'ok': true};
    }
    final bytes = utf8.encode(payload is String ? payload : jsonEncode(payload));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  }
}

Map<String, dynamic> _accountJson({
  String id = 'acc1',
  String name = 'Personal',
  bool isDefault = true,
}) {
  return {
    'id': id,
    'name': name,
    'from_address': 'me@example.com',
    'display_name': 'Me',
    'is_default': isDefault,
    'enabled': true,
  };
}

Map<String, dynamic> _headerJson({
  String uid = '10',
  String subject = 'Invoice',
  String fromName = 'Billing',
  bool isRead = false,
}) {
  return {
    'uid': uid,
    'subject': subject,
    'from_name': fromName,
    'from_address': 'bills@example.com',
    'date': '2026-08-23T12:00:00+00:00',
    'date_epoch': 1755950400,
    'is_read': isRead,
    'has_attachments': true,
  };
}

Future<AppController> _controller(http.Client raw) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: raw);
  controller.httpLayer = OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw);
  return controller;
}

EmailClient _client(http.Client raw) {
  return EmailClient(OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('EmailHeader.fromJson maps web list fields', () {
    final h = EmailHeader.fromJson(_headerJson());
    expect(h.uid, '10');
    expect(h.unread, isTrue);
    expect(h.fromLabel, 'Billing');
    expect(h.hasAttachments, isTrue);
  });

  test('htmlToPlainText strips tags and scripts', () {
    expect(
      htmlToPlainText('<p>Hi<br>there</p><script>alert(1)</script>'),
      contains('Hi'),
    );
    expect(htmlToPlainText('<b>Hi</b> &amp; you'), 'Hi & you');
  });

  test('emailErrorMessage maps 403 to email scopes', () {
    expect(
      emailErrorMessage(ApiException(403, 'Forbidden')),
      contains('email:read'),
    );
  });

  test('EmailClient.listAccounts hits /api/email/accounts', () async {
    final raw = EmailHttp(accounts: [_accountJson()]);
    final listed = await _client(raw).listAccounts();
    expect(raw.paths, contains('GET /api/email/accounts'));
    expect(listed.single.label, 'Personal');
  });

  test('EmailClient.listMessages hits /api/email/list', () async {
    final raw = EmailHttp(emails: [_headerJson()]);
    final listed = await _client(raw).listMessages(filter: 'unread');
    expect(raw.paths.single, 'GET /api/email/list');
    expect(listed.single.subject, 'Invoice');
    expect(listed.single.unread, isTrue);
  });

  test('EmailClient.read prefers body then html', () async {
    final raw = EmailHttp(readBody: {
      'uid': '1',
      'subject': 'Hi',
      'from_name': 'Ada',
      'from_address': 'ada@example.com',
      'body': '',
      'body_html': '<p>HTML only</p>',
      'message_id': '<x@y>',
    });
    final mail = await _client(raw).read('1');
    expect(raw.paths.single, 'GET /api/email/read/1');
    expect(mail.plainBody, contains('HTML only'));
  });

  test('EmailClient.send posts SendEmailRequest fields', () async {
    final raw = EmailHttp();
    await _client(raw).send(
      to: 'ada@example.com',
      subject: 'Re: Hello',
      body: 'Thanks',
      accountId: 'acc1',
      inReplyTo: '<m1@example.com>',
    );
    expect(raw.paths.single, 'POST /api/email/send');
    expect(raw.lastBody!['to'], 'ada@example.com');
    expect(raw.lastBody!['in_reply_to'], '<m1@example.com>');
    expect(raw.lastBody!['account_id'], 'acc1');
  });

  testWidgets('list shows empty-account copy', (tester) async {
    final raw = EmailHttp(accounts: []);
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: EmailListScreen(controller: controller, client: _client(raw)),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('No email accounts'), findsOneWidget);
    expect(find.textContaining('Google OAuth'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsNothing);
  });

  testWidgets('list shows unread subject from IMAP fields', (tester) async {
    final raw = EmailHttp(
      accounts: [_accountJson()],
      emails: [_headerJson(subject: 'Board packet')],
    );
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: EmailListScreen(controller: controller, client: _client(raw)),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Board packet'), findsOneWidget);
    expect(find.textContaining('Billing'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  testWidgets('list error shows retry and 403 copy', (tester) async {
    final raw = EmailHttp(statusCode: 403, errorBody: '{"detail":"nope"}');
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: EmailListScreen(controller: controller, client: _client(raw)),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('email:read'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('compose send posts to /api/email/send', (tester) async {
    final raw = EmailHttp(accounts: [_accountJson()]);
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: EmailComposeScreen(
          controller: controller,
          client: _client(raw),
          accountId: 'acc1',
        ),
      ),
    );
    await tester.pump();
    final fields = find.byType(TextField);
    await tester.enterText(fields.at(0), 'ada@example.com');
    await tester.enterText(fields.at(1), 'Hello');
    await tester.enterText(fields.at(2), 'Hi Ada');
    await tester.tap(find.byTooltip('Send'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(raw.paths, contains('POST /api/email/send'));
    expect(raw.lastBody!['to'], 'ada@example.com');
    expect(raw.lastBody!['subject'], 'Hello');
  });
}

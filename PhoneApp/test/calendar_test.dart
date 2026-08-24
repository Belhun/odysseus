import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/calendar_client.dart';
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/calendar_event_screen.dart';
import 'package:odysseus_phone/screens/calendar_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class CalendarHttp extends http.BaseClient {
  CalendarHttp({
    this.calendars = const [],
    this.events = const [],
    this.statusCode = 200,
    this.errorBody,
  });

  List<Map<String, dynamic>> calendars;
  List<Map<String, dynamic>> events;
  int statusCode;
  String? errorBody;
  final List<String> calls = [];
  Map<String, String> lastQuery = {};
  Map<String, dynamic>? lastBody;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    calls.add('${request.method} ${request.url.path}');
    lastQuery = request.url.queryParameters;
    if (request is http.Request && request.body.isNotEmpty) {
      lastBody = jsonDecode(request.body) as Map<String, dynamic>;
    }
    Object payload;
    if (statusCode >= 400) {
      payload = errorBody ?? {'detail': 'forbidden'};
    } else if (request.url.path.endsWith('/calendars')) {
      payload = {'calendars': calendars};
    } else if (request.url.path.endsWith('/events') && request.method == 'GET') {
      payload = {'events': events};
    } else if (request.url.path.endsWith('/events') && request.method == 'POST') {
      payload = {'ok': true, 'uid': 'new-1'};
    } else if (request.method == 'PUT' || request.method == 'DELETE') {
      payload = {'ok': true};
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

Map<String, dynamic> _calJson({
  String href = 'cal-1',
  String name = 'Personal',
  String color = '#5b8abf',
}) {
  return {'href': href, 'name': name, 'color': color, 'source': 'local'};
}

Map<String, dynamic> _eventJson({
  String uid = 'e1',
  String summary = 'Standup',
  String dtstart = '2026-08-15T09:00:00-07:00',
  String dtend = '2026-08-15T09:30:00-07:00',
  bool allDay = false,
  String calendarHref = 'cal-1',
  String calendar = 'Personal',
  String color = '#5b8abf',
  String rrule = '',
  bool isRecurrence = false,
  String seriesUid = '',
}) {
  return {
    'uid': uid,
    'summary': summary,
    'dtstart': dtstart,
    'dtend': dtend,
    'all_day': allDay,
    'calendar_href': calendarHref,
    'calendar': calendar,
    'color': color,
    'rrule': rrule,
    'is_recurrence': isRecurrence,
    'series_uid': seriesUid,
    'description': '',
    'location': '',
  };
}

Future<AppController> _controller(http.Client raw) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: raw);
  controller.finance = FinanceClient(
    OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw),
  );
  return controller;
}

CalendarClient _client(http.Client raw) {
  return CalendarClient(
    OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('localDateOf keeps naive dates and buckets Z to local', () {
    expect(localDateOf('2026-08-15'), '2026-08-15');
    expect(localDateOf('2026-08-15T22:00:00'), '2026-08-15');
    final z = DateTime.parse('2026-08-15T22:00:00Z').toLocal();
    expect(localDateOf('2026-08-15T22:00:00Z'), ymd(z));
  });

  test('eventOccursOn all-day exclusive end and timed local day', () {
    final allDay = CalendarEvent.fromJson(_eventJson(
      uid: 'ad',
      allDay: true,
      dtstart: '2026-08-15',
      dtend: '2026-08-16',
    ));
    expect(eventOccursOn(allDay, '2026-08-15'), isTrue);
    expect(eventOccursOn(allDay, '2026-08-16'), isFalse);

    final same = CalendarEvent.fromJson(_eventJson(
      uid: 'same',
      allDay: true,
      dtstart: '2026-08-20',
      dtend: '2026-08-20',
    ));
    expect(eventOccursOn(same, '2026-08-20'), isTrue);

    final timed = CalendarEvent.fromJson(_eventJson(
      dtstart: '2026-08-15T09:00:00',
      dtend: '2026-08-15T10:00:00',
    ));
    expect(eventOccursOn(timed, '2026-08-15'), isTrue);
    expect(eventOccursOn(timed, '2026-08-16'), isFalse);
  });

  test('stampLocalDateTime includes a timezone offset', () {
    final stamp = stampLocalDateTime(DateTime(2026, 8, 15, 9, 5));
    expect(stamp, startsWith('2026-08-15T09:05:00'));
    expect(stamp.contains('+') || stamp.contains('-'), isTrue);
    expect(stampAllDay(DateTime(2026, 8, 15)), '2026-08-15');
  });

  test('monthGrid Monday-starts before the 1st', () {
    final grid = monthGrid(DateTime(2026, 8, 1));
    expect(grid, hasLength(42));
    expect(grid.first, DateTime(2026, 7, 27));
    final range = monthQueryRange(DateTime(2026, 8, 1));
    expect(range.$1, '2026-07-27');
    expect(range.$2, '2026-09-07');
  });

  test('CalendarEvent.fromJson maps href, all_day, occurrence uid', () {
    final e = CalendarEvent.fromJson(_eventJson(
      uid: 'base::2026-08-15',
      allDay: true,
      dtstart: '2026-08-15',
      dtend: '2026-08-16',
      calendarHref: 'cal-9',
      isRecurrence: true,
      seriesUid: 'base',
    ));
    expect(e.uid, 'base::2026-08-15');
    expect(e.allDay, isTrue);
    expect(e.calendarHref, 'cal-9');
    expect(e.isOccurrence, isTrue);
    expect(e.seriesId, 'base');
  });

  test('CalendarClient.listEvents hits /api/calendar/events with start/end', () async {
    final raw = CalendarHttp(events: [_eventJson()]);
    final listed = await _client(raw).listEvents(start: '2026-08-01', end: '2026-09-01');
    expect(raw.calls.single, 'GET /api/calendar/events');
    expect(raw.lastQuery['start'], '2026-08-01');
    expect(raw.lastQuery['end'], '2026-09-01');
    expect(listed.single.summary, 'Standup');
  });

  test('CalendarClient.createEvent POSTs summary and calendar_href', () async {
    final raw = CalendarHttp();
    final uid = await _client(raw).createEvent({
      'summary': 'Dentist',
      'dtstart': '2026-08-15T09:00:00-07:00',
      'calendar_href': 'cal-1',
    });
    expect(raw.calls.single, 'POST /api/calendar/events');
    expect(raw.lastBody!['summary'], 'Dentist');
    expect(raw.lastBody!['calendar_href'], 'cal-1');
    expect(uid, 'new-1');
  });

  test('calendarErrorMessage maps 403 to calendar scopes', () {
    expect(
      calendarErrorMessage(ApiException(403, 'Forbidden')),
      contains('calendar:read'),
    );
  });

  testWidgets('month shows empty copy for the selected day', (tester) async {
    final raw = CalendarHttp(calendars: [_calJson()], events: []);
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: CalendarScreen(
          controller: controller,
          client: _client(raw),
          now: DateTime(2026, 8, 15),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('August 2026'), findsOneWidget);
    expect(find.text('No events this day'), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  testWidgets('403 shows calendar scope copy and Retry', (tester) async {
    final raw = CalendarHttp(statusCode: 403, errorBody: '{"detail":"nope"}');
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: CalendarScreen(
          controller: controller,
          client: _client(raw),
          now: DateTime(2026, 8, 15),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('calendar:read'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('tapping a dotted day lists the event title', (tester) async {
    final raw = CalendarHttp(
      calendars: [_calJson()],
      events: [_eventJson(summary: 'Standup')],
    );
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: CalendarScreen(
          controller: controller,
          client: _client(raw),
          now: DateTime(2026, 8, 15),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.byKey(const ValueKey('cal-day-2026-08-15')));
    await tester.pump();
    expect(find.text('Standup'), findsWidgets);
  });

  testWidgets('new editor save POSTs an event', (tester) async {
    final raw = CalendarHttp(calendars: [_calJson()]);
    final controller = await _controller(raw);
    await tester.pumpWidget(
      MaterialApp(
        home: CalendarEventScreen(
          controller: controller,
          client: _client(raw),
          day: DateTime(2026, 8, 15),
          calendars: [
            CalendarCal(href: 'cal-1', name: 'Personal', color: '#5b8abf'),
          ],
        ),
      ),
    );
    await tester.pump();
    await tester.enterText(find.byType(TextField).first, 'From phone');
    await tester.tap(find.text('Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(raw.calls, contains('POST /api/calendar/events'));
    expect(raw.lastBody!['summary'], 'From phone');
    expect(raw.lastBody!['all_day'], isFalse);
    expect(raw.lastBody!['dtstart'], contains('2026-08-15T09:00:00'));
  });
}

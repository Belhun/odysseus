import 'models.dart';
import 'ody_http.dart';

/// Web form `#cal-f-rrule` values (`static/js/calendar.js`).
const kRruleChoices = <({String value, String label})>[
  (value: '', label: 'Does not repeat'),
  (value: 'FREQ=DAILY', label: 'Daily'),
  (value: 'FREQ=WEEKLY', label: 'Weekly'),
  (value: 'FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR', label: 'Weekdays'),
  (value: 'FREQ=MONTHLY', label: 'Monthly'),
  (value: 'FREQ=YEARLY', label: 'Yearly'),
];

final _tzAware = RegExp(r'[Zz]$|[+\-]\d{2}:?\d{2}$');

String twoDigits(int n) => n.toString().padLeft(2, '0');

String ymd(DateTime d) =>
    '${d.year}-${twoDigits(d.month)}-${twoDigits(d.day)}';

/// Web `_localDateOf`: naive ISO keeps the written date; `Z` / offset bucket
/// by the device's local calendar day.
String localDateOf(String iso) {
  final raw = iso.trim();
  if (raw.isEmpty) return '';
  if (raw.length == 10) return raw;
  if (_tzAware.hasMatch(raw)) {
    final parsed = DateTime.tryParse(raw);
    if (parsed != null) return ymd(parsed.toLocal());
  }
  return raw.length >= 10 ? raw.substring(0, 10) : raw;
}

/// Timed create/update payload, matching web `_tzOffset()` stamps.
String stampLocalDateTime(DateTime dt) {
  final o = dt.timeZoneOffset;
  final abs = o.abs();
  final sign = o.isNegative ? '-' : '+';
  final off =
      '$sign${twoDigits(abs.inHours)}:${twoDigits(abs.inMinutes.remainder(60))}';
  return '${ymd(dt)}T${twoDigits(dt.hour)}:${twoDigits(dt.minute)}:00$off';
}

String stampAllDay(DateTime dt) => ymd(dt);

/// 6-week month grid. Default Monday start matches web (Sunday only if
/// `cal-week-start=sun` in localStorage).
List<DateTime> monthGrid(DateTime month, {int weekStart = DateTime.monday}) {
  final first = DateTime(month.year, month.month, 1);
  final dow = (first.weekday - weekStart) % 7;
  final gridStart = DateTime(first.year, first.month, first.day - dow);
  return [for (var i = 0; i < 42; i++) gridStart.add(Duration(days: i))];
}

/// Inclusive grid start, exclusive end — same window as web `_monthRange`.
(String start, String end) monthQueryRange(
  DateTime month, {
  int weekStart = DateTime.monday,
}) {
  final grid = monthGrid(month, weekStart: weekStart);
  return (ymd(grid.first), ymd(grid.first.add(const Duration(days: 42))));
}

/// Web `_eventsForDay` overlap rules.
bool eventOccursOn(CalendarEvent e, String dateStr) {
  if (e.allDay) {
    final start = localDateOf(e.dtstart);
    final end = localDateOf(e.dtend.isEmpty ? e.dtstart : e.dtend);
    if (start == end) return start == dateStr;
    return start.compareTo(dateStr) <= 0 && end.compareTo(dateStr) > 0;
  }
  final startDate = localDateOf(e.dtstart);
  final endDate = localDateOf(e.dtend.isEmpty ? e.dtstart : e.dtend);
  if (startDate != endDate) {
    return startDate.compareTo(dateStr) <= 0 &&
        endDate.compareTo(dateStr) >= 0;
  }
  return startDate == dateStr;
}

String formatEventWhen(CalendarEvent e) {
  if (e.allDay) return 'All day';
  final parsed = DateTime.tryParse(e.dtstart);
  if (parsed == null) return e.dtstart;
  final local = parsed.toLocal();
  return '${twoDigits(local.hour)}:${twoDigits(local.minute)}';
}

String calendarErrorMessage(Object error) {
  if (error is ApiException && error.statusCode == 403) {
    return 'This token needs calendar:read and calendar:write. Cookie login works. '
        'A phone_finance token is not enough.';
  }
  return '$error';
}

class CalendarCal {
  CalendarCal({
    required this.href,
    required this.name,
    required this.color,
    this.source = 'local',
  });

  final String href;
  final String name;
  final String color;
  final String source;

  factory CalendarCal.fromJson(Map<String, dynamic> json) {
    return CalendarCal(
      href: asString(json['href'] ?? json['id']),
      name: asString(json['name'], 'Calendar'),
      color: asString(json['color'], '#5b8abf'),
      source: asString(json['source'], 'local'),
    );
  }
}

class CalendarEvent {
  CalendarEvent({
    required this.uid,
    required this.summary,
    required this.dtstart,
    this.dtend = '',
    this.allDay = false,
    this.isUtc = false,
    this.description = '',
    this.location = '',
    this.rrule = '',
    this.calendar = '',
    this.calendarHref = '',
    this.color = '',
    this.isRecurrence = false,
    this.seriesUid = '',
  });

  final String uid;
  final String summary;
  final String dtstart;
  final String dtend;
  final bool allDay;
  final bool isUtc;
  final String description;
  final String location;
  final String rrule;
  final String calendar;
  final String calendarHref;
  final String color;
  final bool isRecurrence;
  final String seriesUid;

  bool get isOccurrence => uid.contains('::');

  String get seriesId {
    if (seriesUid.isNotEmpty) return seriesUid;
    final i = uid.indexOf('::');
    return i == -1 ? uid : uid.substring(0, i);
  }

  String get displayTitle => summary.trim().isEmpty ? '(no title)' : summary.trim();

  factory CalendarEvent.fromJson(Map<String, dynamic> json) {
    return CalendarEvent(
      uid: asString(json['uid'] ?? json['id']),
      summary: asString(json['summary'] ?? json['title']),
      dtstart: asString(json['dtstart']),
      dtend: asString(json['dtend']),
      allDay: asBool(json['all_day']),
      isUtc: asBool(json['is_utc']),
      description: asString(json['description']),
      location: asString(json['location']),
      rrule: asString(json['rrule']),
      calendar: asString(json['calendar']),
      calendarHref: asString(json['calendar_href']),
      color: asString(json['color']),
      isRecurrence: asBool(json['is_recurrence']),
      seriesUid: asString(json['series_uid']),
    );
  }
}

class CalendarClient {
  CalendarClient(this.httpClient);

  final OdyHttp httpClient;

  Future<List<CalendarCal>> listCalendars() async {
    final data = await httpClient.get('/api/calendar/calendars');
    final map = _asMap(data);
    return (map['calendars'] as List? ?? [])
        .whereType<Map>()
        .map((e) => CalendarCal.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<CalendarEvent>> listEvents({
    required String start,
    required String end,
    String? calendar,
  }) async {
    final data = await httpClient.get('/api/calendar/events', query: {
      'start': start,
      'end': end,
      if (calendar != null && calendar.isNotEmpty) 'calendar': calendar,
    });
    final map = _asMap(data);
    return (map['events'] as List? ?? [])
        .whereType<Map>()
        .map((e) => CalendarEvent.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<String> createEvent(Map<String, dynamic> body) async {
    final data = await httpClient.sendJson('POST', '/api/calendar/events', body: body);
    return asString(_asMap(data)['uid']);
  }

  Future<void> updateEvent(String uid, Map<String, dynamic> body) async {
    await httpClient.sendJson(
      'PUT',
      '/api/calendar/events/$uid',
      body: body,
    );
  }

  Future<void> deleteEvent(String uid, {String scope = 'series'}) async {
    await httpClient.sendJson(
      'DELETE',
      '/api/calendar/events/$uid',
      query: {if (scope != 'series') 'scope': scope},
    );
  }

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return <String, dynamic>{};
  }
}

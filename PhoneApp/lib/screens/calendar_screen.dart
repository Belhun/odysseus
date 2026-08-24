import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../api/calendar_client.dart';
import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'calendar_event_screen.dart';

class CalendarScreen extends StatefulWidget {
  const CalendarScreen({
    super.key,
    required this.controller,
    this.client,
    this.now,
  });

  final AppController controller;
  final CalendarClient? client;
  final DateTime? now;

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  late DateTime _month;
  late DateTime _selected;
  bool _loading = true;
  String? _error;
  String? _filterHref;
  List<CalendarCal> _calendars = [];
  List<CalendarEvent> _events = [];

  CalendarClient? get _api {
    if (widget.client != null) return widget.client;
    try {
      return CalendarClient(widget.controller.odyHttp);
    } catch (_) {
      return null;
    }
  }

  @override
  void initState() {
    super.initState();
    final now = widget.now ?? DateTime.now();
    _month = DateTime(now.year, now.month);
    _selected = DateTime(now.year, now.month, now.day);
    _load();
  }

  Future<void> _load() async {
    final api = _api;
    if (api == null) {
      setState(() {
        _loading = false;
        _error = 'Not connected.';
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final range = monthQueryRange(_month);
      final cals = await api.listCalendars();
      final events = await api.listEvents(
        start: range.$1,
        end: range.$2,
        calendar: _filterHref,
      );
      if (!mounted) return;
      setState(() {
        _calendars = cals;
        _events = events;
        _loading = false;
        if (_filterHref != null &&
            dropdownValueIn(_filterHref, cals.map((c) => c.href)) == null) {
          _filterHref = null;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = calendarErrorMessage(e);
        _loading = false;
      });
    }
  }

  void _shiftMonth(int delta) {
    setState(() {
      _month = DateTime(_month.year, _month.month + delta);
      final last = DateTime(_month.year, _month.month + 1, 0).day;
      final day = _selected.day.clamp(1, last);
      _selected = DateTime(_month.year, _month.month, day);
    });
    _load();
  }

  void _goToday() {
    final now = widget.now ?? DateTime.now();
    setState(() {
      _month = DateTime(now.year, now.month);
      _selected = DateTime(now.year, now.month, now.day);
    });
    _load();
  }

  List<CalendarEvent> _onDay(DateTime day) {
    final key = ymd(day);
    return _events.where((e) => eventOccursOn(e, key)).toList();
  }

  Future<void> _openEditor({CalendarEvent? event, DateTime? day}) async {
    final api = _api;
    if (api == null) return;
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CalendarEventScreen(
          controller: widget.controller,
          client: api,
          event: event,
          day: day ?? _selected,
          calendars: _calendars,
        ),
      ),
    );
    if (saved == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final title = DateFormat.yMMMM().format(_month);
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
            tooltip: 'Previous month',
            onPressed: () => _shiftMonth(-1),
            icon: const Icon(Icons.chevron_left),
          ),
          IconButton(
            tooltip: 'Today',
            onPressed: _goToday,
            icon: const Icon(Icons.today),
          ),
          IconButton(
            tooltip: 'Next month',
            onPressed: () => _shiftMonth(1),
            icon: const Icon(Icons.chevron_right),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        tooltip: 'New event',
        onPressed: () => _openEditor(day: _selected),
        child: const Icon(Icons.add),
      ),
      body: Column(
        children: [
          if (_calendars.length > 1)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: DropdownButtonFormField<String?>(
                value: dropdownValueIn(_filterHref, [
                  null,
                  ..._calendars.map((c) => c.href),
                ]),
                decoration: const InputDecoration(
                  labelText: 'Calendar',
                  isDense: true,
                ),
                items: [
                  const DropdownMenuItem(value: null, child: Text('All calendars')),
                  ..._calendars.map(
                    (c) => DropdownMenuItem(value: c.href, child: Text(c.name)),
                  ),
                ],
                onChanged: (v) {
                  setState(() => _filterHref = v);
                  _load();
                },
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
    final grid = monthGrid(_month);
    final dayEvents = _onDay(_selected);
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(8, 8, 8, 88),
        children: [
          Row(
            children: [
              for (final label in const ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
                Expanded(
                  child: Text(
                    label,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: OdyColors.subheader, fontSize: 12),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: grid.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 7,
              childAspectRatio: 0.92,
            ),
            itemBuilder: (context, i) => _cell(grid[i]),
          ),
          const SizedBox(height: 12),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Text(
              DateFormat('EEEE d MMMM').format(_selected),
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          if (dayEvents.isEmpty)
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'No events this day',
                style: TextStyle(color: OdyColors.muted),
              ),
            )
          else
            for (final e in dayEvents)
              ListTile(
                leading: Container(
                  width: 10,
                  height: 10,
                  margin: const EdgeInsets.only(top: 6),
                  decoration: BoxDecoration(
                    color: parseHexColor(e.color),
                    shape: BoxShape.circle,
                  ),
                ),
                title: Text(e.displayTitle),
                subtitle: Text(
                  [
                    formatEventWhen(e),
                    if (e.calendar.isNotEmpty) e.calendar,
                  ].join(' · '),
                ),
                onTap: () => _openEditor(event: e),
              ),
        ],
      ),
    );
  }

  Widget _cell(DateTime day) {
    final now = widget.now ?? DateTime.now();
    final inMonth = day.month == _month.month;
    final selected = ymd(day) == ymd(_selected);
    final today = ymd(day) == ymd(now);
    final colors = _onDay(day)
        .map((e) => e.color)
        .where((c) => c.isNotEmpty)
        .toSet()
        .take(3)
        .toList();
    return InkWell(
      key: ValueKey('cal-day-${ymd(day)}'),
      onTap: () => setState(() => _selected = day),
      child: Container(
        margin: const EdgeInsets.all(2),
        decoration: BoxDecoration(
          color: selected ? OdyColors.accent.withValues(alpha: 0.18) : null,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: today
                ? OdyColors.accent
                : selected
                    ? OdyColors.accent.withValues(alpha: 0.5)
                    : Colors.transparent,
          ),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              '${day.day}',
              style: TextStyle(
                color: inMonth ? null : OdyColors.muted,
                fontWeight: today ? FontWeight.w700 : FontWeight.w500,
              ),
            ),
            const SizedBox(height: 3),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (final c in colors)
                  Container(
                    width: 5,
                    height: 5,
                    margin: const EdgeInsets.symmetric(horizontal: 1),
                    decoration: BoxDecoration(
                      color: parseHexColor(c),
                      shape: BoxShape.circle,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

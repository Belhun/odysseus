import 'package:flutter/material.dart';

import '../api/calendar_client.dart';
import '../api/models.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';

class CalendarEventScreen extends StatefulWidget {
  const CalendarEventScreen({
    super.key,
    required this.controller,
    this.client,
    this.event,
    this.day,
    this.calendars = const [],
  });

  final AppController controller;
  final CalendarClient? client;
  final CalendarEvent? event;
  final DateTime? day;
  final List<CalendarCal> calendars;

  @override
  State<CalendarEventScreen> createState() => _CalendarEventScreenState();
}

class _CalendarEventScreenState extends State<CalendarEventScreen> {
  final _title = TextEditingController();
  final _notes = TextEditingController();
  final _location = TextEditingController();
  late DateTime _start;
  late DateTime _end;
  late bool _allDay;
  String _rrule = '';
  String? _calendarHref;
  List<CalendarCal> _calendars = [];
  bool _saving = false;
  bool _loadingCals = false;

  CalendarClient? get _api {
    if (widget.client != null) return widget.client;
    try {
      return CalendarClient(widget.controller.odyHttp);
    } catch (_) {
      return null;
    }
  }

  bool get _isNew => widget.event == null;

  @override
  void initState() {
    super.initState();
    final existing = widget.event;
    final day = widget.day ?? DateTime.now();
    _calendars = List.of(widget.calendars);
    if (existing != null) {
      _title.text = existing.summary;
      _notes.text = existing.description;
      _location.text = existing.location;
      _allDay = existing.allDay;
      _start = _parseStamp(existing.dtstart, fallback: day);
      _end = existing.dtend.isEmpty
          ? _start.add(const Duration(hours: 1))
          : _parseStamp(existing.dtend, fallback: _start.add(const Duration(hours: 1)));
      if (_allDay && ymd(_end) != ymd(_start) && _end.isAfter(_start)) {
        _end = _end.subtract(const Duration(days: 1));
      }
      _rrule = existing.rrule;
      _calendarHref = existing.calendarHref.isEmpty ? null : existing.calendarHref;
    } else {
      _allDay = false;
      _start = DateTime(day.year, day.month, day.day, 9);
      _end = DateTime(day.year, day.month, day.day, 10);
      _calendarHref = _calendars.isEmpty ? null : _calendars.first.href;
    }
    if (_calendars.isEmpty) {
      _loadCalendars();
    }
  }

  Future<void> _loadCalendars() async {
    final api = _api;
    if (api == null) return;
    setState(() => _loadingCals = true);
    try {
      final cals = await api.listCalendars();
      if (!mounted) return;
      setState(() {
        _calendars = cals;
        _calendarHref ??= cals.isEmpty ? null : cals.first.href;
        _loadingCals = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadingCals = false);
      await showBusyError(context, calendarErrorMessage(e));
    }
  }

  DateTime _parseStamp(String raw, {required DateTime fallback}) {
    if (raw.length == 10) {
      final d = DateTime.tryParse(raw);
      return d ?? fallback;
    }
    return DateTime.tryParse(raw)?.toLocal() ?? fallback;
  }

  @override
  void dispose() {
    _title.dispose();
    _notes.dispose();
    _location.dispose();
    super.dispose();
  }

  Future<void> _pickDate({required bool start}) async {
    final initial = start ? _start : _end;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2018),
      lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
    );
    if (picked == null) return;
    setState(() {
      if (start) {
        _start = DateTime(picked.year, picked.month, picked.day, _start.hour, _start.minute);
        if (_end.isBefore(_start)) {
          _end = _allDay ? _start : _start.add(const Duration(hours: 1));
        }
      } else {
        _end = DateTime(picked.year, picked.month, picked.day, _end.hour, _end.minute);
      }
    });
  }

  Future<void> _pickTime({required bool start}) async {
    final initial = TimeOfDay.fromDateTime(start ? _start : _end);
    final picked = await showTimePicker(context: context, initialTime: initial);
    if (picked == null) return;
    setState(() {
      if (start) {
        _start = DateTime(_start.year, _start.month, _start.day, picked.hour, picked.minute);
        if (!_end.isAfter(_start)) {
          _end = _start.add(const Duration(hours: 1));
        }
      } else {
        _end = DateTime(_end.year, _end.month, _end.day, picked.hour, picked.minute);
      }
    });
  }

  Map<String, dynamic> _body() {
    if (_allDay) {
      final endExclusive = DateTime(_end.year, _end.month, _end.day)
          .add(const Duration(days: 1));
      return {
        'summary': _title.text.trim(),
        'dtstart': stampAllDay(_start),
        'dtend': stampAllDay(endExclusive),
        'all_day': true,
        'description': _notes.text.trim(),
        'location': _location.text.trim(),
        'rrule': _rrule,
        if (_isNew && _calendarHref != null) 'calendar_href': _calendarHref,
      };
    }
    return {
      'summary': _title.text.trim(),
      'dtstart': stampLocalDateTime(_start),
      'dtend': stampLocalDateTime(_end),
      'all_day': false,
      'description': _notes.text.trim(),
      'location': _location.text.trim(),
      'rrule': _rrule,
      if (_isNew && _calendarHref != null) 'calendar_href': _calendarHref,
    };
  }

  Future<void> _save() async {
    final api = _api;
    if (api == null) {
      await showBusyError(context, 'Not connected.');
      return;
    }
    if (_title.text.trim().isEmpty) {
      await showBusyError(context, 'Title is required.');
      return;
    }
    if (!_allDay && !_end.isAfter(_start)) {
      await showBusyError(context, 'End must be after start.');
      return;
    }
    setState(() => _saving = true);
    try {
      final existing = widget.event;
      if (existing == null) {
        await api.createEvent(_body());
      } else {
        await api.updateEvent(existing.seriesId, _body());
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() => _saving = false);
      await showBusyError(context, calendarErrorMessage(e));
    }
  }

  Future<void> _delete() async {
    final api = _api;
    final existing = widget.event;
    if (api == null || existing == null) return;
    final occurrence = existing.isOccurrence;
    final choice = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete event'),
        content: Text(
          occurrence
              ? 'This is one day of a repeating series. Delete only this day, or the whole series?'
              : 'This removes the same event the web calendar uses.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          if (occurrence)
            TextButton(
              onPressed: () => Navigator.pop(ctx, 'occurrence'),
              child: const Text('This day'),
            ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, 'series'),
            child: Text(occurrence ? 'All events' : 'Delete'),
          ),
        ],
      ),
    );
    if (choice == null) return;
    try {
      await api.deleteEvent(
        choice == 'occurrence' ? existing.uid : existing.seriesId,
        scope: choice,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) await showBusyError(context, calendarErrorMessage(e));
    }
  }

  @override
  Widget build(BuildContext context) {
    final rruleValues = [
      ...kRruleChoices.map((c) => c.value),
      if (_rrule.isNotEmpty && kRruleChoices.every((c) => c.value != _rrule)) _rrule,
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(_isNew ? 'New event' : 'Edit event'),
        actions: [
          if (!_isNew)
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
          if (widget.event?.isOccurrence == true)
            const Padding(
              padding: EdgeInsets.only(bottom: 12),
              child: Text(
                'This is one day of a repeating series. Saving updates every day.',
                style: TextStyle(color: OdyColors.warn, fontSize: 13),
              ),
            ),
          TextField(
            controller: _title,
            decoration: const InputDecoration(labelText: 'Title'),
            textCapitalization: TextCapitalization.sentences,
          ),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('All day'),
            value: _allDay,
            onChanged: (v) => setState(() => _allDay = v),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Starts'),
            subtitle: Text(
              _allDay ? ymd(_start) : '${ymd(_start)} ${twoDigits(_start.hour)}:${twoDigits(_start.minute)}',
            ),
            trailing: const Icon(Icons.event),
            onTap: () => _pickDate(start: true),
          ),
          if (!_allDay)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Start time'),
              subtitle: Text('${twoDigits(_start.hour)}:${twoDigits(_start.minute)}'),
              trailing: const Icon(Icons.schedule),
              onTap: () => _pickTime(start: true),
            ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('Ends'),
            subtitle: Text(
              _allDay ? ymd(_end) : '${ymd(_end)} ${twoDigits(_end.hour)}:${twoDigits(_end.minute)}',
            ),
            trailing: const Icon(Icons.event),
            onTap: () => _pickDate(start: false),
          ),
          if (!_allDay)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('End time'),
              subtitle: Text('${twoDigits(_end.hour)}:${twoDigits(_end.minute)}'),
              trailing: const Icon(Icons.schedule),
              onTap: () => _pickTime(start: false),
            ),
          if (_loadingCals)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: LinearProgressIndicator(),
            )
          else if (_calendars.length > 1 && _isNew)
            DropdownButtonFormField<String>(
              value: dropdownValueIn(_calendarHref, _calendars.map((c) => c.href)) ??
                  _calendars.first.href,
              decoration: const InputDecoration(labelText: 'Calendar'),
              items: [
                for (final c in _calendars)
                  DropdownMenuItem(value: c.href, child: Text(c.name)),
              ],
              onChanged: (v) => setState(() => _calendarHref = v),
            )
          else if (!_isNew && widget.event!.calendar.isNotEmpty)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Calendar'),
              subtitle: Text(widget.event!.calendar),
            ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: dropdownValueIn(_rrule, rruleValues) ?? '',
            decoration: const InputDecoration(labelText: 'Repeat'),
            items: [
              for (final c in kRruleChoices)
                DropdownMenuItem(value: c.value, child: Text(c.label)),
              if (_rrule.isNotEmpty && kRruleChoices.every((c) => c.value != _rrule))
                DropdownMenuItem(value: _rrule, child: Text(_rrule)),
            ],
            onChanged: (v) => setState(() => _rrule = v ?? ''),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _location,
            decoration: const InputDecoration(labelText: 'Location'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _notes,
            decoration: const InputDecoration(labelText: 'Notes'),
            minLines: 3,
            maxLines: 6,
            textCapitalization: TextCapitalization.sentences,
          ),
        ],
      ),
    );
  }
}

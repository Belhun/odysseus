import 'package:flutter/foundation.dart';
import 'dart:developer' as developer;

/// In-app + console logger. `flutter run` often hides debugPrint among Android
/// IME noise; `print` and the Connect-screen log panel always keep a copy.
class OdyLog extends ChangeNotifier {
  OdyLog._();
  static final OdyLog instance = OdyLog._();

  final List<String> lines = <String>[];
  static const int maxLines = 120;

  void add(String message, {Object? error, StackTrace? stack}) {
    final ts = DateTime.now().toIso8601String().substring(11, 23);
    final line = '$ts $message';
    // print survives flutter run stdout better than debugPrint alone.
    // ignore: avoid_print
    print('[OdyPhone] $line');
    debugPrint('[OdyPhone] $line');
    developer.log(
      message,
      name: 'OdyPhone',
      error: error,
      stackTrace: stack,
    );
    lines.add(line);
    if (error != null) {
      final errLine = '$ts ERR $error';
      // ignore: avoid_print
      print('[OdyPhone] $errLine');
      lines.add(errLine);
    }
    if (stack != null) {
      for (final s in stack.toString().split('\n').take(12)) {
        if (s.trim().isEmpty) continue;
        lines.add('$ts   $s');
      }
    }
    while (lines.length > maxLines) {
      lines.removeAt(0);
    }
    notifyListeners();
  }

  void clear() {
    lines.clear();
    notifyListeners();
  }
}

void odyLog(String message, {Object? error, StackTrace? stack}) {
  OdyLog.instance.add(message, error: error, stack: stack);
}

String odyRedactSecret(String? value) {
  final v = value?.trim() ?? '';
  if (v.isEmpty) return '(empty)';
  if (v.length <= 6) return '(${v.length} chars)';
  return '${v.substring(0, 4)}…(${v.length} chars)';
}

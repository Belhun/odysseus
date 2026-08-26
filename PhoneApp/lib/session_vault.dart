import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Odysseus session cookie in platform secure storage.
class SessionVault {
  SessionVault._();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const _keySession = 'ody_session_cookie';

  static Future<String?> readSession(SharedPreferences prefs) async {
    if (kIsWeb) {
      return prefs.getString('sessionCookie');
    }
    try {
      final secure = await _storage.read(key: _keySession);
      if (secure != null && secure.isNotEmpty) {
        return secure;
      }
    } catch (_) {
      // Unit tests and some platforms lack secure storage.
    }
    final legacy = prefs.getString('sessionCookie');
    if (legacy != null && legacy.isNotEmpty) {
      await writeSession(prefs, legacy);
      await prefs.remove('sessionCookie');
    }
    return legacy;
  }

  static Future<void> writeSession(SharedPreferences prefs, String session) async {
    if (kIsWeb) {
      await prefs.setString('sessionCookie', session);
      return;
    }
    if (session.isEmpty) {
      try {
        await _storage.delete(key: _keySession);
      } catch (_) {}
      await prefs.remove('sessionCookie');
      return;
    }
    try {
      await _storage.write(key: _keySession, value: session);
    } catch (_) {}
    await prefs.remove('sessionCookie');
  }

  static Future<void> clearSession(SharedPreferences prefs) async {
    if (!kIsWeb) {
      try {
        await _storage.delete(key: _keySession);
      } catch (_) {}
    }
    await prefs.remove('sessionCookie');
  }
}

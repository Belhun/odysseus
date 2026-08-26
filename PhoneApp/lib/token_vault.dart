import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// API token in platform secure storage; URLs and usernames stay in prefs.
class TokenVault {
  TokenVault._();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const _keyToken = 'ody_api_token';

  static Future<String?> readToken(SharedPreferences prefs) async {
    if (kIsWeb) {
      return prefs.getString('token');
    }
    try {
      final secure = await _storage.read(key: _keyToken);
      if (secure != null && secure.isNotEmpty) {
        return secure;
      }
    } catch (_) {
      // Unit tests and some platforms lack secure storage.
    }
    final legacy = prefs.getString('token');
    if (legacy != null && legacy.isNotEmpty) {
      await writeToken(prefs, legacy);
      await prefs.remove('token');
    }
    return legacy;
  }

  static Future<void> writeToken(SharedPreferences prefs, String token) async {
    if (kIsWeb) {
      await prefs.setString('token', token);
      return;
    }
    if (token.isEmpty) {
      try {
        await _storage.delete(key: _keyToken);
      } catch (_) {}
      await prefs.remove('token');
      return;
    }
    try {
      await _storage.write(key: _keyToken, value: token);
    } catch (_) {}
    await prefs.remove('token');
  }

  static Future<void> clearToken(SharedPreferences prefs) async {
    if (!kIsWeb) {
      try {
        await _storage.delete(key: _keyToken);
      } catch (_) {}
    }
    await prefs.remove('token');
  }
}

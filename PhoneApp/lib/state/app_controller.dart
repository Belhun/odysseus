import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../api/finance_client.dart';
import '../api/models.dart';
import '../api/ody_http.dart';
import '../debug_log.dart';

class AppController extends ChangeNotifier {
  AppController({
    required this.prefs,
    http.Client? httpClient,
  }) : _rawClient = httpClient;

  final SharedPreferences prefs;
  final http.Client? _rawClient;

  String baseUrl = '';
  String token = '';
  String sessionCookie = '';
  String username = '';
  bool privacyMode = false;
  int themeIndex = 0; // 0 dark, 1 light, 2 system
  bool busy = false;
  String? lastError;
  bool needsTotp = false;

  FinanceClient? finance;
  List<FinanceAccount> cachedAccounts = [];
  BudgetSnapshot? cachedBudget;
  NetWorth? cachedNetWorth;
  List<RecurringSeries> cachedRecurring = [];
  bool homePrefetched = false;

  bool get isConnected => finance != null;

  Future<void> restore() async {
    baseUrl = prefs.getString('baseUrl') ?? '';
    token = prefs.getString('token') ?? '';
    sessionCookie = prefs.getString('sessionCookie') ?? '';
    username = prefs.getString('username') ?? '';
    privacyMode = prefs.getBool('privacyMode') ?? false;
    themeIndex = prefs.getInt('themeIndex') ?? 0;
    const bootUrl = String.fromEnvironment('ODY_URL');
    const bootToken = String.fromEnvironment('ODY_TOKEN');
    const bootUser = String.fromEnvironment('ODY_USER');
    if (bootUrl.isNotEmpty) baseUrl = bootUrl;
    if (bootToken.isNotEmpty) {
      token = bootToken;
      sessionCookie = '';
    }
    if (bootUser.isNotEmpty) username = bootUser;
    if (bootUrl.isNotEmpty || bootToken.isNotEmpty) {
      odyLog('bootstrap from dart-define url=$baseUrl token=${token.isNotEmpty} user=$username');
      await _persist();
    }
    if (baseUrl.isNotEmpty && (token.isNotEmpty || sessionCookie.isNotEmpty)) {
      _attachClient();
      try {
        cachedAccounts = await finance!.listAccounts();
        try {
          cachedBudget = await finance!.budgets(month: currentMonthKey());
        } catch (e) {
          odyLog('prefetch budget $e');
        }
        try {
          cachedNetWorth = await finance!.netWorth();
        } catch (e) {
          odyLog('prefetch networth $e');
        }
        try {
          cachedRecurring = await finance!.recurring();
        } catch (e) {
          odyLog('prefetch recurring $e');
        }
        homePrefetched = true;
      } catch (e) {
        odyLog('restore session failed $e');
        finance = null;
        homePrefetched = false;
      }
    }
    notifyListeners();
  }

  void _attachClient() {
    final httpLayer = OdyHttp(
      baseUrl: baseUrl,
      token: token.isEmpty ? null : token,
      sessionCookie: token.isEmpty ? sessionCookie : null,
      client: _rawClient,
    );
    finance = FinanceClient(httpLayer);
  }

  Future<bool> connect({
    required String url,
    String apiToken = '',
    String user = '',
    String password = '',
    String totp = '',
  }) async {
    busy = true;
    lastError = null;
    needsTotp = false;
    notifyListeners();
    try {
      baseUrl = normalizeBaseUrl(url);
      odyLog(
        'connect start url=$baseUrl mode=${apiToken.trim().isNotEmpty ? "token" : "password"} '
        'user=${user.trim().isEmpty ? "(empty)" : user.trim()} '
        'token=${odyRedactSecret(apiToken)} password=${password.isEmpty ? "no" : "yes"} '
        'totp=${totp.trim().isEmpty ? "no" : "yes"}',
      );
      if (apiToken.trim().isEmpty && password.isEmpty) {
        throw ApiException(
          400,
          'Paste an ody_ token, or switch to Password and enter username and password.',
        );
      }
      if (apiToken.trim().isNotEmpty) {
        token = apiToken.trim();
        sessionCookie = '';
        username = user.trim();
        _attachClient();
        try {
          await finance!.ping();
        } catch (e) {
          // Ping is companion-scoped; finance still works if the token has
          // finance scopes. Keep going unless finance itself fails.
          if (e is ApiException && e.statusCode == 401) rethrow;
        }
        await finance!.listAccounts();
      } else {
        token = '';
        final probe = FinanceClient(OdyHttp(baseUrl: baseUrl, client: _rawClient));
        final login = await probe.login(
          username: user.trim(),
          password: password,
          totp: totp,
        );
        if (login['requires_totp'] == true) {
          needsTotp = true;
          lastError = 'Enter the 2FA code from your authenticator.';
          finance = null;
          odyLog('connect requires TOTP');
          return false;
        }
        sessionCookie = '${login['_session'] ?? ''}';
        odyLog(
          'login json keys=${login.keys.where((k) => k != "_session").join(",")} '
          'session=${sessionCookie.isEmpty ? "missing" : "present"}',
        );
        if (sessionCookie.isEmpty) {
          throw ApiException(
            401,
            kIsWeb
                ? 'Login succeeded but no session cookie came back. Chrome/Flutter web cannot read HttpOnly cookies. Use an ody_ token.'
                : 'Login succeeded (200) but odysseus_session was missing. Hot restart this PhoneApp build so Android can read the cookie.',
          );
        }
        username = '${login['username'] ?? user.trim()}';
        _attachClient();
        await finance!.listAccounts();
      }
      await _persist();
      odyLog('connect ok accounts-loaded auth=${token.isNotEmpty ? "token" : "cookie"}');
      return true;
    } catch (e) {
      finance = null;
      lastError = _friendly(e);
      odyLog('connect fail friendly=$lastError', error: e, stack: StackTrace.current);
      return false;
    } finally {
      busy = false;
      notifyListeners();
    }
  }

  Future<void> disconnect() async {
    token = '';
    sessionCookie = '';
    finance = null;
    await prefs.remove('token');
    await prefs.remove('sessionCookie');
    notifyListeners();
  }

  Future<void> setPrivacy(bool value) async {
    privacyMode = value;
    await prefs.setBool('privacyMode', value);
    notifyListeners();
  }

  Future<void> setThemeIndex(int value) async {
    themeIndex = value;
    await prefs.setInt('themeIndex', value);
    notifyListeners();
  }

  Future<void> _persist() async {
    await prefs.setString('baseUrl', baseUrl);
    await prefs.setString('token', token);
    await prefs.setString('sessionCookie', sessionCookie);
    await prefs.setString('username', username);
  }

  static String _friendly(Object e) {
    final text = '$e';
    if (text.contains('HandshakeException') || text.contains('CERTIFICATE_VERIFY_FAILED')) {
      return 'TLS failed. Use https://dell-mini-pc.tailcbcc46.ts.net and stay on Tailscale.';
    }
    if (text.contains('Failed host lookup') ||
        text.contains('Name not resolved') ||
        text.contains('unknown host')) {
      return 'Private DNS blocked Tailscale MagicDNS. This build should connect via 100.79.4.36 instead. Tap Connect again after the app restarts.';
    }
    if (text.contains('SocketException') ||
        text.contains('Connection refused') ||
        text.contains('Connection timed out')) {
      return 'Could not reach the Mini PC on Tailscale. Keep Tailscale on. Do not add :7000 to the HTTPS URL.';
    }
    if (text.contains('XMLHttpRequest') || text.contains('Failed to fetch')) {
      return 'Could not reach the server from this browser (CORS or network). On Pixel this is a reachability/URL problem, not a password problem.';
    }
    return text;
  }
}

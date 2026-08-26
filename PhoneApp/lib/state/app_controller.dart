import 'dart:convert';



import 'package:flutter/foundation.dart';

import 'package:http/http.dart' as http_pkg;

import 'package:shared_preferences/shared_preferences.dart';



import '../api/auth_client.dart';

import '../api/finance_client.dart';

import '../api/models.dart';

import '../api/ody_http.dart';

import '../debug_log.dart';

import '../security/biometric_lock.dart';

import '../security/setup_logic.dart';

import '../session_vault.dart';

import '../setup_link.dart';

import '../token_vault.dart';



class AppController extends ChangeNotifier {

  AppController({

    required this.prefs,

    http_pkg.Client? httpClient,

    BiometricLockService? biometricLock,

  })  : _rawClient = httpClient,

        _biometricLock = biometricLock ?? BiometricLockService();



  final SharedPreferences prefs;

  final http_pkg.Client? _rawClient;

  final BiometricLockService _biometricLock;



  String baseUrl = '';

  String token = '';

  String sessionCookie = '';

  String username = '';

  bool privacyMode = false;

  int themeIndex = 0; // 0 dark, 1 light, 2 system

  bool setupComplete = false;

  bool biometricLockEnabled = false;

  bool pendingBiometricPrompt = false;

  bool isUnlocked = false;

  bool busy = false;

  String? lastError;

  bool needsTotp = false;



  FinanceClient? finance;

  OdyHttp? httpLayer;



  OdyHttp get odyHttp {

    final layer = httpLayer ?? finance?.httpClient;

    if (layer == null) {

      throw StateError('Not connected');

    }

    return layer;

  }



  List<FinanceAccount> cachedAccounts = [];

  BudgetSnapshot? cachedBudget;

  NetWorth? cachedNetWorth;

  List<RecurringSeries> cachedRecurring = [];

  bool homePrefetched = false;



  bool get isConnected => finance != null;



  bool get needsAppLock => setupComplete && biometricLockEnabled && !kIsWeb && !isUnlocked;

  bool get needsBiometricLock => needsAppLock;



  Future<bool> get biometricAvailable => _biometricLock.isAvailable;



  Future<void> restore() async {

    baseUrl = prefs.getString('baseUrl') ?? '';

    token = (await TokenVault.readToken(prefs)) ?? '';

    sessionCookie = (await SessionVault.readSession(prefs)) ?? '';

    username = prefs.getString('username') ?? '';

    privacyMode = prefs.getBool('privacyMode') ?? false;

    themeIndex = prefs.getInt('themeIndex') ?? 0;

    setupComplete = prefs.getBool('setupComplete') ?? false;

    biometricLockEnabled = prefs.getBool('biometricLockEnabled') ?? false;



    const bootUrl = String.fromEnvironment('ODY_URL');

    const bootToken = String.fromEnvironment('ODY_TOKEN');

    const bootUser = String.fromEnvironment('ODY_USER');

    if (bootUrl.isNotEmpty) baseUrl = bootUrl;

    if (bootToken.isNotEmpty) token = bootToken;

    if (bootUser.isNotEmpty) username = bootUser;

    if (bootUrl.isNotEmpty || bootToken.isNotEmpty) {

      odyLog('bootstrap from dart-define url=$baseUrl token=${token.isNotEmpty} user=$username');

      await _persistProfile();

    }



    if (setupComplete) {
      if (biometricLockEnabled && !kIsWeb) {
        isUnlocked = false;
        finance = null;
        httpLayer = null;
        homePrefetched = false;
      } else {
        isUnlocked = true;
        if (baseUrl.isNotEmpty && (token.isNotEmpty || sessionCookie.isNotEmpty)) {
          await _tryRestoreSession();
        }
      }
    } else if (baseUrl.isNotEmpty && (token.isNotEmpty || sessionCookie.isNotEmpty)) {

      await _tryRestoreSession();

    } else {

      isUnlocked = true;

    }

    notifyListeners();

  }



  Future<void> _tryRestoreSession() async {

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

      httpLayer = null;

      homePrefetched = false;

    }

  }



  void lock() {
    if (!setupComplete || !biometricLockEnabled || kIsWeb || !isUnlocked) return;
    finance = null;
    httpLayer = null;
    isUnlocked = false;
    notifyListeners();
  }



  Future<bool> unlockWithBiometric() async {

    lastError = null;

    busy = true;

    notifyListeners();

    try {

      final ok = await _biometricLock.unlock(biometricOnly: false);

      if (!ok) {

        lastError = 'Biometric unlock failed or was cancelled.';

        return false;

      }

      _attachClient();

      await finance!.listAccounts();

      isUnlocked = true;

      return true;

    } catch (e) {

      finance = null;

      httpLayer = null;

      lastError = _friendly(e);

      return false;

    } finally {

      busy = false;

      notifyListeners();

    }

  }



  Future<bool> unlockWithPassword({

    required String password,

    String totp = '',

  }) async {

    busy = true;

    lastError = null;

    needsTotp = false;

    notifyListeners();

    try {

      await _loginWithPassword(password: password, totp: totp);

      isUnlocked = true;

      return true;

    } catch (e) {

      finance = null;

      httpLayer = null;

      lastError = _friendly(e);

      return false;

    } finally {

      busy = false;

      notifyListeners();

    }

  }



  Future<bool> completeSetup({

    required String url,

    required String user,

    required String password,

    required String apiToken,

    String totp = '',

  }) async {

    busy = true;

    lastError = null;

    needsTotp = false;

    notifyListeners();

    try {

      final validation = SetupLogic.validate(

        url: url,

        username: user,

        password: password,

        token: apiToken,

      );

      if (validation != null) {

        throw ApiException(400, validation);

      }

      baseUrl = normalizeBaseUrl(url);

      username = user.trim();

      token = apiToken.trim();

      odyLog('completeSetup start url=$baseUrl user=$username token=${odyRedactSecret(token)}');



      await _loginWithPassword(password: password, totp: totp);

      await _validateToken();



      setupComplete = true;

      biometricLockEnabled = false;

      pendingBiometricPrompt = !kIsWeb;

      isUnlocked = true;

      await _persist();

      odyLog('completeSetup ok pendingBiometricPrompt=$pendingBiometricPrompt');

      return true;

    } catch (e) {

      finance = null;

      httpLayer = null;

      sessionCookie = '';

      lastError = _friendly(e);

      odyLog('completeSetup fail friendly=$lastError', error: e, stack: StackTrace.current);

      return false;

    } finally {

      busy = false;

      notifyListeners();

    }

  }



  Future<void> acceptBiometricLock() async {

    if (kIsWeb) {

      dismissBiometricPrompt();

      return;

    }

    final available = await _biometricLock.isAvailable;

    if (!available) {

      lastError = 'No biometrics enrolled on this device.';

      dismissBiometricPrompt();

      notifyListeners();

      return;

    }

    biometricLockEnabled = true;

    pendingBiometricPrompt = false;

    await prefs.setBool('biometricLockEnabled', true);

    notifyListeners();

  }



  void declineBiometricLock() {

    biometricLockEnabled = false;

    pendingBiometricPrompt = false;

    prefs.setBool('biometricLockEnabled', false);

    notifyListeners();

  }



  void dismissBiometricPrompt() {

    pendingBiometricPrompt = false;

    notifyListeners();

  }



  Future<bool> enableBiometricLock({required String password}) async {

    if (kIsWeb) {

      lastError = 'Biometric unlock is not available on web.';

      notifyListeners();

      return false;

    }

    busy = true;

    lastError = null;

    notifyListeners();

    try {

      final available = await _biometricLock.isAvailable;

      if (!available) {

        throw ApiException(400, 'No biometrics enrolled. Add fingerprint or face in Android settings.');

      }

      await _loginWithPassword(password: password);

      final ok = await _biometricLock.unlock(biometricOnly: false);

      if (!ok) {

        throw ApiException(400, 'Biometric check failed. Try again.');

      }

      biometricLockEnabled = true;

      await prefs.setBool('biometricLockEnabled', true);

      return true;

    } catch (e) {

      lastError = _friendly(e);

      return false;

    } finally {

      busy = false;

      notifyListeners();

    }

  }



  Future<void> setBiometricLockEnabled(bool value) async {
    if (value) return;
    biometricLockEnabled = false;
    isUnlocked = true;
    await prefs.setBool('biometricLockEnabled', false);
    if (setupComplete &&
        finance == null &&
        baseUrl.isNotEmpty &&
        (token.isNotEmpty || sessionCookie.isNotEmpty)) {
      await _tryRestoreSession();
    }
    notifyListeners();
  }



  Future<void> _loginWithPassword({

    required String password,

    String totp = '',

  }) async {

    sessionCookie = '';

    final probe = FinanceClient(OdyHttp(baseUrl: baseUrl, client: _rawClient));

    final login = await probe.login(

      username: username.trim(),

      password: password,

      totp: totp,

    );

    if (login['requires_totp'] == true) {

      needsTotp = true;

      throw ApiException(401, 'Enter the 2FA code from your authenticator.');

    }

    sessionCookie = '${login['_session'] ?? ''}';

    if (sessionCookie.isEmpty) {

      throw ApiException(

        401,

        kIsWeb

            ? 'Login succeeded but no session cookie came back. Use native Android for password login.'

            : 'Login succeeded but odysseus_session was missing. Hot restart this PhoneApp build.',

      );

    }

    username = '${login['username'] ?? username.trim()}';

    _attachClient();

    await finance!.listAccounts();

    await _persistProfile();

    await SessionVault.writeSession(prefs, sessionCookie);

  }



  Future<void> _validateToken() async {

    final tokenProbe = OdyHttp(baseUrl: baseUrl, token: token, client: _rawClient);

    final auth = await AuthClient(tokenProbe).fetch();

    if (!auth.hasFinance) {

      throw ApiException(

        403,

        'Token is missing finance scope. Mint a Phone app token with finance read/write.',

      );

    }

  }



  void _attachClient() {

    final layer = OdyHttp(

      baseUrl: baseUrl,

      token: token.isEmpty ? null : token,

      sessionCookie: token.isEmpty ? sessionCookie : null,

      client: _rawClient,

    );

    httpLayer = layer;

    finance = FinanceClient(layer);

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

          if (e is ApiException && e.statusCode == 401) rethrow;

        }

        await finance!.listAccounts();

      } else {

        token = '';

        username = user.trim();

        await _loginWithPassword(password: password, totp: totp);

      }

      await _persist();

      odyLog('connect ok accounts-loaded auth=${token.isNotEmpty ? "token" : "cookie"}');

      return true;

    } catch (e) {

      finance = null;

      httpLayer = null;

      lastError = _friendly(e);

      odyLog('connect fail friendly=$lastError', error: e, stack: StackTrace.current);

      return false;

    } finally {

      busy = false;

      notifyListeners();

    }

  }



  /// Clears session and returns to setup. Keeps server URL, username, and token.
  Future<void> logout() async {
    sessionCookie = '';
    finance = null;
    httpLayer = null;
    setupComplete = false;
    biometricLockEnabled = false;
    pendingBiometricPrompt = false;
    isUnlocked = true;
    homePrefetched = false;
    await SessionVault.clearSession(prefs);
    await prefs.setBool('setupComplete', false);
    await prefs.setBool('biometricLockEnabled', false);
    notifyListeners();
  }

  @Deprecated('Use logout()')
  Future<void> disconnect() => logout();



  Future<void> clearSavedToken() async {

    token = '';

    sessionCookie = '';

    finance = null;

    httpLayer = null;

    setupComplete = false;

    biometricLockEnabled = false;

    pendingBiometricPrompt = false;

    isUnlocked = true;

    await TokenVault.clearToken(prefs);

    await SessionVault.clearSession(prefs);

    await prefs.setBool('setupComplete', false);

    await prefs.setBool('biometricLockEnabled', false);

    notifyListeners();

  }



  Future<bool> applySetupLink(String raw) async {

    final link = PhoneAppSetupLink.tryParse(raw);

    if (link == null) {

      odyLog('setup link ignored');

      return false;

    }

    if (link.setupCode.isNotEmpty) {

      try {

        final payload = await _exchangeSetupCode(link.url, link.setupCode);

        baseUrl = normalizeBaseUrl('${payload['url'] ?? link.url}');

        token = '${payload['token'] ?? ''}';

        username = '${payload['user'] ?? link.user}';

        await _persistProfile();

        notifyListeners();

        return true;

      } catch (e) {

        lastError = _friendly(e);

        notifyListeners();

        return false;

      }

    }

    baseUrl = normalizeBaseUrl(link.url);

    token = link.token;

    username = link.user;

    await _persistProfile();

    notifyListeners();

    return true;

  }



  Future<Map<String, dynamic>> _exchangeSetupCode(String url, String code) async {

    final base = normalizeBaseUrl(url);

    final uri = Uri.parse('$base/api/phoneapp/exchange-setup');

    final client = _rawClient ?? http_pkg.Client();

    final ownsClient = _rawClient == null;

    try {

      final res = await client.post(

        uri,

        headers: const {'Content-Type': 'application/json'},

        body: jsonEncode({'code': code}),

      );

      final body = jsonDecode(res.body);

      if (res.statusCode != 200 || body is! Map || body['ok'] != true) {

        final err = body is Map ? '${body['error'] ?? res.body}' : res.body;

        throw ApiException(res.statusCode, err);

      }

      return Map<String, dynamic>.from(body);

    } finally {

      if (ownsClient) client.close();

    }

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



  Future<void> _persistProfile() async {

    await prefs.setString('baseUrl', baseUrl);

    await TokenVault.writeToken(prefs, token);

    await prefs.setString('username', username);

  }



  Future<void> _persist() async {

    await _persistProfile();

    await SessionVault.writeSession(prefs, sessionCookie);

    await prefs.setBool('setupComplete', setupComplete);

    await prefs.setBool('biometricLockEnabled', biometricLockEnabled);

  }



  static String _friendly(Object e) {

    final text = '$e';

    if (text.contains('HandshakeException') || text.contains('CERTIFICATE_VERIFY_FAILED')) {
      return 'TLS failed. Use your Odysseus https URL on Tailscale and keep Tailscale connected.';
    }

    if (text.contains('Failed host lookup') ||

        text.contains('Name not resolved') ||

        text.contains('unknown host')) {
      return 'Private DNS may block MagicDNS. Rebuild with ODY_MAGICDNS_HOST and ODY_TAILSCALE_IP dart-defines.';
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



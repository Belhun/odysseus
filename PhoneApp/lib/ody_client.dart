import 'connect_logic.dart';
import 'ody_http_factory.dart';
import 'ody_session.dart';

class FinanceConnectResult {
  FinanceConnectResult({
    required this.serverUrl,
    required this.mode,
    this.apiToken,
    this.sessionCookie,
    this.usernameLabel,
    this.accounts = const [],
  });

  final String serverUrl;
  final String mode;
  final String? apiToken;
  final String? sessionCookie;
  final String? usernameLabel;
  final List<dynamic> accounts;
}

class OdyClient {
  OdyClient({OdySession? session}) : _session = session ?? createOdySession();

  final OdySession _session;

  /// Token tab. Never POSTs /api/auth/login. Empty token is rejected before
  /// any network call so we do not send a fake password login.
  Future<FinanceConnectResult> connectWithToken({
    required String serverUrl,
    required String token,
    String? usernameLabel,
  }) async {
    final urlError = ConnectLogic.validateServerUrl(serverUrl);
    if (urlError != null) {
      throw OdyClientException(urlError);
    }
    final tokenError = ConnectLogic.validateToken(token);
    if (tokenError != null) {
      throw OdyClientException(tokenError);
    }
    final trimmed = token.trim();
    final accounts = await _getAccounts(
      serverUrl: serverUrl,
      headers: {'Authorization': 'Bearer $trimmed'},
    );
    return FinanceConnectResult(
      serverUrl: serverUrl.trim(),
      mode: 'token',
      apiToken: trimmed,
      usernameLabel: (usernameLabel ?? '').trim().isEmpty
          ? null
          : usernameLabel!.trim(),
      accounts: accounts,
    );
  }

  /// Password tab. POST /api/auth/login only. Do not use /api/login.
  Future<FinanceConnectResult> loginWithPassword({
    required String serverUrl,
    required String username,
    required String password,
    String? totp,
    bool remember = true,
  }) async {
    final urlError = ConnectLogic.validateServerUrl(serverUrl);
    if (urlError != null) {
      throw OdyClientException(urlError);
    }
    if (username.trim().isEmpty || password.isEmpty) {
      throw OdyClientException('Username and password are required');
    }
    final loginUri = ConnectLogic.resolve(serverUrl, ConnectLogic.loginPath);
    final response = await _session.send(
      uri: loginUri,
      method: 'POST',
      jsonBody: ConnectLogic.loginBody(
        username: username,
        password: password,
        remember: remember,
        totp: totp,
      ),
      captureSessionCookie: true,
    );
    if (response.statusCode != 200) {
      throw OdyClientException(
        _detail(response) ?? 'Login failed (${response.statusCode})',
        statusCode: response.statusCode,
      );
    }
    final payload = response.json;
    if (payload is Map && payload['requires_totp'] == true) {
      throw OdyClientException('Enter your TOTP code', statusCode: 200);
    }
    if (response.sessionCookie == null || response.sessionCookie!.isEmpty) {
      throw OdyClientException(
        'Login succeeded but the session cookie was not visible. '
        'On Flutter web, HttpOnly + SameSite cookies usually block this; '
        'use the API token tab.',
      );
    }
    final accounts = await _getAccounts(
      serverUrl: serverUrl,
      headers: {'Cookie': '${ConnectLogic.sessionCookieName}=${response.sessionCookie}'},
    );
    return FinanceConnectResult(
      serverUrl: serverUrl.trim(),
      mode: 'password',
      sessionCookie: response.sessionCookie,
      usernameLabel: username.trim(),
      accounts: accounts,
    );
  }

  Future<List<dynamic>> _getAccounts({
    required String serverUrl,
    required Map<String, String> headers,
  }) async {
    final uri = ConnectLogic.resolve(serverUrl, ConnectLogic.financeAccountsPath);
    final response = await _session.send(
      uri: uri,
      method: 'GET',
      headers: headers,
    );
    if (response.statusCode != 200) {
      throw OdyClientException(
        _detail(response) ?? 'Finance accounts failed (${response.statusCode})',
        statusCode: response.statusCode,
      );
    }
    final payload = response.json;
    if (payload is Map && payload['accounts'] is List) {
      return List<dynamic>.from(payload['accounts'] as List);
    }
    return const [];
  }

  String? _detail(OdyResponse response) {
    final payload = response.json;
    if (payload is Map) {
      final detail = payload['detail'] ?? payload['error'];
      if (detail != null) {
        return detail.toString();
      }
    }
    return response.body.isEmpty ? null : response.body;
  }

  void close() => _session.close();
}

class OdyClientException implements Exception {
  OdyClientException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

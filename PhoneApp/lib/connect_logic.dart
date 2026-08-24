/// Pure Connect-screen rules. No Flutter, so unit tests stay cheap.
class ConnectLogic {
  static const loginPath = '/api/auth/login';
  static const wrongLoginPath = '/api/login';
  static const financeAccountsPath = '/api/finance/accounts';
  static const companionPingPath = '/api/companion/ping';
  static const sessionCookieName = 'odysseus_session';

  /// Token tab: empty input must not fall through to a password login.
  static String? validateToken(String raw) {
    final token = raw.trim();
    if (token.isEmpty) {
      return 'Paste an ody_ API token';
    }
    if (!token.startsWith('ody_')) {
      return 'Token must start with ody_';
    }
    return null;
  }

  static String? validateServerUrl(String raw) {
    final url = raw.trim();
    if (url.isEmpty) {
      return 'Server URL is required';
    }
    final uri = Uri.tryParse(url);
    if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
      return 'Server URL must include a scheme, e.g. http://127.0.0.1:7000';
    }
    return null;
  }

  static Uri resolve(String serverUrl, String path) {
    var base = serverUrl.trim();
    if (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    return Uri.parse('$base$path');
  }

  static Map<String, dynamic> loginBody({
    required String username,
    required String password,
    bool remember = true,
    String? totp,
  }) {
    final body = <String, dynamic>{
      'username': username.trim(),
      'password': password,
      'remember': remember,
    };
    final code = totp?.trim() ?? '';
    if (code.isNotEmpty) {
      body['totp_code'] = code;
    }
    return body;
  }
}

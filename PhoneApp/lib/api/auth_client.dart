import 'ody_http.dart';

class AuthInfo {
  const AuthInfo({
    required this.auth,
    this.owner,
    this.scopes = const [],
    this.features = const {},
  });

  final String auth;
  final String? owner;
  final List<String> scopes;
  final Map<String, bool> features;

  bool get isToken => auth == 'token';
  bool get isSession => auth == 'session';
  bool get hasChat => features['chat'] == true;
  bool get hasFinance => features['finance'] == true;

  factory AuthInfo.fromJson(Map<String, dynamic> json) {
    final rawScopes = json['scopes'];
    final rawFeatures = json['features'];
    return AuthInfo(
      auth: '${json['auth'] ?? ''}',
      owner: json['owner']?.toString(),
      scopes: rawScopes is List
          ? rawScopes.map((s) => '$s').where((s) => s.isNotEmpty).toList()
          : const [],
      features: rawFeatures is Map
          ? rawFeatures.map((k, v) => MapEntry('$k', v == true))
          : const {},
    );
  }
}

class AuthClient {
  AuthClient(this.httpClient);

  final OdyHttp httpClient;

  Future<AuthInfo> fetch() async {
    final raw = await httpClient.get('/api/mobile/auth');
    if (raw is! Map) {
      throw ApiException(500, 'Unexpected auth response');
    }
    return AuthInfo.fromJson(Map<String, dynamic>.from(raw));
  }
}

/// User-facing labels for PhoneApp feature flags returned by /api/mobile/auth.
const phoneFeatureLabels = <String, String>{
  'chat': 'Chat',
  'finance': 'Finance',
  'notes': 'Notes',
  'calendar': 'Calendar',
  'email': 'Email',
  'todos': 'Todos',
  'documents': 'Documents',
  'memory': 'Memory',
  'cookbook': 'Cookbook',
};

String tokenPrefixLabel(String token) {
  final trimmed = token.trim();
  if (!trimmed.startsWith('ody_')) return '';
  return trimmed.length <= 12 ? trimmed : '${trimmed.substring(0, 12)}...';
}

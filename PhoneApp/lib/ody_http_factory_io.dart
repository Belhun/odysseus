import 'dart:convert';
import 'dart:io';

import 'connect_logic.dart';
import 'deploy_config.dart';
import 'ody_session.dart';

Map<String, String> get magicDnsIpOverrides => DeployConfig.magicDnsIpOverrides;

OdySession createOdySession() => _IoOdySession();

HttpClient createOdyHttpClient() {
  final client = HttpClient();
  client.userAgent = 'Odysseus-PhoneApp';
  client.badCertificateCallback = (X509Certificate cert, String host, int port) {
    for (final entry in magicDnsIpOverrides.entries) {
      if (host != entry.key && host != entry.value) continue;
      if (cert.subject.contains(entry.key)) return true;
    }
    return false;
  };
  return client;
}

class _IoOdySession implements OdySession {
  _IoOdySession() : _client = createOdyHttpClient();
  final HttpClient _client;
  String? _sessionCookie;

  @override
  Future<OdyResponse> send({
    required Uri uri,
    required String method,
    Map<String, String>? headers,
    Object? jsonBody,
    bool captureSessionCookie = false,
  }) async {
    final originalHost = uri.host;
    final override = magicDnsIpOverrides[originalHost];
    final connectUri = override == null ? uri : uri.replace(host: override);
    final request = await _open(method, connectUri);
    if (override != null) {
      final hostHeader = uri.hasPort ? '$originalHost:${uri.port}' : originalHost;
      request.headers.set(HttpHeaders.hostHeader, hostHeader);
    }
    headers?.forEach(request.headers.set);
    if (_sessionCookie != null &&
        (headers == null || !headers.keys.any((k) => k.toLowerCase() == 'cookie'))) {
      request.cookies.add(Cookie(ConnectLogic.sessionCookieName, _sessionCookie!));
    }
    if (jsonBody != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(jsonBody));
    }
    final response = await request.close();
    final body = await response.transform(utf8.decoder).join();
    String? captured;
    for (final cookie in response.cookies) {
      if (cookie.name == ConnectLogic.sessionCookieName) {
        captured = cookie.value;
        _sessionCookie = cookie.value;
      }
    }
    return OdyResponse(
      statusCode: response.statusCode,
      body: body,
      sessionCookie: captureSessionCookie ? captured : _sessionCookie,
    );
  }

  Future<HttpClientRequest> _open(String method, Uri uri) {
    switch (method.toUpperCase()) {
      case 'GET':
        return _client.getUrl(uri);
      case 'POST':
        return _client.postUrl(uri);
      case 'PUT':
        return _client.putUrl(uri);
      case 'PATCH':
        return _client.patchUrl(uri);
      case 'DELETE':
        return _client.deleteUrl(uri);
      default:
        throw ArgumentError('Unsupported method $method');
    }
  }

  @override
  void close() => _client.close(force: true);
}

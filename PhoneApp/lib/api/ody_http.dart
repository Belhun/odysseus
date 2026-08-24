import 'dart:convert';

import 'package:http/http.dart' as http;

import '../debug_log.dart';
import 'ody_http_factory_stub.dart'
    if (dart.library.io) 'ody_http_factory_io.dart' as ody_factory;
import 'session_post_stub.dart'
    if (dart.library.io) 'session_post_io.dart' as session_post;

class ApiException implements Exception {
  ApiException(this.statusCode, this.message, {this.body});

  final int statusCode;
  final String message;
  final String? body;

  @override
  String toString() => message;
}

/// One HTTP client for the Odysseus server. Token or session cookie, never both
/// as competing identities: token wins when present.
class OdyHttp {
  OdyHttp({
    required this.baseUrl,
    this.token,
    this.sessionCookie,
    http.Client? client,
  }) : _client = client ?? ody_factory.createOdyClient();

  final String baseUrl;
  final String? token;
  final String? sessionCookie;
  final http.Client _client;

  Map<String, String> get _headers {
    final h = <String, String>{
      'Accept': 'application/json',
      'X-Requested-With': 'OdysseusPhone',
    };
    final tok = token?.trim();
    if (tok != null && tok.isNotEmpty) {
      final value = tok.startsWith('ody_') ? tok : tok;
      h['Authorization'] = value.startsWith('Bearer ') ? value : 'Bearer $value';
    } else {
      final cookie = sessionCookie?.trim();
      if (cookie != null && cookie.isNotEmpty) {
        h['Cookie'] = cookie.contains('=') ? cookie : 'odysseus_session=$cookie';
      }
    }
    return h;
  }

  Uri uri(String path, [Map<String, String>? query]) {
    final normalized = path.startsWith('/') ? path : '/$path';
    return Uri.parse('$baseUrl$normalized').replace(
      queryParameters: query == null || query.isEmpty ? null : query,
    );
  }

  Future<dynamic> get(String path, {Map<String, String>? query}) async {
    final url = uri(path, query);
    odyLog('GET $url auth=${_authMode()}');
    final res = await _client.get(url, headers: _headers);
    odyLog('GET $path -> ${res.statusCode} ${res.reasonPhrase} bytes=${res.body.length}');
    return parseResponse(res);
  }

  Future<dynamic> sendJson(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
  }) async {
    final headers = {..._headers, 'Content-Type': 'application/json'};
    final encoded = body == null ? null : jsonEncode(body);
    late http.Response res;
    final url = uri(path, query);
    odyLog('$method $url auth=${_authMode()}');
    switch (method) {
      case 'POST':
        res = await _client.post(url, headers: headers, body: encoded);
      case 'PUT':
        res = await _client.put(url, headers: headers, body: encoded);
      case 'PATCH':
        res = await _client.patch(url, headers: headers, body: encoded);
      case 'DELETE':
        res = await _client.delete(url, headers: headers, body: encoded);
      default:
        throw ArgumentError('Unsupported method $method');
    }
    odyLog('$method $path -> ${res.statusCode} ${res.reasonPhrase} bytes=${res.body.length}');
    return parseResponse(res);
  }

  Future<http.Response> postRaw(String path, {Object? body}) async {
    final url = uri(path);
    odyLog('POST-RAW $url auth=${_authMode()} (password/token not logged)');
    final res = await session_post.postJsonCapturingCookies(
      uri: url,
      headers: {..._headers, 'Content-Type': 'application/json'},
      body: body,
      client: _client,
    );
    final cookieNames = res.headers.entries
        .where((e) => e.key.toLowerCase() == 'set-cookie')
        .map((e) => e.value.split('=').first)
        .join(',');
    odyLog(
      'POST-RAW $path -> ${res.statusCode} bytes=${res.body.length} set-cookie-names=$cookieNames',
    );
    return res;
  }

  Future<http.StreamedResponse> sendMultipart(
    http.MultipartRequest request,
  ) async {
    request.headers.addAll(_headers);
    return _client.send(request);
  }

  dynamic parseResponse(http.Response res) {
    if (res.statusCode == 204) return null;
    final text = res.body;
    dynamic decoded;
    if (text.isNotEmpty) {
      try {
        decoded = jsonDecode(text);
      } catch (_) {
        decoded = text;
      }
    }
    if (res.statusCode >= 400) {
      odyLog('HTTP error ${res.statusCode} body=${_clip(text)}');
      throw ApiException(
        res.statusCode,
        _messageFor(res.statusCode, decoded, text),
        body: text,
      );
    }
    return decoded;
  }

  String _authMode() {
    final tok = token?.trim() ?? '';
    if (tok.isNotEmpty) return 'bearer';
    final cookie = sessionCookie?.trim() ?? '';
    if (cookie.isNotEmpty) return 'cookie';
    return 'none';
  }

  static String _clip(String raw) {
    final oneLine = raw.replaceAll(RegExp(r'\s+'), ' ').trim();
    if (oneLine.length <= 240) return oneLine;
    return '${oneLine.substring(0, 240)}…';
  }

  static String _messageFor(int status, dynamic decoded, String raw) {
    String? detail;
    String? error;
    if (decoded is Map) {
      final d = decoded['detail'];
      if (d is String && d.isNotEmpty) detail = d;
      else if (d != null) detail = '$d';
      final e = decoded['error'];
      if (e is String && e.isNotEmpty) error = e;
    }
    if (status == 401) {
      final msg = (detail ?? error ?? '').toLowerCase();
      if (msg.contains('invalid credentials')) {
        return 'Wrong username or password (401 Invalid credentials).';
      }
      if (msg.contains('invalid 2fa')) {
        return 'Wrong 2FA code (401).';
      }
      if (msg.contains('not authenticated')) {
        return '401 Not authenticated — the app never reached /api/auth/login. Hot restart PhoneApp.';
      }
      if (detail != null) return '401: $detail';
      if (error != null) return '401: $error';
      return '401 Not authenticated. Check the token or password.';
    }
    if (detail != null) return detail;
    if (error != null) return error;
    if (status == 403) {
      return 'Forbidden. A phone token needs finance:read and finance:write. Companion chat tokens are not enough.';
    }
    if (status == 404) return 'Finance plugin is not installed, or the path is missing.';
    if (raw.isNotEmpty && raw.length < 280) return raw;
    return 'Request failed ($status)';
  }

  static String? sessionCookieFromHeaders(Map<String, String> headers) {
    for (final entry in headers.entries) {
      if (entry.key.toLowerCase() != 'set-cookie') continue;
      final match = RegExp(r'odysseus_session=([^;,\s]+)').firstMatch(entry.value);
      if (match != null) return match.group(1);
    }
    return null;
  }
}

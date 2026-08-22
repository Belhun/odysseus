import 'dart:convert';

import 'package:http/browser_client.dart';
import 'package:http/http.dart' as http;

import 'connect_logic.dart';
import 'ody_session.dart';

/// Flutter web uses the browser. HttpOnly cookies are not readable from
/// Dart, and SameSite=Lax often blocks cross-origin password login.
/// Token auth (Authorization header) is the supported web path.
OdySession createOdySession() => _WebOdySession();

class _WebOdySession implements OdySession {
  _WebOdySession() : _tokenClient = BrowserClient() {
    _cookieClient.withCredentials = true;
  }

  final http.Client _tokenClient;
  final BrowserClient _cookieClient = BrowserClient();

  @override
  Future<OdyResponse> send({
    required Uri uri,
    required String method,
    Map<String, String>? headers,
    Object? jsonBody,
    bool captureSessionCookie = false,
  }) async {
    final client = captureSessionCookie ? _cookieClient : _tokenClient;
    final req = http.Request(method, uri);
    if (headers != null) {
      req.headers.addAll(headers);
    }
    if (jsonBody != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(jsonBody);
    }
    final streamed = await client.send(req);
    final body = await streamed.stream.bytesToString();
    // Browser never exposes HttpOnly odysseus_session to Dart.
    return OdyResponse(
      statusCode: streamed.statusCode,
      body: body,
      sessionCookie: null,
    );
  }

  @override
  void close() {
    _tokenClient.close();
    _cookieClient.close();
  }
}

// Referenced so static tests and the guide can name the cookie.
const sessionCookieName = ConnectLogic.sessionCookieName;

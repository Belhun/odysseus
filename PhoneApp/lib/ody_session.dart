import 'dart:convert';

/// HTTP session used by Connect. Token auth sends Authorization.
/// Native password login captures odysseus_session from dart:io cookies
/// because Android WebView/HttpClient hides Set-Cookie from Dart's
/// `http` package headers.
class OdyResponse {
  OdyResponse({
    required this.statusCode,
    required this.body,
    this.sessionCookie,
  });

  final int statusCode;
  final String body;
  final String? sessionCookie;

  dynamic get json {
    if (body.isEmpty) {
      return null;
    }
    return jsonDecode(body);
  }
}

abstract class OdySession {
  Future<OdyResponse> send({
    required Uri uri,
    required String method,
    Map<String, String>? headers,
    Object? jsonBody,
    bool captureSessionCookie = false,
  });

  void close();
}

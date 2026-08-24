import 'dart:convert';

import 'package:http/http.dart' as http;

/// Browser path: package:http cannot read HttpOnly Set-Cookie.
Future<http.Response> postJsonCapturingCookies({
  required Uri uri,
  required Map<String, String> headers,
  Object? body,
  http.Client? client,
}) {
  final c = client ?? http.Client();
  return c.post(
    uri,
    headers: headers,
    body: body == null ? null : jsonEncode(body),
  );
}

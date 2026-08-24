import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../debug_log.dart';
import 'ody_http_factory_io.dart';

/// Native path: dart:io keeps Set-Cookie off the headers map.
/// Read HttpClientResponse.cookies so odysseus_session survives login.
Future<http.Response> postJsonCapturingCookies({
  required Uri uri,
  required Map<String, String> headers,
  Object? body,
  http.Client? client,
}) async {
  if (odyUsesRawHttps(uri)) {
    odyLog('raw-https POST $uri');
    final encoded = body == null
        ? <int>[]
        : utf8.encode(body is String ? body : jsonEncode(body));
    final addr = InternetAddress.tryParse(magicDnsFallbackIps[uri.host]!)!;
    return httpsViaIp(
      method: 'POST',
      url: uri,
      addr: addr,
      headers: headers,
      body: encoded,
    );
  }
  final httpClient = buildOdyHttpClient();
  try {
    final req = await httpClient.postUrl(uri);
    headers.forEach(req.headers.set);
    if (body != null) {
      final encoded = body is String ? body : jsonEncode(body);
      final bytes = utf8.encode(encoded);
      req.contentLength = bytes.length;
      req.add(bytes);
    }
    odyLog('dart:io POST $uri');
    final res = await req.close();
    final cookieNames = res.cookies.map((c) => c.name).join(',');
    final headerNames = <String>[];
    res.headers.forEach((name, _) => headerNames.add(name));
    odyLog(
      'dart:io POST done status=${res.statusCode} cookies=[$cookieNames] headers=$headerNames',
    );
    final bodyBytes = await res.fold<List<int>>(<int>[], (p, chunk) {
      p.addAll(chunk);
      return p;
    });
    final map = <String, String>{};
    res.headers.forEach((name, values) {
      map[name] = values.join(', ');
    });
    if (res.cookies.isNotEmpty) {
      map['set-cookie'] = res.cookies.map((c) => '${c.name}=${c.value}').join(', ');
    }
    return http.Response.bytes(
      bodyBytes,
      res.statusCode,
      headers: map,
      reasonPhrase: res.reasonPhrase,
    );
  } catch (e) {
    odyLog('dart:io POST failed $e');
    rethrow;
  } finally {
    httpClient.close(force: true);
  }
}

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/ody_http.dart';

void main() {
  test('Bearer header uses the ody_ token', () {
    final client = OdyHttp(baseUrl: 'http://host:7000', token: 'ody_abc');
    expect(client.uri('/api/finance/accounts').toString(),
        'http://host:7000/api/finance/accounts');
  });

  test('parseResponse maps 403 to finance scope copy', () {
    final client = OdyHttp(baseUrl: 'http://host:7000', token: 'ody_abc');
    expect(
      () => client.parseResponse(http.Response('{"detail":"nope"}', 403)),
      throwsA(isA<ApiException>()),
    );
    try {
      client.parseResponse(http.Response('{}', 403));
    } on ApiException catch (e) {
      expect(e.message, contains('finance:read'));
    }
  });

  test('sessionCookieFromHeaders reads odysseus_session', () {
    expect(
      OdyHttp.sessionCookieFromHeaders({
        'set-cookie': 'odysseus_session=abc123; Path=/; HttpOnly',
      }),
      'abc123',
    );
    expect(
      OdyHttp.sessionCookieFromHeaders({
        'set-cookie': 'odysseus_session=tok_from_io',
      }),
      'tok_from_io',
    );
  });

  test('parseResponse returns json maps', () {
    final client = OdyHttp(baseUrl: 'http://host:7000');
    final decoded = client.parseResponse(
      http.Response(jsonEncode({'accounts': []}), 200),
    );
    expect(decoded['accounts'], isEmpty);
  });
}

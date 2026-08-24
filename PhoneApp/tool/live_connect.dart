import 'dart:io';

import 'package:phone_app/ody_client.dart';

/// Native dart:io Connect (same HTTP stack as Android). Not Flutter web.
///
///   ODY_URL=http://127.0.0.1:7000 \
///   ODY_TOKEN=ody_… \
///   ODY_USER=belhun \
///   ODY_PASSWORD=… \
///   dart run tool/live_connect.dart
void main() async {
  final url = Platform.environment['ODY_URL'] ?? 'http://127.0.0.1:7000';
  final token = Platform.environment['ODY_TOKEN'] ?? '';
  final user = Platform.environment['ODY_USER'] ?? 'belhun';
  final password = Platform.environment['ODY_PASSWORD'] ?? '';
  final client = OdyClient();
  var failed = false;

  try {
    if (token.isEmpty) {
      stderr.writeln('FAIL G_NATIVE: ODY_TOKEN missing');
      failed = true;
    } else {
      final result = await client.connectWithToken(serverUrl: url, token: token);
      stdout.writeln(
        'PASS G_NATIVE token accounts=${result.accounts.length} mode=${result.mode}',
      );
    }

    if (password.isEmpty) {
      stderr.writeln('FAIL H_NATIVE: ODY_PASSWORD missing');
      failed = true;
    } else {
      final result = await client.loginWithPassword(
        serverUrl: url,
        username: user,
        password: password,
      );
      final cookie = result.sessionCookie ?? '';
      if (cookie.isEmpty) {
        stderr.writeln('FAIL H_NATIVE: no odysseus_session cookie');
        failed = true;
      } else {
        stdout.writeln(
          'PASS H_NATIVE password cookie_len=${cookie.length} accounts=${result.accounts.length}',
        );
      }
    }

    try {
      await client.connectWithToken(serverUrl: url, token: '');
      stderr.writeln('FAIL F: empty token did not throw');
      failed = true;
    } on OdyClientException catch (err) {
      if (err.message.contains('Paste an ody_ API token')) {
        stdout.writeln('PASS F empty token rejected before network: ${err.message}');
      } else {
        stderr.writeln('FAIL F unexpected: $err');
        failed = true;
      }
    }
  } catch (err, stack) {
    stderr.writeln('FAIL unexpected: $err\n$stack');
    failed = true;
  } finally {
    client.close();
  }
  exit(failed ? 1 : 0);
}

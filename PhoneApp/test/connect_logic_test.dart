import 'package:flutter_test/flutter_test.dart';
import 'package:odysseus_phone/connect_logic.dart';

void main() {
  test('empty token is rejected and never looks like a password login', () {
    expect(ConnectLogic.validateToken(''), 'Paste an ody_ API token');
    expect(ConnectLogic.validateToken('   '), 'Paste an ody_ API token');
    expect(ConnectLogic.validateToken('not-a-token'), 'Token must start with ody_');
    expect(ConnectLogic.validateToken('ody_abc'), isNull);
  });

  test('password login posts /api/auth/login not /api/login', () {
    expect(ConnectLogic.loginPath, '/api/auth/login');
    expect(ConnectLogic.wrongLoginPath, '/api/login');
    final uri = ConnectLogic.resolve('http://127.0.0.1:7000', ConnectLogic.loginPath);
    expect(uri.toString(), 'http://127.0.0.1:7000/api/auth/login');
    expect(uri.path, isNot(equals('/api/login')));
  });

  test('login body includes totp only when provided', () {
    final body = ConnectLogic.loginBody(
      username: 'belhun',
      password: 'secret',
      totp: '123456',
    );
    expect(body['username'], 'belhun');
    expect(body['remember'], isTrue);
    expect(body['totp_code'], '123456');
    final without = ConnectLogic.loginBody(username: 'belhun', password: 'secret');
    expect(without.containsKey('totp_code'), isFalse);
  });
}

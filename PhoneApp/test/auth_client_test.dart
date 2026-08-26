import 'package:flutter_test/flutter_test.dart';
import 'package:odysseus_phone/api/auth_client.dart';

void main() {
  test('AuthInfo.fromJson parses token scopes and features', () {
    final info = AuthInfo.fromJson({
      'auth': 'token',
      'owner': 'belhun',
      'scopes': ['chat', 'finance:read', 'finance:write'],
      'features': {'chat': true, 'finance': true, 'notes': false},
    });
    expect(info.isToken, isTrue);
    expect(info.hasChat, isTrue);
    expect(info.hasFinance, isTrue);
    expect(info.scopes, contains('chat'));
  });

  test('tokenPrefixLabel shortens ody_ secrets', () {
    expect(
      tokenPrefixLabel('ody_abcdefghijklmnopqrstuvwxyz'),
      'ody_abcdefgh...',
    );
    expect(tokenPrefixLabel('not-a-token'), '');
  });
}

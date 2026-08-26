import 'package:flutter_test/flutter_test.dart';
import 'package:odysseus_phone/security/setup_logic.dart';

void main() {
  test('profile validation requires url username and ody token', () {
    expect(
      SetupLogic.validateProfile(
        url: '',
        username: 'belhun',
        token: 'ody_abc',
      ),
      'Server URL is required',
    );
    expect(
      SetupLogic.validateProfile(
        url: 'https://host.ts.net',
        username: '',
        token: 'ody_abc',
      ),
      'Username is required',
    );
    expect(
      SetupLogic.validateProfile(
        url: 'https://host.ts.net',
        username: 'belhun',
        token: '',
      ),
      'Paste an ody_ API token',
    );
    expect(
      SetupLogic.validateProfile(
        url: 'https://host.ts.net',
        username: 'belhun',
        token: 'ody_abc',
      ),
      isNull,
    );
  });

  test('login validation requires password on submit', () {
    expect(SetupLogic.validateLogin(password: ''), 'Password is required');
    expect(SetupLogic.validateLogin(password: 'secret'), isNull);
  });

  test('full setup validates profile and password together', () {
    expect(
      SetupLogic.validate(
        url: 'https://host.ts.net',
        username: 'belhun',
        password: '',
        token: 'ody_abc',
      ),
      'Password is required',
    );
    expect(
      SetupLogic.validate(
        url: 'https://host.ts.net',
        username: 'belhun',
        password: 'secret',
        token: 'ody_abc',
      ),
      isNull,
    );
  });
}

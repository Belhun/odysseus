import 'package:flutter_test/flutter_test.dart';
import 'package:odysseus_phone/setup_link.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('odyphone setup link parses url token user', () {
    const raw =
        'odyphone://setup?url=https%3A%2F%2Fdell-mini-pc.tailcbcc46.ts.net&token=ody_test&user=belhun';
    final link = PhoneAppSetupLink.tryParse(raw);
    expect(link, isNotNull);
    expect(link!.url, 'https://dell-mini-pc.tailcbcc46.ts.net');
    expect(link.token, 'ody_test');
    expect(link.user, 'belhun');
  });

  test('wss qr is not a PhoneApp setup link', () {
    expect(
      PhoneAppSetupLink.tryParse('wss://dell-mini-pc.tailcbcc46.ts.net:443/phonepi'),
      isNull,
    );
  });

  test('logout clears session and returns to setup', () async {
    SharedPreferences.setMockInitialValues({
      'baseUrl': 'https://dell-mini-pc.tailcbcc46.ts.net',
      'token': 'ody_saved',
      'username': 'belhun',
      'sessionCookie': 'cookie',
      'setupComplete': true,
    });
    final prefs = await SharedPreferences.getInstance();
    final controller = AppController(prefs: prefs);
    await controller.restore();
    controller.baseUrl = 'https://your-host.tailXXXXXX.ts.net';
    controller.token = 'ody_saved';
    controller.sessionCookie = 'cookie';
    await controller.logout();
    expect(controller.finance, isNull);
    expect(controller.token, 'ody_saved');
    expect(controller.baseUrl, 'https://your-host.tailXXXXXX.ts.net');
    expect(controller.username, 'belhun');
    expect(controller.setupComplete, isFalse);
    expect(prefs.getString('sessionCookie'), isNull);
    expect(prefs.getBool('setupComplete'), isFalse);
    await controller.clearSavedToken();
    expect(controller.token, isEmpty);
  });
}

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

  test('sign-out keeps saved token; clear token wipes it', () async {
    SharedPreferences.setMockInitialValues({
      'baseUrl': 'https://dell-mini-pc.tailcbcc46.ts.net',
      'token': 'ody_saved',
      'username': 'belhun',
      'sessionCookie': 'cookie',
    });
    final prefs = await SharedPreferences.getInstance();
    final controller = AppController(prefs: prefs);
    controller.baseUrl = 'https://dell-mini-pc.tailcbcc46.ts.net';
    controller.token = 'ody_saved';
    controller.sessionCookie = 'cookie';
    await controller.disconnect();
    expect(controller.finance, isNull);
    expect(controller.token, 'ody_saved');
    expect(prefs.getString('token'), 'ody_saved');
    expect(prefs.getString('baseUrl'), 'https://dell-mini-pc.tailcbcc46.ts.net');
    expect(prefs.getString('sessionCookie'), isNull);
    await controller.clearSavedToken();
    expect(controller.token, isEmpty);
    expect(prefs.getString('token'), isNull);
  });
}

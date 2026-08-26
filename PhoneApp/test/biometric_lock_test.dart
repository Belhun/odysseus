import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/security/biometric_lock.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class FakeFinanceHttp extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final body = utf8.encode(jsonEncode({
      'accounts': [
        {'id': 'a1', 'name': 'Checking', 'posted_cents': 0, 'balance_cents': 0},
      ],
    }));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([body]),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}

class FakeBiometricGateway implements BiometricLockGateway {
  bool available = true;
  bool unlockResult = true;
  int authCalls = 0;

  @override
  Future<bool> authenticate({
    required String localizedReason,
    bool biometricOnly = false,
  }) async {
    authCalls++;
    return unlockResult;
  }

  @override
  Future<bool> canCheckBiometrics() async => available;

  @override
  Future<bool> isDeviceSupported() async => available;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('biometric on requires unlock until authenticate succeeds', () async {
    SharedPreferences.setMockInitialValues({
      'setupComplete': true,
      'biometricLockEnabled': true,
      'baseUrl': 'https://host.ts.net',
      'username': 'belhun',
      'token': 'ody_test',
      'sessionCookie': 'sess',
    });
    final prefs = await SharedPreferences.getInstance();
    final gateway = FakeBiometricGateway();
    final controller = AppController(
      prefs: prefs,
      httpClient: FakeFinanceHttp(),
      biometricLock: BiometricLockService(gateway: gateway),
    );
    await controller.restore();
    expect(controller.needsBiometricLock, isTrue);
    expect(controller.isUnlocked, isFalse);
    expect(controller.isConnected, isFalse);

    final ok = await controller.unlockWithBiometric();
    expect(ok, isTrue);
    expect(controller.isUnlocked, isTrue);
    expect(controller.isConnected, isTrue);
    expect(gateway.authCalls, 1);

    controller.lock();
    expect(controller.isUnlocked, isFalse);
    expect(controller.needsBiometricLock, isTrue);
  });

  test('biometric off stays signed in with auto login', () async {
    SharedPreferences.setMockInitialValues({
      'setupComplete': true,
      'biometricLockEnabled': false,
      'baseUrl': 'https://host.ts.net',
      'username': 'belhun',
      'token': 'ody_test',
      'sessionCookie': 'sess',
    });
    final prefs = await SharedPreferences.getInstance();
    final controller = AppController(
      prefs: prefs,
      httpClient: FakeFinanceHttp(),
      biometricLock: BiometricLockService(gateway: FakeBiometricGateway()),
    );
    await controller.restore();
    expect(controller.needsBiometricLock, isFalse);
    expect(controller.isUnlocked, isTrue);
    expect(controller.isConnected, isTrue);

    controller.lock();
    expect(controller.isUnlocked, isTrue);
    expect(controller.isConnected, isTrue);
  });

  test('decline biometric keeps stay-signed-in mode', () async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final controller = AppController(prefs: prefs);
    controller.pendingBiometricPrompt = true;
    controller.declineBiometricLock();
    expect(controller.biometricLockEnabled, isFalse);
    expect(controller.pendingBiometricPrompt, isFalse);
  });

  test('disabling biometric restores auto login', () async {
    SharedPreferences.setMockInitialValues({
      'setupComplete': true,
      'biometricLockEnabled': true,
      'baseUrl': 'https://host.ts.net',
      'username': 'belhun',
      'token': 'ody_test',
      'sessionCookie': 'sess',
    });
    final prefs = await SharedPreferences.getInstance();
    final controller = AppController(
      prefs: prefs,
      httpClient: FakeFinanceHttp(),
      biometricLock: BiometricLockService(gateway: FakeBiometricGateway()),
    );
    await controller.restore();
    expect(controller.needsBiometricLock, isTrue);

    await controller.setBiometricLockEnabled(false);
    expect(controller.biometricLockEnabled, isFalse);
    expect(controller.isUnlocked, isTrue);
    expect(controller.isConnected, isTrue);
  });
}

import 'package:flutter/foundation.dart';
import 'package:local_auth/local_auth.dart';

/// Thin wrapper around [LocalAuthentication] so tests can inject a fake gateway.
abstract class BiometricLockGateway {
  Future<bool> canCheckBiometrics();
  Future<bool> isDeviceSupported();
  Future<bool> authenticate({
    required String localizedReason,
    bool biometricOnly = false,
  });
}

class LocalAuthGateway implements BiometricLockGateway {
  LocalAuthGateway([LocalAuthentication? auth]) : _auth = auth ?? LocalAuthentication();

  final LocalAuthentication _auth;

  @override
  Future<bool> canCheckBiometrics() => _auth.canCheckBiometrics;

  @override
  Future<bool> isDeviceSupported() => _auth.isDeviceSupported();

  @override
  Future<bool> authenticate({
    required String localizedReason,
    bool biometricOnly = false,
  }) {
    return _auth.authenticate(
      localizedReason: localizedReason,
      options: AuthenticationOptions(
        biometricOnly: biometricOnly,
        stickyAuth: true,
        useErrorDialogs: true,
      ),
    );
  }
}

class BiometricLockService {
  BiometricLockService({BiometricLockGateway? gateway})
      : _gateway = gateway ?? LocalAuthGateway();

  final BiometricLockGateway _gateway;

  static const unlockReason = 'Unlock Odysseus to view your finances';

  Future<bool> get isAvailable async {
    if (kIsWeb) return false;
    if (!await _gateway.isDeviceSupported()) return false;
    return await _gateway.canCheckBiometrics() || await _gateway.isDeviceSupported();
  }

  Future<bool> unlock({bool biometricOnly = false}) async {
    if (kIsWeb) return true;
    try {
      return await _gateway.authenticate(
        localizedReason: unlockReason,
        biometricOnly: biometricOnly,
      );
    } catch (_) {
      return false;
    }
  }
}

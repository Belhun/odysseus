import 'package:flutter/material.dart';

import '../state/app_controller.dart';

/// Optional prompt after first successful login.
Future<void> showBiometricEnablePrompt(BuildContext context, AppController controller) async {
  if (!context.mounted || !controller.pendingBiometricPrompt) return;
  if (controller.biometricLockEnabled) {
    controller.dismissBiometricPrompt();
    return;
  }

  final available = await controller.biometricAvailable;
  if (!context.mounted) return;

  await showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) {
      return AlertDialog(
        title: const Text('Enable biometric unlock?'),
        content: Text(
          available
              ? 'Use fingerprint or face to open Odysseus next time. You can change this later under Settings → Security.'
              : 'This device has no biometrics enrolled. The app will stay signed in. Add a fingerprint or face in Android settings to enable it later.',
        ),
        actions: [
          TextButton(
            onPressed: () {
              controller.declineBiometricLock();
              Navigator.of(ctx).pop();
            },
            child: const Text('Not now'),
          ),
          if (available)
            FilledButton(
              onPressed: () async {
                Navigator.of(ctx).pop();
                await controller.acceptBiometricLock();
              },
              child: const Text('Enable'),
            ),
        ],
      );
    },
  );
}

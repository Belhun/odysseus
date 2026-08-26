import 'package:flutter/material.dart';

import 'screens/connect_screen.dart';
import 'screens/lock_screen.dart';
import 'screens/setup_screen.dart';
import 'screens/shell_screen.dart';
import 'state/app_controller.dart';
import 'widgets/biometric_prompt.dart';

/// Routes between setup, lock/unlock, reconnect, and the main shell.
class AppGate extends StatefulWidget {
  const AppGate({super.key, required this.controller});

  final AppController controller;

  @override
  State<AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<AppGate> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.controller.addListener(_onControllerChanged);
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onControllerChanged);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _onControllerChanged() {
    if (widget.controller.pendingBiometricPrompt && widget.controller.isUnlocked) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) showBiometricEnablePrompt(context, widget.controller);
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      widget.controller.lock();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final c = widget.controller;
        if (!c.setupComplete) {
          return SetupScreen(controller: c);
        }
        if (c.needsBiometricLock) {
          return LockScreen(controller: c);
        }
        if (c.isConnected) {
          return ShellScreen(controller: c);
        }
        return ConnectScreen(controller: c);
      },
    );
  }
}

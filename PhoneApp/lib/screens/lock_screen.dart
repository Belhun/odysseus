import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/ody_theme.dart';

class LockScreen extends StatefulWidget {
  const LockScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _tryUnlock());
  }

  Future<void> _tryUnlock() async {
    if (_busy || widget.controller.isUnlocked) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final ok = await widget.controller.unlockWithBiometric();
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (!ok) {
        _error = widget.controller.lastError ?? 'Unlock failed. Try again.';
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final name = widget.controller.username.trim();
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(),
              const Icon(Icons.lock_outline, size: 56, color: OdyColors.subheader),
              const SizedBox(height: 16),
              const Text(
                'Odysseus is locked',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              Text(
                name.isEmpty
                    ? 'Use your device biometrics or PIN to continue.'
                    : 'Hi $name. Use your device biometrics or PIN to continue.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: OdyColors.subheader),
              ),
              const SizedBox(height: 28),
              FilledButton.icon(
                onPressed: _busy ? null : _tryUnlock,
                icon: _busy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.fingerprint),
                label: Text(_busy ? 'Unlocking…' : 'Unlock'),
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(_error!, textAlign: TextAlign.center, style: const TextStyle(color: OdyColors.red)),
              ],
              const Spacer(flex: 2),
            ],
          ),
        ),
      ),
    );
  }
}

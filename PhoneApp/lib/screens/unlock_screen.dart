import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/ody_theme.dart';

/// Password-only unlock when biometric lock is off (or on web).
class UnlockScreen extends StatefulWidget {
  const UnlockScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<UnlockScreen> createState() => _UnlockScreenState();
}

class _UnlockScreenState extends State<UnlockScreen> {
  late final TextEditingController _password;
  late final TextEditingController _totp;

  @override
  void initState() {
    super.initState();
    _password = TextEditingController();
    _totp = TextEditingController();
  }

  @override
  void dispose() {
    _password.dispose();
    _totp.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    await widget.controller.unlockWithPassword(
      password: _password.text,
      totp: _totp.text,
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final name = c.username.trim();
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 48),
            const Icon(Icons.lock_outline, size: 56, color: OdyColors.subheader),
            const SizedBox(height: 16),
            const Text(
              'Sign in to Odysseus',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            Text(
              name.isEmpty
                  ? 'Enter your password to continue.'
                  : 'Hi $name. Enter your password to continue.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: OdyColors.subheader),
            ),
            if (c.baseUrl.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                c.baseUrl,
                textAlign: TextAlign.center,
                style: const TextStyle(color: OdyColors.muted, fontSize: 12),
              ),
            ],
            const SizedBox(height: 28),
            TextField(
              controller: _password,
              decoration: const InputDecoration(labelText: 'Password'),
              obscureText: true,
              autofocus: true,
              onSubmitted: (_) => _submit(),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _totp,
              decoration: InputDecoration(
                labelText: '2FA code${c.needsTotp ? ' (required)' : ' (if enabled)'}',
              ),
              keyboardType: TextInputType.number,
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: c.busy ? null : _submit,
              child: c.busy
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Unlock'),
            ),
            if (c.lastError != null) ...[
              const SizedBox(height: 16),
              Text(c.lastError!, style: const TextStyle(color: OdyColors.red)),
            ],
          ],
        ),
      ),
    );
  }
}

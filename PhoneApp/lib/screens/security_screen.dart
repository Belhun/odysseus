import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/ody_theme.dart';

class SecurityScreen extends StatefulWidget {
  const SecurityScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<SecurityScreen> createState() => _SecurityScreenState();
}

class _SecurityScreenState extends State<SecurityScreen> {
  final _password = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _password.dispose();
    super.dispose();
  }

  Future<void> _toggleBiometric(bool enable) async {
    setState(() => _error = null);
    if (!enable) {
      await widget.controller.setBiometricLockEnabled(false);
      return;
    }
    if (_password.text.isEmpty) {
      setState(() => _error = 'Enter your password to enable biometric unlock.');
      return;
    }
    final ok = await widget.controller.enableBiometricLock(password: _password.text);
    if (!mounted) return;
    if (ok) {
      _password.clear();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Biometric unlock enabled')),
        );
      }
    } else {
      setState(() => _error = widget.controller.lastError);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final c = widget.controller;
        return Scaffold(
          appBar: AppBar(title: const Text('Security')),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text(
                'App unlock',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 4),
              const Text(
                'When biometric unlock is off, the app stays signed in and opens without a lock screen. Your password is never stored on this device.',
                style: TextStyle(color: OdyColors.subheader, fontSize: 13),
              ),
              const SizedBox(height: 16),
              if (kIsWeb)
                const ListTile(
                  title: Text('Biometric unlock'),
                  subtitle: Text('Not available on web. Use the Android app on your phone.'),
                )
              else ...[
                SwitchListTile(
                  title: const Text('Biometric unlock'),
                  subtitle: Text(
                    c.biometricLockEnabled
                        ? 'Fingerprint, face, or device PIN opens the app'
                        : 'Stay signed in — no lock screen',
                  ),
                  value: c.biometricLockEnabled,
                  onChanged: c.busy ? null : _toggleBiometric,
                ),
                if (!c.biometricLockEnabled) ...[
                  const SizedBox(height: 8),
                  TextField(
                    controller: _password,
                    decoration: const InputDecoration(
                      labelText: 'Password',
                      helperText: 'Required once to turn on biometric unlock',
                    ),
                    obscureText: true,
                  ),
                ],
              ],
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(_error!, style: const TextStyle(color: OdyColors.red)),
              ],
              const SizedBox(height: 24),
              ListTile(
                title: const Text('Username'),
                subtitle: Text(c.username.isEmpty ? 'Not set' : c.username),
              ),
              ListTile(
                title: const Text('Server'),
                subtitle: Text(c.baseUrl.isEmpty ? 'Not set' : c.baseUrl),
              ),
            ],
          ),
        );
      },
    );
  }
}

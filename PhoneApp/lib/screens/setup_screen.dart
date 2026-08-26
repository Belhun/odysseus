import 'package:flutter/material.dart';

import '../debug_log.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';

class SetupScreen extends StatefulWidget {
  const SetupScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> {
  late final TextEditingController _url;
  late final TextEditingController _user;
  late final TextEditingController _password;
  late final TextEditingController _totp;
  late final TextEditingController _token;

  @override
  void initState() {
    super.initState();
    OdyLog.instance.addListener(_onLog);
    _url = TextEditingController(
      text: widget.controller.baseUrl.isNotEmpty
          ? widget.controller.baseUrl
          : 'https://your-host.tailXXXXXX.ts.net',
    );
    _user = TextEditingController(text: widget.controller.username);
    _password = TextEditingController();
    _totp = TextEditingController();
    _token = TextEditingController(text: widget.controller.token);
    odyLog('Setup screen open url=${_url.text}');
  }

  void _onLog() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    OdyLog.instance.removeListener(_onLog);
    _url.dispose();
    _user.dispose();
    _password.dispose();
    _totp.dispose();
    _token.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    odyLog(
      'Setup tapped url=${_url.text} user=${_user.text.trim().isEmpty ? "(empty)" : _user.text.trim()} '
      'token=${odyRedactSecret(_token.text)} password=${_password.text.isEmpty ? "no" : "yes"}',
    );
    try {
      await widget.controller.completeSetup(
        url: _url.text,
        user: _user.text,
        password: _password.text,
        apiToken: _token.text,
        totp: _totp.text,
      );
    } catch (e, st) {
      odyLog('Setup threw', error: e, stack: st);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return Scaffold(
      appBar: AppBar(title: const Text('Odysseus setup')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'First-time setup',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            'Configure your server, username, and API token. Then sign in with your Odysseus password. You can optionally enable fingerprint unlock after login.',
            style: TextStyle(color: OdyColors.subheader),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _url,
            decoration: const InputDecoration(
              labelText: 'Server URL',
              hintText: 'https://your-machine.tailxxxxx.ts.net',
              helperText: 'Tailscale Serve HTTPS URL, no port.',
            ),
            keyboardType: TextInputType.url,
            autocorrect: false,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _user,
            decoration: const InputDecoration(labelText: 'Username'),
            autocorrect: false,
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _token,
            decoration: const InputDecoration(
              labelText: 'ody_ API token',
              helperText:
                  'Gear → Phone app token on Odysseus. Needs finance scopes for this client.',
            ),
            obscureText: true,
            autocorrect: false,
          ),
          const Divider(height: 40),
          const Text(
            'Sign in',
            style: TextStyle(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          const Text(
            'Your password is not stored on this device.',
            style: TextStyle(color: OdyColors.muted, fontSize: 12),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _password,
            decoration: const InputDecoration(labelText: 'Password'),
            obscureText: true,
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
                : const Text('Sign in and finish setup'),
          ),
          if (c.lastError != null) ...[
            const SizedBox(height: 16),
            Text(c.lastError!, style: const TextStyle(color: OdyColors.red)),
          ],
          const SizedBox(height: 24),
          Row(
            children: [
              const Text('Debug log', style: TextStyle(fontWeight: FontWeight.w600)),
              const Spacer(),
              TextButton(
                onPressed: () => OdyLog.instance.clear(),
                child: const Text('Clear'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFF1b1e23),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFF3a3f4b)),
            ),
            child: SelectableText(
              OdyLog.instance.lines.isEmpty
                  ? '(no lines yet — tap Sign in)'
                  : OdyLog.instance.lines.join('\n'),
              style: const TextStyle(
                fontFamily: 'monospace',
                fontSize: 11,
                color: Color(0xFF9cdef2),
                height: 1.35,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../debug_log.dart';
import '../state/app_controller.dart';
import '../theme/ody_theme.dart';

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  late final TextEditingController _url;
  late final TextEditingController _token;
  late final TextEditingController _user;
  late final TextEditingController _password;
  late final TextEditingController _totp;
  bool _useToken = false;

  @override
  void initState() {
    super.initState();
    OdyLog.instance.addListener(_onLog);
    _url = TextEditingController(
      text: widget.controller.baseUrl.isNotEmpty
          ? widget.controller.baseUrl
          : 'https://dell-mini-pc.tailcbcc46.ts.net',
    );
    _token = TextEditingController(text: widget.controller.token);
    _user = TextEditingController(text: widget.controller.username);
    _password = TextEditingController();
    _totp = TextEditingController();
    _useToken = widget.controller.token.isNotEmpty;
    odyLog('Connect screen open tokenTab=$_useToken url=${_url.text}');
  }

  void _onLog() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    OdyLog.instance.removeListener(_onLog);
    _url.dispose();
    _token.dispose();
    _user.dispose();
    _password.dispose();
    _totp.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    odyLog(
      'Connect tapped mode=${_useToken ? "token" : "password"} '
      'url=${_url.text} host=${Uri.tryParse(_url.text)?.host} '
      'user=${_user.text.trim().isEmpty ? "(empty)" : _user.text.trim()} '
      'token=${odyRedactSecret(_useToken ? _token.text : "")} '
      'password=${_password.text.isEmpty ? "no" : "yes"} totp=${_totp.text.isEmpty ? "no" : "yes"}',
    );
    try {
      final ok = await widget.controller.connect(
        url: _url.text,
        apiToken: _useToken ? _token.text : '',
        user: _user.text,
        password: _password.text,
        totp: _totp.text,
      );
      odyLog('Connect finished ok=$ok error=${widget.controller.lastError}');
      if (!ok && mounted && widget.controller.needsTotp) {
        setState(() => _useToken = false);
      }
    } catch (e, st) {
      odyLog('Connect threw', error: e, stack: st);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return Scaffold(
      appBar: AppBar(title: const Text('Odysseus')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Text(
            'Phone client',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 8),
          const Text(
            'v1 syncs finance to your Odysseus server. Reach the host over Tailscale. There is no public relay and no cloud login.',
            style: TextStyle(color: OdyColors.subheader),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: _url,
            decoration: const InputDecoration(
              labelText: 'Server URL',
              hintText: 'https://your-machine.tailxxxxx.ts.net',
              helperText:
                  'Tailscale Serve HTTPS URL, no port. If Connect fails on DNS, keep this host; the app uses the Mini PC Tailscale IP.',
            ),
            keyboardType: TextInputType.url,
            autocorrect: false,
          ),
          const SizedBox(height: 16),
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: true, label: Text('API token'), icon: Icon(Icons.key)),
              ButtonSegment(value: false, label: Text('Password'), icon: Icon(Icons.person)),
            ],
            selected: {_useToken},
            onSelectionChanged: (s) => setState(() => _useToken = s.first),
          ),
          const SizedBox(height: 16),
          if (_useToken) ...[
            TextField(
              controller: _token,
              decoration: const InputDecoration(
                labelText: 'ody_ token',
                helperText:
                    'Gear → Phone app token (admin). One click: Phone finance. Paste here and leave password blank.',
              ),
              obscureText: true,
              autocorrect: false,
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _user,
              decoration: const InputDecoration(
                labelText: 'Username (optional label)',
              ),
            ),
          ] else ...[
            TextField(
              controller: _user,
              decoration: const InputDecoration(labelText: 'Username'),
              autocorrect: false,
            ),
            const SizedBox(height: 8),
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
            const SizedBox(height: 8),
            const Text(
              'Pixel over Tailscale. Server URL must be https://dell-mini-pc.tailcbcc46.ts.net (no port). Mint a token from the Odysseus gear: Phone app token.',
              style: TextStyle(color: OdyColors.muted, fontSize: 12),
            ),
          ],
          const SizedBox(height: 20),
          if (c.token.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                'Saved token is ready. Tap Connect, or Clear saved token in Settings to forget it.',
                style: TextStyle(color: OdyColors.muted, fontSize: 12),
              ),
            ),
          FilledButton(
            onPressed: c.busy ? null : _submit,
            child: c.busy
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Connect'),
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
          const Text(
            'These lines also print as [OdyPhone] in flutter run. The Android IME spam in that console is not this log.',
            style: TextStyle(color: OdyColors.muted, fontSize: 11),
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
                  ? '(no lines yet — tap Connect)'
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

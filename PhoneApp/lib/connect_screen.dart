import 'package:flutter/material.dart';

import 'finance_home.dart';
import 'ody_client.dart';

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key, this.client});

  final OdyClient? client;

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  late final OdyClient _client;
  final _url = TextEditingController(text: 'http://127.0.0.1:7000');
  final _token = TextEditingController();
  final _tokenLabel = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _totp = TextEditingController();
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _client = widget.client ?? OdyClient();
  }

  @override
  void dispose() {
    _tabs.dispose();
    _url.dispose();
    _token.dispose();
    _tokenLabel.dispose();
    _username.dispose();
    _password.dispose();
    _totp.dispose();
    if (widget.client == null) {
      _client.close();
    }
    super.dispose();
  }

  Future<void> _connectToken() async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final result = await _client.connectWithToken(
        serverUrl: _url.text,
        token: _token.text,
        usernameLabel: _tokenLabel.text,
      );
      if (!mounted) {
        return;
      }
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => FinanceHome(result: result),
        ),
      );
    } on OdyClientException catch (err) {
      setState(() => _error = err.message);
    } catch (err) {
      setState(() => _error = err.toString());
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  Future<void> _connectPassword() async {
    setState(() {
      _error = null;
      _busy = true;
    });
    try {
      final result = await _client.loginWithPassword(
        serverUrl: _url.text,
        username: _username.text,
        password: _password.text,
        totp: _totp.text,
      );
      if (!mounted) {
        return;
      }
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => FinanceHome(result: result),
        ),
      );
    } on OdyClientException catch (err) {
      setState(() => _error = err.message);
    } catch (err) {
      setState(() => _error = err.toString());
    } finally {
      if (mounted) {
        setState(() => _busy = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('PhoneApp Connect'),
        bottom: TabBar(
          controller: _tabs,
          tabs: const [
            Tab(text: 'API token'),
            Tab(text: 'Password'),
          ],
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              key: const Key('server-url'),
              controller: _url,
              decoration: const InputDecoration(
                labelText: 'Server URL',
                hintText: 'http://127.0.0.1:7000',
              ),
              keyboardType: TextInputType.url,
              enabled: !_busy,
            ),
            const SizedBox(height: 12),
            Expanded(
              child: TabBarView(
                controller: _tabs,
                children: [
                  _tokenTab(),
                  _passwordTab(),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(
                _error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _tokenTab() {
    return ListView(
      children: [
        const Text(
          'Paste an ody_ token with finance:read and finance:write. '
          'Username is a label only and is not sent as a password.',
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('api-token'),
          controller: _token,
          decoration: const InputDecoration(
            labelText: 'API token',
            hintText: 'ody_…',
          ),
          obscureText: true,
          enabled: !_busy,
        ),
        TextField(
          controller: _tokenLabel,
          decoration: const InputDecoration(
            labelText: 'Username (optional label)',
          ),
          enabled: !_busy,
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('connect-token'),
          onPressed: _busy ? null : _connectToken,
          child: Text(_busy ? 'Connecting…' : 'Connect with token'),
        ),
      ],
    );
  }

  Widget _passwordTab() {
    return ListView(
      children: [
        const Text(
          'Posts /api/auth/login as JSON. Do not use /api/login. '
          'Flutter web often cannot see the HttpOnly session cookie; use the token tab there.',
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('password-username'),
          controller: _username,
          decoration: const InputDecoration(labelText: 'Username'),
          enabled: !_busy,
        ),
        TextField(
          key: const Key('password-password'),
          controller: _password,
          decoration: const InputDecoration(labelText: 'Password'),
          obscureText: true,
          enabled: !_busy,
        ),
        TextField(
          controller: _totp,
          decoration: const InputDecoration(
            labelText: 'TOTP (if 2FA)',
          ),
          keyboardType: TextInputType.number,
          enabled: !_busy,
        ),
        const SizedBox(height: 16),
        FilledButton(
          key: const Key('connect-password'),
          onPressed: _busy ? null : _connectPassword,
          child: Text(_busy ? 'Signing in…' : 'Sign in with password'),
        ),
      ],
    );
  }
}

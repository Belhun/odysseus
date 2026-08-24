import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import '../theme/ody_theme.dart';
import '../widgets/common.dart';
import 'accounts_screen.dart';
import 'budget_screen.dart';
import 'import_screen.dart';
import 'reports_screen.dart';
import 'rules_screen.dart';

class MoreScreen extends StatelessWidget {
  const MoreScreen({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        children: [
          const ListTile(
            title: Text('Finance'),
            subtitle: Text('Same destinations as the Odysseus web finance tabs'),
          ),
          _tile(context, Icons.account_balance, 'Accounts',
              () => AccountsScreen(controller: controller)),
          _tile(context, Icons.file_upload, 'Import',
              () => ImportScreen(controller: controller)),
          _tile(context, Icons.bar_chart, 'Reports',
              () => ReportsScreen(controller: controller)),
          _tile(context, Icons.rule, 'Rules', () => RulesScreen(controller: controller)),
          _tile(
            context,
            Icons.event_available,
            'Budget (test: month-close)',
            () => BudgetScreen(controller: controller, monthClose: true),
          ),
          const Divider(),
          const ListTile(
            title: Text('No API yet'),
            subtitle: Text('Labeled placeholders. Not a second database.'),
          ),
          _placeholder(
            context,
            'Goals',
            'Odysseus has no goals table. Use Budget limits for now.',
            'Budget',
          ),
          _placeholder(
            context,
            'Investing',
            'No investing endpoints. Do not block shipping on this.',
            null,
          ),
          _placeholder(
            context,
            'Sankey / cashflow map',
            'Ocular-style Sankey is not on the finance API. Reports → Cashflow is the closest live view.',
            'Reports',
          ),
          const Divider(),
          const ListTile(
            title: Text('Later Odysseus modules'),
            subtitle: Text('Shell only. Chat, email, calendar, notes come after finance v1.'),
          ),
          _placeholder(context, 'Chat', 'Not in v1.', null),
          _placeholder(context, 'Email', 'Not in v1.', null),
          _placeholder(context, 'Calendar', 'Not in v1.', null),
          _placeholder(context, 'Notes', 'Not in v1.', null),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.settings),
            title: const Text('Settings'),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => SettingsScreen(controller: controller)),
            ),
          ),
        ],
      ),
    );
  }

  ListTile _tile(
    BuildContext context,
    IconData icon,
    String title,
    Widget Function() page,
  ) {
    return ListTile(
      leading: Icon(icon),
      title: Text(title),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => page())),
    );
  }

  ListTile _placeholder(
    BuildContext context,
    String title,
    String reason,
    String? closest,
  ) {
    return ListTile(
      leading: const Icon(Icons.hourglass_empty, color: OdyColors.muted),
      title: Text(title),
      subtitle: const Text('Placeholder'),
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => PlaceholderScreen(title: title, reason: reason, closest: closest),
        ),
      ),
    );
  }
}

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return Scaffold(
          appBar: AppBar(title: const Text('Settings')),
          body: ListView(
            children: [
              ListTile(
                title: const Text('Server'),
                subtitle: Text(controller.baseUrl.isEmpty ? 'Not set' : controller.baseUrl),
              ),
              ListTile(
                title: const Text('Auth'),
                subtitle: Text(
                  controller.token.isNotEmpty
                      ? 'API token (ody_)'
                      : controller.sessionCookie.isNotEmpty
                          ? 'Session cookie'
                          : 'None',
                ),
              ),
              const ListTile(
                title: Text('Network'),
                subtitle: Text(
                  'Keep the phone on Tailscale. Do not expose Odysseus to the public internet.',
                ),
              ),
              SwitchListTile(
                title: const Text('Privacy mode'),
                subtitle: const Text('Hide balances on this device'),
                value: controller.privacyMode,
                onChanged: controller.setPrivacy,
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                child: Text('Theme', style: Theme.of(context).textTheme.titleSmall),
              ),
              RadioListTile<int>(
                value: 0,
                groupValue: controller.themeIndex,
                title: const Text('Dark (Odysseus)'),
                onChanged: (v) {
                  if (v != null) controller.setThemeIndex(v);
                },
              ),
              RadioListTile<int>(
                value: 1,
                groupValue: controller.themeIndex,
                title: const Text('Light'),
                onChanged: (v) {
                  if (v != null) controller.setThemeIndex(v);
                },
              ),
              RadioListTile<int>(
                value: 2,
                groupValue: controller.themeIndex,
                title: const Text('System'),
                onChanged: (v) {
                  if (v != null) controller.setThemeIndex(v);
                },
              ),
              const SizedBox(height: 12),
              Padding(
                padding: const EdgeInsets.all(16),
                child: OutlinedButton(
                  onPressed: () async {
                    await controller.disconnect();
                    if (context.mounted) Navigator.of(context).popUntil((r) => r.isFirst);
                  },
                  child: const Text('Disconnect'),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

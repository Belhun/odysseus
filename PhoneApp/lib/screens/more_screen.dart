import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import 'accounts_screen.dart';
import 'budget_screen.dart';
import 'calendar_screen.dart';
import 'chat_list_screen.dart';
import 'email_list_screen.dart';
import 'goals_screen.dart';
import 'import_screen.dart';
import 'investing_screen.dart';
import 'notes_list_screen.dart';
import 'reports_screen.dart';
import 'rules_screen.dart';
import 'sankey_screen.dart';

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
            title: Text('Finance extras'),
            subtitle: Text('Same books as the web finance modal'),
          ),
          _tile(context, Icons.flag, 'Goals', () => GoalsScreen(controller: controller)),
          _tile(context, Icons.show_chart, 'Investing',
              () => InvestingScreen(controller: controller)),
          _tile(
            context,
            Icons.account_tree,
            'Sankey / cashflow map',
            () => SankeyScreen(controller: controller),
          ),
          const Divider(),
          const ListTile(
            title: Text('Companion'),
            subtitle: Text('Same records as Odysseus web'),
          ),
          _tile(context, Icons.chat_bubble_outline, 'Chat',
              () => ChatListScreen(controller: controller)),
          _tile(context, Icons.mail_outline, 'Email',
              () => EmailListScreen(controller: controller)),
          _tile(context, Icons.calendar_month, 'Calendar',
              () => CalendarScreen(controller: controller)),
          _tile(context, Icons.sticky_note_2_outlined, 'Notes',
              () => NotesListScreen(controller: controller)),
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    OutlinedButton(
                      onPressed: () async {
                        await controller.disconnect();
                        if (context.mounted) Navigator.of(context).popUntil((r) => r.isFirst);
                      },
                      child: const Text('Sign out'),
                    ),
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () async {
                        await controller.clearSavedToken();
                        if (context.mounted) Navigator.of(context).popUntil((r) => r.isFirst);
                      },
                      child: const Text('Clear saved token'),
                    ),
                    const Padding(
                      padding: EdgeInsets.only(top: 4),
                      child: Text(
                        'Sign out keeps the last ody_ token for one-tap reconnect. Clear saved token forgets it.',
                        style: TextStyle(fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

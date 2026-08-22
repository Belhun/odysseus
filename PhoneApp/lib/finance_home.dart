import 'package:flutter/material.dart';

import 'ody_client.dart';

class FinanceHome extends StatelessWidget {
  const FinanceHome({super.key, required this.result});

  final FinanceConnectResult result;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Accounts'), key: const Key('accounts-appbar')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Server: ${result.serverUrl}'),
            Text('Mode: ${result.mode}'),
            if (result.usernameLabel != null) Text('Label: ${result.usernameLabel}'),
            const SizedBox(height: 12),
            Expanded(
              child: result.accounts.isEmpty
                  ? const Text('No accounts yet. Finance plugin is installed and reachable.')
                  : ListView.builder(
                      itemCount: result.accounts.length,
                      itemBuilder: (context, index) {
                        final row = result.accounts[index];
                        final name = row is Map ? (row['name'] ?? row['id'] ?? row) : row;
                        return ListTile(title: Text('$name'));
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

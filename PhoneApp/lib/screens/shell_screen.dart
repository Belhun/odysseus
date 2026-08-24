import 'package:flutter/material.dart';

import '../state/app_controller.dart';
import 'accounts_screen.dart';
import 'budget_screen.dart';
import 'home_screen.dart';
import 'import_screen.dart';
import 'more_screen.dart';
import 'recurring_screen.dart';
import 'reports_screen.dart';
import 'transaction_edit_screen.dart';
import 'transactions_screen.dart';

/// Unified Cashew-style destinations that also match Odysseus web tabs.
class ShellScreen extends StatefulWidget {
  const ShellScreen({super.key, required this.controller});

  final AppController controller;

  @override
  State<ShellScreen> createState() => _ShellScreenState();
}

class _ShellScreenState extends State<ShellScreen> {
  int _index = 0;

  static const _tabs = [
    NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
    NavigationDestination(icon: Icon(Icons.payments_outlined), selectedIcon: Icon(Icons.payments), label: 'Transactions'),
    NavigationDestination(icon: Icon(Icons.pie_chart_outline), selectedIcon: Icon(Icons.pie_chart), label: 'Budget'),
    NavigationDestination(icon: Icon(Icons.event_repeat_outlined), selectedIcon: Icon(Icons.event_repeat), label: 'Recurring'),
    NavigationDestination(icon: Icon(Icons.more_horiz), selectedIcon: Icon(Icons.more_horiz), label: 'More'),
  ];

  @override
  Widget build(BuildContext context) {
    final pages = [
      HomeScreen(controller: widget.controller, onOpenTab: _openTab),
      TransactionsScreen(controller: widget.controller),
      BudgetScreen(controller: widget.controller),
      RecurringScreen(controller: widget.controller),
      MoreScreen(controller: widget.controller),
    ];
    final showFab = _index == 0 || _index == 1;
    return Scaffold(
      body: IndexedStack(index: _index, children: pages),
      floatingActionButton: showFab
          ? FloatingActionButton(
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => TransactionEditScreen(controller: widget.controller),
                ),
              ),
              tooltip: 'Add transaction',
              child: const Icon(Icons.add),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        destinations: _tabs,
        onDestinationSelected: (i) => setState(() => _index = i),
      ),
    );
  }

  void _openTab(String name) {
    setState(() {
      switch (name) {
        case 'transactions':
          _index = 1;
        case 'budget':
          _index = 2;
        case 'recurring':
          _index = 3;
        case 'more':
          _index = 4;
        default:
          _index = 0;
      }
    });
    if (name == 'accounts') {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => AccountsScreen(controller: widget.controller)),
      );
    } else if (name == 'import') {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ImportScreen(controller: widget.controller)),
      );
    } else if (name == 'reports') {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => ReportsScreen(controller: widget.controller)),
      );
    }
  }
}

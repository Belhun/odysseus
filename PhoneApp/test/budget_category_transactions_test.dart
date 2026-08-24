import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/models.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/budget_screen.dart';
import 'package:odysseus_phone/screens/transactions_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class RecordingFinanceHttp extends http.BaseClient {
  RecordingFinanceHttp({this.transactions = const []});

  final List<Map<String, dynamic>> transactions;
  final List<Uri> transactionListUris = [];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final path = request.url.path;
    Object body = {'ok': true};
    if (path.endsWith('/accounts')) {
      body = {
        'accounts': [
          {'id': 'a1', 'name': 'Checking', 'posted_cents': 5000, 'balance_cents': 5000},
        ]
      };
    } else if (path.endsWith('/categories')) {
      body = {
        'categories': [
          {'id': 'c1', 'name': 'Groceries', 'display_name': 'Groceries'},
        ]
      };
    } else if (path.endsWith('/transactions')) {
      transactionListUris.add(request.url);
      body = {'total': transactions.length, 'transactions': transactions};
    } else if (path.contains('/budgets') || path.contains('/spending')) {
      body = {
        'month': request.url.queryParameters['month'] ?? '2026-08',
        'categories': [
          {
            'category_id': 'c1',
            'category_name': 'Groceries',
            'spent_cents': 5000,
            'transaction_count': 1,
            'limit_cents': 20000,
            'remaining_cents': 15000,
          },
        ],
        'income_cents': 0,
        'net_spend_cents': 5000,
        'personal_spend_cents': 5000,
        'unclassified_count': 0,
      };
    }
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}

Future<AppController> _controller(http.Client raw) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: raw);
  controller.baseUrl = 'http://test:7000';
  controller.token = 'ody_test';
  controller.finance = FinanceClient(
    OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw),
  );
  return controller;
}

Future<void> _pumpBudget(WidgetTester tester, AppController controller, {bool monthClose = false}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: BudgetScreen(controller: controller, monthClose: monthClose),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('short tap on a budget row still opens the limit editor', (tester) async {
    final httpClient = RecordingFinanceHttp();
    final controller = await _controller(httpClient);
    await _pumpBudget(tester, controller);

    await tester.tap(find.text('Groceries'));
    await tester.pumpAndSettle();

    expect(find.text('Limit · Groceries'), findsOneWidget);
    expect(find.text('Hold for transactions'), findsNothing);
    expect(httpClient.transactionListUris, isEmpty);
  });

  testWidgets('long-press opens category transactions for the selected budget month', (tester) async {
    final httpClient = RecordingFinanceHttp(
      transactions: [
        {
          'id': 't1',
          'account_id': 'a1',
          'amount_cents': -1250,
          'payee': 'Market',
          'date': '2026-07-04',
          'category_id': 'c1',
          'category_name': 'Groceries',
          'status': 'cleared',
        },
      ],
    );
    final controller = await _controller(httpClient);
    await _pumpBudget(tester, controller, monthClose: true);

    await tester.longPress(find.text('Groceries'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    final expectedMonth = previousMonthKey(currentMonthKey());
    expect(find.textContaining('Groceries · $expectedMonth'), findsWidgets);
    expect(find.text('Market'), findsOneWidget);
    expect(find.text('Limit · Groceries'), findsNothing);

    expect(httpClient.transactionListUris, isNotEmpty);
    final q = httpClient.transactionListUris.last.queryParameters;
    expect(q['category_id'], 'c1');
    expect(q['month'], expectedMonth);
    expect(q.containsKey('uncategorized'), isFalse);
  });

  testWidgets('filtered transactions show an empty state for that month', (tester) async {
    final httpClient = RecordingFinanceHttp();
    final controller = await _controller(httpClient);
    await tester.pumpWidget(
      MaterialApp(
        home: TransactionsScreen(
          controller: controller,
          initialCategoryId: 'c1',
          initialCategoryName: 'Groceries',
          initialMonth: '2025-01',
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('No transactions in 2025-01 for Groceries.'), findsOneWidget);
    expect(httpClient.transactionListUris, isNotEmpty);
    final q = httpClient.transactionListUris.last.queryParameters;
    expect(q['category_id'], 'c1');
    expect(q['month'], '2025-01');
  });

  testWidgets('back from category transactions returns to budget', (tester) async {
    final httpClient = RecordingFinanceHttp();
    final controller = await _controller(httpClient);
    await _pumpBudget(tester, controller);

    await tester.longPress(find.text('Groceries'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.byType(TransactionsScreen), findsOneWidget);

    await tester.pageBack();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.byType(TransactionsScreen), findsNothing);
    expect(find.byType(BudgetScreen), findsOneWidget);
    expect(find.text(currentMonthKey()), findsWidgets);
  });
}

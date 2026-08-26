import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/models.dart';
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/app.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class EmptyFinanceHttp extends http.BaseClient {
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
      body = {'categories': []};
    } else if (path.endsWith('/transactions')) {
      body = {'total': 0, 'transactions': []};
    } else if (path.endsWith('/recurring')) {
      body = {'series': []};
    } else if (path.contains('/budgets') || path.contains('/spending')) {
      body = {
        'month': '2026-08',
        'categories': [],
        'income_cents': 0,
        'net_spend_cents': 0,
        'personal_spend_cents': 0,
        'unclassified_count': 0,
      };
    } else if (path.contains('/net-worth')) {
      body = {'assets_cents': 5000, 'liabilities_cents': 0, 'net_worth_cents': 5000};
    } else if (path.contains('/trends')) {
      body = {'trends': []};
    } else if (path.contains('/cashflow')) {
      body = {'income_cents': 0, 'net_spend_cents': 0, 'personal_spend_cents': 0};
    } else if (path.contains('/spend-by-account')) {
      body = {'accounts': []};
    } else if (path.contains('/goals')) {
      body = {'goals': []};
    } else if (path.contains('/ping')) {
      body = {'ok': true};
    }
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      200,
      headers: {'content-type': 'application/json'},
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('setup screen explains Tailscale', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final controller = AppController(prefs: prefs);
    await tester.pumpWidget(OdysseusPhoneApp(controller: controller));
    expect(find.text('Odysseus setup'), findsOneWidget);
    expect(find.text('First-time setup'), findsOneWidget);
    expect(find.text('Home'), findsNothing);
  });

  testWidgets('shell uses one bottom nav', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final http = EmptyFinanceHttp();
    final controller = AppController(prefs: prefs, httpClient: http);
    controller.setupComplete = true;
    controller.biometricLockEnabled = false;
    controller.isUnlocked = true;
    controller.baseUrl = 'http://test:7000';
    controller.token = 'ody_test';
    controller.finance = FinanceClient(
      OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: http),
    );
    controller.homePrefetched = true;
    controller.cachedAccounts = [
      FinanceAccount.fromJson({
        'id': 'a1',
        'name': 'Checking',
        'posted_cents': 5000,
        'balance_cents': 5000,
      }),
    ];
    await tester.pumpWidget(OdysseusPhoneApp(controller: controller));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Home'), findsWidgets);
    expect(find.text('Transactions'), findsWidgets);
    expect(find.text('Budget'), findsWidgets);
    expect(find.text('Recurring'), findsWidgets);
    expect(find.text('More'), findsWidgets);
    expect(find.byType(NavigationBar), findsOneWidget);
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  testWidgets('More opens Goals instead of a placeholder', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final http = EmptyFinanceHttp();
    final httpLayer = OdyHttp(
      baseUrl: 'http://test:7000',
      token: 'ody_test',
      client: http,
    );
    final controller = AppController(prefs: prefs, httpClient: http);
    controller.setupComplete = true;
    controller.biometricLockEnabled = false;
    controller.isUnlocked = true;
    controller.homePrefetched = true;
    controller.httpLayer = httpLayer;
    controller.finance = FinanceClient(httpLayer);
    await tester.pumpWidget(OdysseusPhoneApp(controller: controller));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.descendant(of: find.byType(NavigationBar), matching: find.text('More')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.scrollUntilVisible(find.text('Investing'), 300);
    expect(find.text('Goals'), findsOneWidget);
    expect(find.text('Investing'), findsOneWidget);
    expect(find.text('Chat'), findsOneWidget);
    expect(find.text('Budget (test: month-close)'), findsOneWidget);
    await tester.tap(find.text('Goals'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('No goals yet'), findsOneWidget);
    expect(find.textContaining('placeholder'), findsNothing);
  });
}

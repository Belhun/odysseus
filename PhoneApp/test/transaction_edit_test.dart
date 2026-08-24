import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/models.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/transaction_edit_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class EditLookupsHttp extends http.BaseClient {
  EditLookupsHttp({this.accounts});

  final List<Map<String, dynamic>>? accounts;
  Map<String, dynamic>? lastPatchBody;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final path = request.url.path;
    Object body = {'ok': true};
    if (path.endsWith('/accounts')) {
      body = {
        'accounts': accounts ??
            [
              {
                'id': 'a1',
                'name': 'Checking',
                'posted_cents': 5000,
                'balance_cents': 5000,
              },
            ],
      };
    } else if (path.endsWith('/categories')) {
      body = {
        'categories': [
          {'id': 'c1', 'name': 'Groceries', 'display_name': 'Groceries'},
        ],
      };
    } else if (request.method == 'PATCH' && path.contains('/transactions/')) {
      if (request is http.Request) {
        lastPatchBody = jsonDecode(request.body) as Map<String, dynamic>;
      }
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

Future<AppController> _controller(http.Client raw) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: raw);
  controller.finance = FinanceClient(
    OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw),
  );
  return controller;
}

FinanceTransaction _tx({
  String movementClass = 'pass_through',
  String status = 'cleared',
  String accountId = 'a1',
  String? categoryId,
}) {
  return FinanceTransaction(
    id: 't1',
    accountId: accountId,
    amountCents: -1250,
    payee: 'PayPal withdrawal',
    status: status,
    date: '2026-08-01',
    memo: 'processor leg',
    categoryId: categoryId,
    movementClass: movementClass,
  );
}

Future<void> _pumpEdit(
  WidgetTester tester, {
  required AppController controller,
  required FinanceTransaction existing,
}) async {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(
    MaterialApp(
      home: TransactionEditScreen(controller: controller, existing: existing),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('uiMovementClass maps pass_through to transfer like the web UI', () {
    expect(uiMovementClass('pass_through'), 'transfer');
    expect(uiMovementClass('transfer'), 'transfer');
    expect(uiMovementClass('spend'), 'spend');
    expect(uiMovementClass(null), isNull);
  });

  test('storedMovementClass keeps pass_through when Transfer is left selected', () {
    expect(
      storedMovementClass('transfer', original: 'pass_through'),
      'pass_through',
    );
    expect(storedMovementClass('spend', original: 'pass_through'), 'spend');
    expect(storedMovementClass('transfer', original: 'transfer'), 'transfer');
    expect(storedMovementClass(null, original: 'pass_through'), isNull);
  });

  test('dropdownValueIn falls back when the bound value is missing', () {
    expect(dropdownValueIn('pass_through', kUiMovementClasses), isNull);
    expect(dropdownValueIn('transfer', kUiMovementClasses), 'transfer');
    expect(dropdownValueIn(null, kUiMovementClasses), isNull);
  });

  testWidgets('editing a pass_through transaction does not red-screen', (tester) async {
    final raw = EditLookupsHttp();
    final controller = await _controller(raw);
    await _pumpEdit(tester, controller: controller, existing: _tx());
    expect(tester.takeException(), isNull);
    expect(find.text('Edit transaction'), findsOneWidget);
    expect(
      tester.state<FormFieldState<String?>>(find.byKey(const Key('tx-movement-class'))).value,
      'transfer',
    );
    expect(find.text('pass_through'), findsNothing);
  });

  testWidgets('unknown movement class falls back instead of asserting', (tester) async {
    final raw = EditLookupsHttp();
    final controller = await _controller(raw);
    await _pumpEdit(
      tester,
      controller: controller,
      existing: _tx(movementClass: 'mystery_class'),
    );
    expect(tester.takeException(), isNull);
    expect(find.text('Edit transaction'), findsOneWidget);
    expect(
      tester.state<FormFieldState<String?>>(find.byKey(const Key('tx-movement-class'))).value,
      isNull,
    );
  });

  testWidgets('saving a pass_through row does not rewrite class to transfer', (tester) async {
    final raw = EditLookupsHttp();
    final controller = await _controller(raw);
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => TransactionEditScreen(
                    controller: controller,
                    existing: _tx(),
                  ),
                ),
              );
            },
            child: const Text('Open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(raw.lastPatchBody, isNotNull);
    expect(raw.lastPatchBody!['movement_class'], 'pass_through');
  });
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/api/sankey_client.dart';
import 'package:odysseus_phone/screens/sankey_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:odysseus_phone/widgets/common.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SankeyHttp extends http.BaseClient {
  SankeyHttp({this.payload, this.status = 200});

  final Map<String, dynamic>? payload;
  final int status;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    Object body = payload ??
        {
          'month': '2026-06',
          'income_cents': 100000,
          'nodes': [
            {'id': 'income', 'label': 'Income', 'cents': 100000, 'kind': 'income'},
            {
              'id': 'g1',
              'label': 'Groceries',
              'cents': 4000,
              'kind': 'category',
              'category_id': 'g1',
              'color': '#27ae60',
            },
            {'id': 'leftover', 'label': 'Leftover', 'cents': 96000, 'kind': 'leftover'},
          ],
          'links': [
            {'source': 'income', 'target': 'g1', 'cents': 4000},
            {'source': 'income', 'target': 'leftover', 'cents': 96000},
          ],
          'unclassified_count': 0,
          'unclassified_outflow_cents': 0,
          'incomplete': false,
        };
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      status,
      headers: {'content-type': 'application/json'},
    );
  }
}

Future<AppController> _controller(http.Client raw, {bool privacy = false}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: raw);
  controller.privacyMode = privacy;
  controller.finance = FinanceClient(
    OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: raw),
  );
  return controller;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('SankeyReport.fromJson reads leftover and incomplete', () {
    final report = SankeyReport.fromJson({
      'month': '2026-06',
      'income_cents': 100000,
      'nodes': [
        {'id': 'income', 'label': 'Income', 'cents': 100000, 'kind': 'income'},
        {'id': 'g1', 'label': 'Groceries', 'cents': 4000, 'kind': 'category', 'category_id': 'g1'},
        {'id': 'leftover', 'label': 'Leftover', 'cents': 96000, 'kind': 'leftover'},
        {'id': 'unclassified', 'label': 'Unclassified', 'cents': 4000, 'kind': 'unclassified'},
      ],
      'links': [
        {'source': 'income', 'target': 'g1', 'cents': 4000},
        {'source': 'income', 'target': 'leftover', 'cents': 96000},
      ],
      'unclassified_count': 1,
      'unclassified_outflow_cents': 4000,
      'incomplete': true,
    });
    expect(report.incomeCents, 100000);
    expect(report.incomplete, isTrue);
    expect(report.categoryNodes.single.label, 'Groceries');
    expect(report.leftoverNode!.cents, 96000);
    expect(report.unclassifiedCount, 1);
  });

  testWidgets('shows income, groceries, leftover', (tester) async {
    final controller = await _controller(SankeyHttp());
    await tester.pumpWidget(MaterialApp(home: SankeyScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('Income'), findsWidgets);
    expect(find.textContaining('Groceries'), findsWidgets);
    expect(find.textContaining('Leftover'), findsWidgets);
  });

  testWidgets('incomplete banner', (tester) async {
    final raw = SankeyHttp(payload: {
      'month': '2026-06',
      'income_cents': 100000,
      'nodes': [
        {'id': 'income', 'label': 'Income', 'cents': 100000, 'kind': 'income'},
        {'id': 'unclassified', 'label': 'Unclassified', 'cents': 4000, 'kind': 'unclassified'},
      ],
      'links': [],
      'unclassified_count': 2,
      'unclassified_outflow_cents': 4000,
      'incomplete': true,
    });
    final controller = await _controller(raw);
    await tester.pumpWidget(MaterialApp(home: SankeyScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('incomplete'), findsWidgets);
  });

  testWidgets('privacy masks money', (tester) async {
    final controller = await _controller(SankeyHttp(), privacy: true);
    await tester.pumpWidget(MaterialApp(home: SankeyScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text(money(100000, privacy: true)), findsWidgets);
    expect(find.textContaining(r'$1,000.00'), findsNothing);
  });

  testWidgets('empty month copy', (tester) async {
    final raw = SankeyHttp(payload: {
      'month': '2026-06',
      'income_cents': 0,
      'nodes': [
        {'id': 'income', 'label': 'Income', 'cents': 0, 'kind': 'income'},
      ],
      'links': [],
      'unclassified_count': 0,
      'unclassified_outflow_cents': 0,
      'incomplete': false,
    });
    final controller = await _controller(raw);
    await tester.pumpWidget(MaterialApp(home: SankeyScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('No cashflow'), findsOneWidget);
  });

  testWidgets('error body on HTTP failure', (tester) async {
    final controller = await _controller(SankeyHttp(status: 500, payload: {'detail': 'boom'}));
    await tester.pumpWidget(MaterialApp(home: SankeyScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Retry'), findsOneWidget);
  });
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/recurring_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

class RecurringHttp extends http.BaseClient {
  RecurringHttp(this.series);

  List<Map<String, dynamic>> series;
  final patches = <Map<String, dynamic>>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    Object body = {'ok': true};
    final path = request.url.path;
    if (request.method == 'PATCH' && path.contains('/recurring/')) {
      final raw = await request.finalize().toBytes();
      final decoded = jsonDecode(utf8.decode(raw)) as Map<String, dynamic>;
      patches.add(decoded);
      final id = path.split('/').last;
      final status = decoded['status'];
      if (status == 'dismissed') {
        series = series.where((s) => s['id'] != id).toList();
      } else {
        series = [
          for (final s in series)
            if (s['id'] == id) {...s, 'status': status} else s,
        ];
      }
      body = {'id': id, 'status': status};
    } else if (path.endsWith('/recurring')) {
      body = {'series': series};
    } else if (path.endsWith('/categories')) {
      body = {
        'categories': [
          {
            'id': 'subs',
            'name': 'Subscriptions',
            'is_income': false,
            'color': '#3498db',
          },
        ]
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

Future<AppController> _controller(RecurringHttp httpClient) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: httpClient);
  controller.finance = FinanceClient(
    OdyHttp(baseUrl: 'http://test:7000', token: 'ody_test', client: httpClient),
  );
  return controller;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Ignore PATCHes dismissed and removes the row', (tester) async {
    final httpClient = RecurringHttp([
      {
        'id': 's1',
        'display_payee': 'NETFLIX',
        'cadence': 'monthly',
        'median_amount_cents': -1600,
        'monthly_normalized_cents': -1600,
        'status': 'active',
      },
    ]);
    final controller = await _controller(httpClient);
    await tester.pumpWidget(MaterialApp(home: RecurringScreen(controller: controller)));
    await tester.pumpAndSettle();
    expect(find.text('Ignore'), findsOneWidget);
    expect(find.text('paused'), findsNothing);
    expect(find.text('ignored'), findsNothing);
    expect(find.text('Ignored'), findsNothing);

    await tester.tap(find.widgetWithText(ChoiceChip, 'Ignore'));
    await tester.pumpAndSettle();
    expect(httpClient.patches.single['status'], 'dismissed');
    expect(find.text('NETFLIX'), findsNothing);
  });

  testWidgets('Automatic PATCHes automatic with spend and Subscriptions', (tester) async {
    final httpClient = RecurringHttp([
      {
        'id': 's1',
        'display_payee': 'NETFLIX',
        'cadence': 'monthly',
        'median_amount_cents': -1600,
        'monthly_normalized_cents': -1600,
        'status': 'active',
      },
    ]);
    final controller = await _controller(httpClient);
    await tester.pumpWidget(MaterialApp(home: RecurringScreen(controller: controller)));
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(ChoiceChip, 'Automatic'));
    await tester.pumpAndSettle();
    expect(httpClient.patches.single, {
      'status': 'automatic',
      'category_id': 'subs',
      'movement_class': 'spend',
    });
    expect(find.text('NETFLIX'), findsOneWidget);
    expect(
      tester.widget<ChoiceChip>(find.widgetWithText(ChoiceChip, 'Automatic')).selected,
      isTrue,
    );
  });

  testWidgets('dismissed series stay off the Recurring list', (tester) async {
    final httpClient = RecurringHttp([
      {
        'id': 's1',
        'display_payee': 'GYM',
        'cadence': 'monthly',
        'median_amount_cents': -5000,
        'monthly_normalized_cents': -5000,
        'status': 'dismissed',
      },
      {
        'id': 's2',
        'display_payee': 'SPOTIFY',
        'cadence': 'monthly',
        'median_amount_cents': -999,
        'monthly_normalized_cents': -999,
        'status': 'active',
      },
    ]);
    final controller = await _controller(httpClient);
    await tester.pumpWidget(MaterialApp(home: RecurringScreen(controller: controller)));
    await tester.pumpAndSettle();
    expect(find.text('GYM'), findsNothing);
    expect(find.text('SPOTIFY'), findsOneWidget);
    expect(
      tester.widget<ChoiceChip>(find.widgetWithText(ChoiceChip, 'Active')).selected,
      isTrue,
    );
  });
}

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/goals_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:odysseus_phone/theme/ody_theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

class GoalsHttp extends http.BaseClient {
  GoalsHttp({this.failGoals = false, this.goals = const []});

  final bool failGoals;
  final List<Map<String, dynamic>> goals;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final path = request.url.path;
    Object body = {'ok': true};
    var status = 200;
    if (path.endsWith('/accounts')) {
      body = {
        'accounts': [
          {'id': 'a1', 'name': 'Savings', 'posted_cents': 250000, 'balance_cents': 250000},
        ]
      };
    } else if (path.endsWith('/categories')) {
      body = {'categories': []};
    } else if (path.contains('/goals')) {
      if (failGoals) {
        status = 500;
        body = {'detail': 'boom'};
      } else {
        body = {'goals': goals};
      }
    }
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      status,
      headers: {'content-type': 'application/json'},
    );
  }
}

Future<AppController> _controller(http.Client client, {bool privacy = false}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs, httpClient: client);
  controller.baseUrl = 'http://test:7000';
  controller.token = 'ody_test';
  controller.privacyMode = privacy;
  final httpLayer = OdyHttp(
    baseUrl: 'http://test:7000',
    token: 'ody_test',
    client: client,
  );
  controller.httpLayer = httpLayer;
  controller.finance = FinanceClient(httpLayer);
  return controller;
}

Widget _wrap(AppController controller) {
  return MaterialApp(
    theme: OdyTheme.dark(),
    home: GoalsScreen(controller: controller),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('goals list shows name and percent', (tester) async {
    final client = GoalsHttp(goals: [
      {
        'id': 'g1',
        'name': 'Emergency fund',
        'kind': 'account',
        'target_cents': 1000000,
        'current_cents': 250000,
        'remaining_cents': 750000,
        'percent': 25,
        'color': '#5b8abf',
      },
    ]);
    final controller = await _controller(client);
    await tester.pumpWidget(_wrap(controller));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Emergency fund'), findsOneWidget);
    expect(find.textContaining('25%'), findsOneWidget);
    expect(find.textContaining(r'$2,500.00'), findsWidgets);
  });

  testWidgets('goals empty copy', (tester) async {
    final controller = await _controller(GoalsHttp());
    await tester.pumpWidget(_wrap(controller));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('No goals yet'), findsOneWidget);
    expect(find.textContaining('envelopes'), findsOneWidget);
  });

  testWidgets('goals error offers retry', (tester) async {
    final controller = await _controller(GoalsHttp(failGoals: true));
    await tester.pumpWidget(_wrap(controller));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('privacy mode hides amounts', (tester) async {
    final client = GoalsHttp(goals: [
      {
        'id': 'g1',
        'name': 'Emergency fund',
        'kind': 'account',
        'target_cents': 1000000,
        'current_cents': 250000,
        'remaining_cents': 750000,
        'percent': 25,
        'color': '#5b8abf',
      },
    ]);
    final controller = await _controller(client, privacy: true);
    await tester.pumpWidget(_wrap(controller));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('Emergency fund'), findsOneWidget);
    expect(find.textContaining('••••'), findsWidgets);
    expect(find.textContaining(r'$2,500.00'), findsNothing);
  });
}

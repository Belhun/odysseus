import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:odysseus_phone/api/finance_client.dart';
import 'package:odysseus_phone/api/investing_client.dart';
import 'package:odysseus_phone/api/ody_http.dart';
import 'package:odysseus_phone/screens/investing_screen.dart';
import 'package:odysseus_phone/state/app_controller.dart';
import 'package:odysseus_phone/widgets/common.dart';
import 'package:shared_preferences/shared_preferences.dart';

class InvestHttp extends http.BaseClient {
  InvestHttp({this.assets = const [], this.summary});

  final List<Map<String, dynamic>> assets;
  final Map<String, dynamic>? summary;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final path = request.url.path;
    Object body = {'ok': true};
    if (path.endsWith('/invest/summary')) {
      body = summary ??
          {
            'total_current_value_cents': 0,
            'total_cost_basis_cents': 0,
            'unrealized_gain_cents': 0,
            'unrealized_gain_pct': null,
            'asset_count': 0,
            'allocation': [],
          };
    } else if (path.endsWith('/invest/assets')) {
      body = {'assets': assets};
    } else if (path.endsWith('/accounts')) {
      body = {'accounts': []};
    }
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([bytes]),
      200,
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

  test('millishares 1.5 is 1500', () {
    expect(millisharesFromShares('1.5'), 1500);
    expect(sharesFromMillishares(1500), '1.5');
  });

  test('InvestAsset.fromJson reads gain', () {
    final asset = InvestAsset.fromJson({
      'id': 'a1',
      'name': 'VTI',
      'symbol': 'VTI',
      'asset_kind': 'etf',
      'shares_millishares': 1500,
      'shares': '1.5',
      'cost_basis_cents': 10000,
      'current_value_cents': 12000,
      'unrealized_gain_cents': 2000,
      'unrealized_gain_pct': 20.0,
    });
    expect(asset.sharesMillishares, 1500);
    expect(asset.unrealizedGainCents, 2000);
    expect(asset.unrealizedGainPct, 20.0);
  });

  testWidgets('empty holdings copy mentions quotes', (tester) async {
    final raw = InvestHttp();
    final controller = await _controller(raw);
    await tester.pumpWidget(MaterialApp(home: InvestingScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(
      find.text(
        'No holdings yet. Add an asset and type its current value. Odysseus does not fetch quotes.',
      ),
      findsOneWidget,
    );
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  testWidgets('privacy hides holding amounts', (tester) async {
    final raw = InvestHttp(
      summary: {
        'total_current_value_cents': 12000,
        'total_cost_basis_cents': 10000,
        'unrealized_gain_cents': 2000,
        'unrealized_gain_pct': 20.0,
        'asset_count': 1,
        'allocation': [
          {'asset_kind': 'etf', 'value_cents': 12000, 'pct': 100.0},
        ],
      },
      assets: [
        {
          'id': 'a1',
          'name': 'VTI',
          'symbol': 'VTI',
          'asset_kind': 'etf',
          'shares_millishares': 1500,
          'shares': '1.5',
          'cost_basis_cents': 10000,
          'current_value_cents': 12000,
          'unrealized_gain_cents': 2000,
          'unrealized_gain_pct': 20.0,
        },
      ],
    );
    final controller = await _controller(raw, privacy: true);
    await tester.pumpWidget(MaterialApp(home: InvestingScreen(controller: controller)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('VTI (VTI)'), findsOneWidget);
    expect(find.text(money(12000, privacy: true)), findsWidgets);
    expect(find.textContaining(r'$120'), findsNothing);
  });
}

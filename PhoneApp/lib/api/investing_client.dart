import '../api/ody_http.dart';
import 'models.dart';

const millisharesPerShare = 1000;

int millisharesFromShares(String raw) {
  final text = raw.trim().replaceAll(',', '');
  if (text.isEmpty) return 0;
  final value = double.tryParse(text);
  if (value == null || value < 0) {
    throw FormatException('shares must be a number 0 or more');
  }
  return (value * millisharesPerShare).round();
}

String sharesFromMillishares(int millishares) {
  final qty = millishares / millisharesPerShare;
  if (qty == qty.roundToDouble()) return qty.toInt().toString();
  var text = qty.toStringAsFixed(3);
  while (text.contains('.') && (text.endsWith('0') || text.endsWith('.'))) {
    text = text.substring(0, text.length - 1);
  }
  return text.isEmpty ? '0' : text;
}

int? dollarsToCents(String raw) {
  final text = raw.trim().replaceAll(',', '').replaceAll(r'$', '');
  if (text.isEmpty) return 0;
  final value = double.tryParse(text);
  if (value == null || value < 0) return null;
  return (value * 100).round();
}

class InvestAsset {
  InvestAsset({
    required this.id,
    required this.name,
    required this.symbol,
    required this.assetKind,
    required this.sharesMillishares,
    required this.shares,
    required this.costBasisCents,
    required this.currentValueCents,
    required this.unrealizedGainCents,
    this.unrealizedGainPct,
    this.accountId,
    this.notes = '',
    this.archived = false,
  });

  final String id;
  final String name;
  final String symbol;
  final String assetKind;
  final int sharesMillishares;
  final String shares;
  final int costBasisCents;
  final int currentValueCents;
  final int unrealizedGainCents;
  final double? unrealizedGainPct;
  final String? accountId;
  final String notes;
  final bool archived;

  factory InvestAsset.fromJson(Map<String, dynamic> json) {
    return InvestAsset(
      id: asString(json['id']),
      name: asString(json['name']),
      symbol: asString(json['symbol']),
      assetKind: asString(json['asset_kind'], 'other'),
      sharesMillishares: asInt(json['shares_millishares']),
      shares: asString(json['shares'], sharesFromMillishares(asInt(json['shares_millishares']))),
      costBasisCents: asInt(json['cost_basis_cents']),
      currentValueCents: asInt(json['current_value_cents']),
      unrealizedGainCents: asInt(json['unrealized_gain_cents']),
      unrealizedGainPct: json['unrealized_gain_pct'] == null
          ? null
          : (json['unrealized_gain_pct'] as num).toDouble(),
      accountId: json['account_id']?.toString(),
      notes: asString(json['notes']),
      archived: asBool(json['archived']),
    );
  }
}

class InvestAllocation {
  InvestAllocation({
    required this.assetKind,
    required this.valueCents,
    required this.pct,
  });

  final String assetKind;
  final int valueCents;
  final double pct;

  factory InvestAllocation.fromJson(Map<String, dynamic> json) {
    return InvestAllocation(
      assetKind: asString(json['asset_kind']),
      valueCents: asInt(json['value_cents']),
      pct: (json['pct'] is num) ? (json['pct'] as num).toDouble() : 0,
    );
  }
}

class InvestSummary {
  InvestSummary({
    required this.totalCurrentValueCents,
    required this.totalCostBasisCents,
    required this.unrealizedGainCents,
    required this.assetCount,
    this.unrealizedGainPct,
    this.allocation = const [],
  });

  final int totalCurrentValueCents;
  final int totalCostBasisCents;
  final int unrealizedGainCents;
  final double? unrealizedGainPct;
  final int assetCount;
  final List<InvestAllocation> allocation;

  factory InvestSummary.fromJson(Map<String, dynamic> json) {
    return InvestSummary(
      totalCurrentValueCents: asInt(json['total_current_value_cents']),
      totalCostBasisCents: asInt(json['total_cost_basis_cents']),
      unrealizedGainCents: asInt(json['unrealized_gain_cents']),
      unrealizedGainPct: json['unrealized_gain_pct'] == null
          ? null
          : (json['unrealized_gain_pct'] as num).toDouble(),
      assetCount: asInt(json['asset_count']),
      allocation: (json['allocation'] as List? ?? [])
          .whereType<Map>()
          .map((e) => InvestAllocation.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }
}

class InvestingClient {
  InvestingClient(this.httpClient);

  final OdyHttp httpClient;

  Future<InvestSummary> summary() async {
    final data = await httpClient.get('/api/finance/invest/summary');
    return InvestSummary.fromJson(_asMap(data));
  }

  Future<List<InvestAsset>> listAssets({bool includeArchived = false}) async {
    final data = await httpClient.get(
      '/api/finance/invest/assets',
      query: {'include_archived': '$includeArchived'},
    );
    final map = _asMap(data);
    return (map['assets'] as List? ?? [])
        .whereType<Map>()
        .map((e) => InvestAsset.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<InvestAsset> createAsset(Map<String, dynamic> body) async {
    final data = await httpClient.sendJson('POST', '/api/finance/invest/assets', body: body);
    return InvestAsset.fromJson(_asMap(data));
  }

  Future<InvestAsset> patchAsset(String id, Map<String, dynamic> body) async {
    final data = await httpClient.sendJson('PATCH', '/api/finance/invest/assets/$id', body: body);
    return InvestAsset.fromJson(_asMap(data));
  }

  Future<void> deleteAsset(String id) async {
    await httpClient.sendJson('DELETE', '/api/finance/invest/assets/$id');
  }

  Future<InvestAsset> updateValue(
    String id, {
    required int currentValueCents,
    String? asOf,
    String? shares,
  }) async {
    final data = await httpClient.sendJson(
      'POST',
      '/api/finance/invest/assets/$id/value',
      body: {
        'current_value_cents': currentValueCents,
        if (asOf != null && asOf.isNotEmpty) 'as_of': asOf,
        if (shares != null) 'shares': shares,
      },
    );
    return InvestAsset.fromJson(_asMap(data));
  }

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return <String, dynamic>{};
  }
}

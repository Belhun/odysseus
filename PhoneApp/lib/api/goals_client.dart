import 'ody_http.dart';

class FinanceGoal {
  FinanceGoal({
    required this.id,
    required this.name,
    required this.kind,
    required this.targetCents,
    required this.currentCents,
    required this.remainingCents,
    required this.percent,
    this.targetDate,
    this.accountId,
    this.categoryId,
    this.baselineCents = 0,
    this.suggestedMonthlyCents,
    this.monthsRemaining,
    this.icon,
    this.color = '#5b8abf',
    this.archived = false,
  });

  final String id;
  final String name;
  final String kind;
  final int targetCents;
  final int currentCents;
  final int remainingCents;
  final int percent;
  final String? targetDate;
  final String? accountId;
  final String? categoryId;
  final int baselineCents;
  final int? suggestedMonthlyCents;
  final int? monthsRemaining;
  final String? icon;
  final String color;
  final bool archived;

  factory FinanceGoal.fromJson(Map<String, dynamic> json) {
    return FinanceGoal(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? ''}',
      kind: '${json['kind'] ?? 'account'}',
      targetCents: (json['target_cents'] as num?)?.toInt() ?? 0,
      currentCents: (json['current_cents'] as num?)?.toInt() ?? 0,
      remainingCents: (json['remaining_cents'] as num?)?.toInt() ?? 0,
      percent: (json['percent'] as num?)?.toInt() ?? 0,
      targetDate: json['target_date']?.toString(),
      accountId: json['account_id']?.toString(),
      categoryId: json['category_id']?.toString(),
      baselineCents: (json['baseline_cents'] as num?)?.toInt() ?? 0,
      suggestedMonthlyCents: (json['suggested_monthly_cents'] as num?)?.toInt(),
      monthsRemaining: (json['months_remaining'] as num?)?.toInt(),
      icon: json['icon']?.toString(),
      color: '${json['color'] ?? '#5b8abf'}',
      archived: json['archived'] == true,
    );
  }
}

class GoalsClient {
  GoalsClient(this.http);

  final OdyHttp http;

  Future<List<FinanceGoal>> list({bool includeArchived = false}) async {
    final data = await http.get(
      '/api/finance/goals',
      query: includeArchived ? {'include_archived': 'true'} : null,
    );
    final map = data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
    return (map['goals'] as List? ?? [])
        .whereType<Map>()
        .map((e) => FinanceGoal.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<FinanceGoal> getOne(String id) async {
    final data = await http.get('/api/finance/goals/$id');
    return FinanceGoal.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<FinanceGoal> create(Map<String, dynamic> body) async {
    final data = await http.sendJson('POST', '/api/finance/goals', body: body);
    return FinanceGoal.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<FinanceGoal> patch(String id, Map<String, dynamic> body) async {
    final data = await http.sendJson('PATCH', '/api/finance/goals/$id', body: body);
    return FinanceGoal.fromJson(Map<String, dynamic>.from(data as Map));
  }

  Future<void> delete(String id) async {
    await http.sendJson('DELETE', '/api/finance/goals/$id');
  }
}

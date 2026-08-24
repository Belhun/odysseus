import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import 'models.dart';
import 'ody_http.dart';

class FinanceClient {
  FinanceClient(this.httpClient);

  final OdyHttp httpClient;

  Future<void> ping() async {
    await httpClient.get('/api/companion/ping');
  }

  Future<Map<String, dynamic>> login({
    required String username,
    required String password,
    String? totp,
    bool remember = true,
  }) async {
    final res = await httpClient.postRaw('/api/auth/login', body: {
      'username': username,
      'password': password,
      if (totp != null && totp.isNotEmpty) 'totp_code': totp,
      'remember': remember,
    });
    final decoded = _asMap(httpClient.parseResponse(res));
    decoded['_session'] = OdyHttp.sessionCookieFromHeaders(res.headers) ?? '';
    return decoded;
  }

  Future<List<FinanceAccount>> listAccounts({bool includeClosed = false}) async {
    final data = await httpClient.get(
      '/api/finance/accounts',
      query: {'include_closed': '$includeClosed'},
    );
    return _list(data, 'accounts', FinanceAccount.fromJson);
  }

  Future<FinanceAccount> createAccount(Map<String, dynamic> body) async {
    final data = await httpClient.sendJson('POST', '/api/finance/accounts', body: body);
    return FinanceAccount.fromJson(_asMap(data));
  }

  Future<void> patchAccount(String id, Map<String, dynamic> body) async {
    await httpClient.sendJson('PATCH', '/api/finance/accounts/$id', body: body);
  }

  Future<void> deleteAccount(String id) async {
    await httpClient.sendJson('DELETE', '/api/finance/accounts/$id');
  }

  Future<List<FinanceCategory>> listCategories() async {
    final data = await httpClient.get('/api/finance/categories');
    return _list(data, 'categories', FinanceCategory.fromJson);
  }

  Future<void> createCategory({
    required String name,
    bool isIncome = false,
    String color = '#5b8abf',
  }) async {
    await httpClient.sendJson('POST', '/api/finance/categories', body: {
      'name': name,
      'is_income': isIncome,
      'color': color,
    });
  }

  Future<({int total, List<FinanceTransaction> transactions})> listTransactions({
    String? accountId,
    String search = '',
    String? categoryId,
    String? month,
    bool unclassified = false,
    bool uncategorized = false,
    int limit = 100,
    int offset = 0,
  }) async {
    final q = <String, String>{
      'limit': '$limit',
      'offset': '$offset',
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      if (search.isNotEmpty) 'search': search,
      if (categoryId != null && categoryId.isNotEmpty) 'category_id': categoryId,
      if (month != null && month.isNotEmpty) 'month': month,
      if (unclassified) 'unclassified': 'true',
      if (uncategorized) 'uncategorized': 'true',
    };
    final data = await httpClient.get('/api/finance/transactions', query: q);
    final map = _asMap(data);
    final txs = (map['transactions'] as List? ?? [])
        .whereType<Map>()
        .map((e) => FinanceTransaction.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return (total: asInt(map['total']), transactions: txs);
  }

  Future<void> createTransaction(Map<String, dynamic> body) async {
    await httpClient.sendJson('POST', '/api/finance/transactions', body: body);
  }

  Future<void> patchTransaction(String id, Map<String, dynamic> body) async {
    await httpClient.sendJson('PATCH', '/api/finance/transactions/$id', body: body);
  }

  Future<void> deleteTransaction(String id) async {
    await httpClient.sendJson('DELETE', '/api/finance/transactions/$id');
  }

  Future<void> classifyTransaction(String id, String movementClass) async {
    await httpClient.sendJson(
      'POST',
      '/api/finance/transactions/$id/classify',
      body: {'movement_class': movementClass},
    );
  }

  Future<BudgetSnapshot> budgets({String? month, String? accountId}) async {
    final data = await httpClient.get('/api/finance/budgets', query: {
      if (month != null) 'month': month,
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
    });
    return BudgetSnapshot.fromJson(_asMap(data));
  }

  Future<void> setBudget({
    required String categoryId,
    required String month,
    required int limitCents,
  }) async {
    await httpClient.sendJson('PUT', '/api/finance/budgets', body: {
      'category_id': categoryId,
      'month': month,
      'limit_cents': limitCents,
    });
  }

  Future<void> copyBudgets({required String fromMonth, required String toMonth}) async {
    await httpClient.sendJson('POST', '/api/finance/budgets/copy', body: {
      'from_month': fromMonth,
      'to_month': toMonth,
    });
  }

  Future<void> setIncomeTarget({required String month, required int cents}) async {
    await httpClient.sendJson('PUT', '/api/finance/budgets/income-target', body: {
      'month': month,
      'income_target_cents': cents,
    });
  }

  Future<List<RecurringSeries>> recurring() async {
    final data = await httpClient.get('/api/finance/recurring');
    return _list(data, 'series', RecurringSeries.fromJson);
  }

  Future<void> patchRecurring(String id, Map<String, dynamic> body) async {
    await httpClient.sendJson('PATCH', '/api/finance/recurring/$id', body: body);
  }

  Future<BudgetSnapshot> reportSpending({String? month}) async {
    final data = await httpClient.get('/api/finance/reports/spending', query: {
      if (month != null) 'month': month,
    });
    return BudgetSnapshot.fromJson(_asMap(data));
  }

  Future<List<TrendPoint>> reportTrends({int months = 6}) async {
    final data = await httpClient.get('/api/finance/reports/trends', query: {
      'months': '$months',
    });
    final map = _asMap(data);
    return (map['trends'] as List? ?? [])
        .whereType<Map>()
        .map((e) => TrendPoint.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<Map<String, dynamic>> reportCashflow({String? month}) async {
    final data = await httpClient.get('/api/finance/reports/cashflow', query: {
      if (month != null) 'month': month,
    });
    return _asMap(data);
  }

  Future<List<Map<String, dynamic>>> spendByAccount({String? month}) async {
    final data = await httpClient.get('/api/finance/reports/spend-by-account', query: {
      if (month != null) 'month': month,
    });
    final map = _asMap(data);
    return (map['accounts'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
  }

  Future<NetWorth> netWorth() async {
    final data = await httpClient.get('/api/finance/reports/net-worth');
    return NetWorth.fromJson(_asMap(data));
  }

  Future<ImportPreview> importPreview({
    required String accountId,
    required String filename,
    required List<int> bytes,
  }) async {
    final req = http.MultipartRequest(
      'POST',
      httpClient.uri('/api/finance/import/preview'),
    );
    req.fields['account_id'] = accountId;
    req.files.add(http.MultipartFile.fromBytes(
      'file',
      bytes,
      filename: filename,
      contentType: MediaType('text', 'csv'),
    ));
    final streamed = await httpClient.sendMultipart(req);
    final res = await http.Response.fromStream(streamed);
    return ImportPreview.fromJson(_asMap(httpClient.parseResponse(res)));
  }

  Future<Map<String, dynamic>> importCommit(String previewId) async {
    final data = await httpClient.sendJson('POST', '/api/finance/import/commit', body: {
      'preview_id': previewId,
      'skip_duplicates': true,
    });
    return _asMap(data);
  }

  Future<List<ImportBatch>> importBatches() async {
    final data = await httpClient.get('/api/finance/import/batches');
    return _list(data, 'batches', ImportBatch.fromJson);
  }

  Future<void> rollbackBatch(String id) async {
    await httpClient.sendJson('DELETE', '/api/finance/import/batches/$id');
  }

  Future<List<CategorizationRule>> rules() async {
    final data = await httpClient.get('/api/finance/rules');
    return _list(data, 'rules', CategorizationRule.fromJson);
  }

  Future<void> createRule({
    required String pattern,
    String? categoryId,
    String? movementClass,
  }) async {
    await httpClient.sendJson('POST', '/api/finance/rules', body: {
      'pattern': pattern,
      if (categoryId != null) 'category_id': categoryId,
      if (movementClass != null) 'movement_class': movementClass,
      'apply_existing': true,
    });
  }

  Future<void> deleteRule(String id) async {
    await httpClient.sendJson('DELETE', '/api/finance/rules/$id');
  }

  List<T> _list<T>(
    dynamic data,
    String key,
    T Function(Map<String, dynamic>) parse,
  ) {
    final map = _asMap(data);
    return (map[key] as List? ?? [])
        .whereType<Map>()
        .map((e) => parse(Map<String, dynamic>.from(e)))
        .toList();
  }

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return <String, dynamic>{};
  }
}

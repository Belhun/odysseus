int asInt(dynamic v, [int fallback = 0]) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? fallback;
}

String asString(dynamic v, [String fallback = '']) {
  if (v == null) return fallback;
  return '$v';
}

bool asBool(dynamic v, [bool fallback = false]) {
  if (v is bool) return v;
  if (v is num) return v != 0;
  final s = '$v'.toLowerCase();
  if (s == 'true' || s == '1') return true;
  if (s == 'false' || s == '0') return false;
  return fallback;
}

class FinanceAccount {
  FinanceAccount({
    required this.id,
    required this.name,
    required this.institution,
    required this.accountType,
    required this.purpose,
    required this.currency,
    required this.balanceCents,
    required this.postedCents,
    this.maskLast4,
    this.isClosed = false,
    this.creditLimitCents,
  });

  final String id;
  final String name;
  final String institution;
  final String accountType;
  final String purpose;
  final String currency;
  final int balanceCents;
  final int postedCents;
  final String? maskLast4;
  final bool isClosed;
  final int? creditLimitCents;

  factory FinanceAccount.fromJson(Map<String, dynamic> json) {
    return FinanceAccount(
      id: asString(json['id']),
      name: asString(json['name']),
      institution: asString(json['institution']),
      accountType: asString(json['account_type'], 'checking'),
      purpose: asString(json['purpose'], 'operating'),
      currency: asString(json['currency'], 'USD'),
      balanceCents: asInt(json['balance_cents'] ?? json['posted_cents']),
      postedCents: asInt(json['posted_cents'] ?? json['balance_cents']),
      maskLast4: json['mask_last4']?.toString(),
      isClosed: asBool(json['is_closed']),
      creditLimitCents: json['credit_limit_cents'] == null
          ? null
          : asInt(json['credit_limit_cents']),
    );
  }
}

class FinanceCategory {
  FinanceCategory({
    required this.id,
    required this.name,
    required this.displayName,
    required this.isIncome,
    required this.color,
    this.parentId,
  });

  final String id;
  final String name;
  final String displayName;
  final bool isIncome;
  final String color;
  final String? parentId;

  factory FinanceCategory.fromJson(Map<String, dynamic> json) {
    return FinanceCategory(
      id: asString(json['id']),
      name: asString(json['name']),
      displayName: asString(json['display_name'] ?? json['name']),
      isIncome: asBool(json['is_income']),
      color: asString(json['color'], '#5b8abf'),
      parentId: json['parent_id']?.toString(),
    );
  }
}

class FinanceTransaction {
  FinanceTransaction({
    required this.id,
    required this.accountId,
    required this.amountCents,
    required this.payee,
    required this.status,
    this.date,
    this.memo = '',
    this.categoryId,
    this.categoryName,
    this.movementClass,
    this.isManual = false,
    this.isLinked = false,
  });

  final String id;
  final String accountId;
  final String? date;
  final int amountCents;
  final String payee;
  final String memo;
  final String? categoryId;
  final String? categoryName;
  final String status;
  final String? movementClass;
  final bool isManual;
  final bool isLinked;

  factory FinanceTransaction.fromJson(Map<String, dynamic> json) {
    return FinanceTransaction(
      id: asString(json['id']),
      accountId: asString(json['account_id']),
      date: json['date']?.toString(),
      amountCents: asInt(json['amount_cents']),
      payee: asString(json['payee']),
      memo: asString(json['memo']),
      categoryId: json['category_id']?.toString(),
      categoryName: json['category_name']?.toString(),
      status: asString(json['status'], 'cleared'),
      movementClass: json['movement_class']?.toString(),
      isManual: asBool(json['is_manual']),
      isLinked: asBool(json['is_linked']),
    );
  }
}

class BudgetCategoryRow {
  BudgetCategoryRow({
    required this.categoryName,
    required this.spentCents,
    required this.transactionCount,
    this.categoryId,
    this.color,
    this.limitCents,
    this.remainingCents,
  });

  final String? categoryId;
  final String categoryName;
  final String? color;
  final int spentCents;
  final int transactionCount;
  final int? limitCents;
  final int? remainingCents;

  factory BudgetCategoryRow.fromJson(Map<String, dynamic> json) {
    return BudgetCategoryRow(
      categoryId: json['category_id']?.toString(),
      categoryName: asString(json['category_name'], 'Uncategorized'),
      color: json['color']?.toString(),
      spentCents: asInt(json['spent_cents']),
      transactionCount: asInt(json['transaction_count']),
      limitCents: json['limit_cents'] == null ? null : asInt(json['limit_cents']),
      remainingCents:
          json['remaining_cents'] == null ? null : asInt(json['remaining_cents']),
    );
  }
}

class BudgetSnapshot {
  BudgetSnapshot({
    required this.month,
    required this.categories,
    required this.incomeCents,
    required this.netSpendCents,
    required this.personalSpendCents,
    required this.unclassifiedCount,
    this.incomeTargetCents,
    this.incomplete = false,
  });

  final String month;
  final List<BudgetCategoryRow> categories;
  final int incomeCents;
  final int netSpendCents;
  final int personalSpendCents;
  final int unclassifiedCount;
  final int? incomeTargetCents;
  final bool incomplete;

  factory BudgetSnapshot.fromJson(Map<String, dynamic> json) {
    final cats = (json['categories'] as List? ?? [])
        .whereType<Map>()
        .map((e) => BudgetCategoryRow.fromJson(Map<String, dynamic>.from(e)))
        .toList();
    return BudgetSnapshot(
      month: asString(json['month']),
      categories: cats,
      incomeCents: asInt(json['income_cents']),
      netSpendCents: asInt(json['net_spend_cents'] ?? json['spending_cents']),
      personalSpendCents: asInt(json['personal_spend_cents'] ?? json['net_spend_cents']),
      unclassifiedCount: asInt(json['unclassified_count']),
      incomeTargetCents: json['income_target_cents'] == null
          ? null
          : asInt(json['income_target_cents']),
      incomplete: asBool(json['incomplete']),
    );
  }
}

class RecurringSeries {
  RecurringSeries({
    required this.id,
    required this.displayPayee,
    required this.cadence,
    required this.medianAmountCents,
    required this.monthlyNormalizedCents,
    required this.status,
    this.nextDueDate,
    this.categoryId,
    this.movementClass,
    this.skipReason,
  });

  final String id;
  final String displayPayee;
  final String cadence;
  final int medianAmountCents;
  final int monthlyNormalizedCents;
  final String status;
  final String? nextDueDate;
  final String? categoryId;
  final String? movementClass;
  final String? skipReason;

  bool get canMarkAutomatic => skipReason == null || skipReason!.isEmpty;

  factory RecurringSeries.fromJson(Map<String, dynamic> json) {
    return RecurringSeries(
      id: asString(json['id']),
      displayPayee: asString(json['display_payee']),
      cadence: asString(json['cadence'], 'monthly'),
      medianAmountCents: asInt(json['median_amount_cents']),
      monthlyNormalizedCents: asInt(json['monthly_normalized_cents']),
      status: asString(json['status'], 'active'),
      nextDueDate: json['next_due_date']?.toString(),
      categoryId: json['category_id']?.toString(),
      movementClass: json['movement_class']?.toString(),
      skipReason: json['skip_reason']?.toString(),
    );
  }
}

class NetWorth {
  NetWorth({
    required this.assetsCents,
    required this.liabilitiesCents,
    required this.netWorthCents,
  });

  final int assetsCents;
  final int liabilitiesCents;
  final int netWorthCents;

  factory NetWorth.fromJson(Map<String, dynamic> json) {
    return NetWorth(
      assetsCents: asInt(json['assets_cents']),
      liabilitiesCents: asInt(json['liabilities_cents']),
      netWorthCents: asInt(json['net_worth_cents']),
    );
  }
}

class TrendPoint {
  TrendPoint({
    required this.month,
    required this.incomeCents,
    required this.spendCents,
  });

  final String month;
  final int incomeCents;
  final int spendCents;

  factory TrendPoint.fromJson(Map<String, dynamic> json) {
    return TrendPoint(
      month: asString(json['month']),
      incomeCents: asInt(json['income_cents']),
      spendCents: asInt(json['net_spend_cents'] ?? json['spending_cents'] ?? json['personal_spend_cents']),
    );
  }
}

class ImportPreview {
  ImportPreview({
    required this.previewId,
    required this.rowCount,
    required this.newCount,
    required this.duplicateCount,
    required this.errorCount,
    this.format,
    this.warning,
    this.errors = const [],
  });

  final String previewId;
  final String? format;
  final int rowCount;
  final int newCount;
  final int duplicateCount;
  final int errorCount;
  final String? warning;
  final List<String> errors;

  factory ImportPreview.fromJson(Map<String, dynamic> json) {
    final errs = <String>[];
    for (final e in json['errors'] as List? ?? []) {
      if (e is Map) {
        errs.add('${e['row']}: ${e['message']}');
      } else {
        errs.add('$e');
      }
    }
    return ImportPreview(
      previewId: asString(json['preview_id']),
      format: json['format']?.toString(),
      rowCount: asInt(json['row_count']),
      newCount: asInt(json['new_count']),
      duplicateCount: asInt(json['duplicate_count']),
      errorCount: asInt(json['error_count']),
      warning: json['warning']?.toString(),
      errors: errs,
    );
  }
}

class ImportBatch {
  ImportBatch({
    required this.id,
    required this.filename,
    required this.importedCount,
    this.accountId,
    this.createdAt,
  });

  final String id;
  final String filename;
  final int importedCount;
  final String? accountId;
  final String? createdAt;

  factory ImportBatch.fromJson(Map<String, dynamic> json) {
    return ImportBatch(
      id: asString(json['id']),
      filename: asString(json['filename']),
      importedCount: asInt(json['imported_count']),
      accountId: json['account_id']?.toString(),
      createdAt: json['created_at']?.toString(),
    );
  }
}

class CategorizationRule {
  CategorizationRule({
    required this.id,
    required this.pattern,
    required this.priority,
    this.categoryId,
    this.movementClass,
  });

  final String id;
  final String pattern;
  final int priority;
  final String? categoryId;
  final String? movementClass;

  factory CategorizationRule.fromJson(Map<String, dynamic> json) {
    return CategorizationRule(
      id: asString(json['id']),
      pattern: asString(json['pattern']),
      priority: asInt(json['priority'], 100),
      categoryId: json['category_id']?.toString(),
      movementClass: json['movement_class']?.toString(),
    );
  }
}

/// Values the phone/web class picker shows. Stored `pass_through` maps to Transfer.
const kUiMovementClasses = <String?>[
  null,
  'spend',
  'income',
  'transfer',
  'reimbursement',
];

const kTxStatuses = ['cleared', 'pending', 'reconciled', 'void'];

/// Web `_uiClassValue`: processor legs are stored as pass_through, shown as Transfer.
String? uiMovementClass(String? movementClass) {
  if (movementClass == 'pass_through') return 'transfer';
  return movementClass;
}

/// Keep pass_through on save when the user leaves Transfer selected.
String? storedMovementClass(String? uiClass, {String? original}) {
  if (uiClass == 'transfer' && original == 'pass_through') {
    return 'pass_through';
  }
  return uiClass;
}

/// DropdownButton asserts the bound value appears exactly once in [items].
T? dropdownValueIn<T>(T? value, Iterable<T?> itemValues) {
  for (final item in itemValues) {
    if (item == value) return value;
  }
  return null;
}

String currentMonthKey([DateTime? now]) {
  final d = now ?? DateTime.now();
  return '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}';
}

String previousMonthKey(String month) {
  final parts = month.split('-');
  var y = int.parse(parts[0]);
  var m = int.parse(parts[1]) - 1;
  if (m == 0) {
    m = 12;
    y -= 1;
  }
  return '${y.toString().padLeft(4, '0')}-${m.toString().padLeft(2, '0')}';
}

String normalizeBaseUrl(String raw) {
  var s = raw.trim();
  if (s.isEmpty) {
    throw FormatException('Server URL is required');
  }
  if (!s.contains('://')) {
    final host = s.split('/').first.split(':').first.toLowerCase();
    final scheme = host.endsWith('.ts.net') ? 'https' : 'http';
    s = '$scheme://$s';
  }
  while (s.endsWith('/')) {
    s = s.substring(0, s.length - 1);
  }
  final uri = Uri.parse(s);
  if (uri.host.isEmpty) {
    throw FormatException('Server URL needs a host (Tailscale IP or hostname)');
  }
  return s;
}

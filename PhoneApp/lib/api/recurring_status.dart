import 'models.dart';

/// Recurring series statuses the Odysseus API accepts.
/// See `RECURRING_STATUSES` in integrations/finance/models.py.
const kRecurringApiStatuses = ['active', 'automatic', 'dismissed'];

/// Chips on the Recurring tab. Labels are product copy; [apiStatus] is the PATCH body.
class RecurringStatusChip {
  const RecurringStatusChip({
    required this.label,
    required this.apiStatus,
  });

  final String label;
  final String apiStatus;
}

const kRecurringStatusChips = [
  RecurringStatusChip(label: 'Active', apiStatus: 'active'),
  RecurringStatusChip(label: 'Automatic', apiStatus: 'automatic'),
  RecurringStatusChip(label: 'Ignore', apiStatus: 'dismissed'),
];

bool isVisibleOnRecurringTab(RecurringSeries series) =>
    series.status != 'dismissed';

List<RecurringSeries> visibleRecurringSeries(Iterable<RecurringSeries> series) =>
    series.where(isVisibleOnRecurringTab).toList();

/// Same category pick as web Recurring: root Subscriptions, else first category.
FinanceCategory? automaticCategoryFor(List<FinanceCategory> categories) {
  for (final c in categories) {
    final parent = c.parentId;
    if ((parent == null || parent.isEmpty) && c.name == 'Subscriptions') {
      return c;
    }
  }
  return categories.isEmpty ? null : categories.first;
}

/// PATCH body for a Recurring status chip. Automatic matches web: spend + Subscriptions.
Map<String, dynamic> recurringStatusPatchBody({
  required String apiStatus,
  required List<FinanceCategory> categories,
}) {
  if (apiStatus != 'automatic') {
    return {'status': apiStatus};
  }
  final cat = automaticCategoryFor(categories);
  return {
    'status': 'automatic',
    if (cat != null) 'category_id': cat.id,
    'movement_class': 'spend',
  };
}

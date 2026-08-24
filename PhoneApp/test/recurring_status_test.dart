import 'package:flutter_test/flutter_test.dart';
import 'package:odysseus_phone/api/models.dart';
import 'package:odysseus_phone/api/recurring_status.dart';

RecurringSeries _series({required String status}) {
  return RecurringSeries(
    id: 's1',
    displayPayee: 'NETFLIX',
    cadence: 'monthly',
    medianAmountCents: -1600,
    monthlyNormalizedCents: -1600,
    status: status,
  );
}

void main() {
  test('chips send API statuses, never paused or ignored', () {
    expect(
      kRecurringStatusChips.map((c) => c.apiStatus).toList(),
      kRecurringApiStatuses,
    );
    expect(kRecurringStatusChips.map((c) => c.label).toList(), [
      'Active',
      'Automatic',
      'Ignore',
    ]);
    expect(kRecurringApiStatuses, ['active', 'automatic', 'dismissed']);
  });

  test('Ignore maps to dismissed and drops the row from the Recurring list', () {
    final ignore = kRecurringStatusChips.singleWhere((c) => c.label == 'Ignore');
    expect(ignore.apiStatus, 'dismissed');
    expect(
      recurringStatusPatchBody(apiStatus: ignore.apiStatus, categories: const []),
      {'status': 'dismissed'},
    );
    final listed = visibleRecurringSeries([
      _series(status: 'active'),
      _series(status: 'automatic'),
      _series(status: 'dismissed'),
    ]);
    expect(listed.map((s) => s.status).toList(), ['active', 'automatic']);
  });

  test('Automatic maps to automatic and sends spend plus Subscriptions', () {
    final auto = kRecurringStatusChips.singleWhere((c) => c.label == 'Automatic');
    expect(auto.apiStatus, 'automatic');
    final cats = [
      FinanceCategory(
        id: 'groceries',
        name: 'Groceries',
        displayName: 'Groceries',
        isIncome: false,
        color: '#111',
      ),
      FinanceCategory(
        id: 'subs',
        name: 'Subscriptions',
        displayName: 'Subscriptions',
        isIncome: false,
        color: '#3498db',
      ),
      FinanceCategory(
        id: 'child',
        name: 'Subscriptions',
        displayName: 'Child',
        isIncome: false,
        color: '#3498db',
        parentId: 'subs',
      ),
    ];
    expect(recurringStatusPatchBody(apiStatus: auto.apiStatus, categories: cats), {
      'status': 'automatic',
      'category_id': 'subs',
      'movement_class': 'spend',
    });
  });

  test('Active stays active', () {
    expect(
      recurringStatusPatchBody(apiStatus: 'active', categories: const []),
      {'status': 'active'},
    );
    expect(isVisibleOnRecurringTab(_series(status: 'active')), isTrue);
  });
}

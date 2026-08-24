import 'package:flutter_test/flutter_test.dart';
import 'package:odysseus_phone/api/models.dart';
import 'package:odysseus_phone/widgets/common.dart';

void main() {
  test('normalizeBaseUrl adds http and strips slash', () {
    expect(normalizeBaseUrl('100.64.0.12:7000'), 'http://100.64.0.12:7000');
    expect(normalizeBaseUrl('http://odysseus:7000/'), 'http://odysseus:7000');
  });

  test('normalizeBaseUrl uses https for Tailscale Serve hostnames', () {
    expect(
      normalizeBaseUrl('dell-mini-pc.tailcbcc46.ts.net'),
      'https://dell-mini-pc.tailcbcc46.ts.net',
    );
  });

  test('normalizeBaseUrl rejects empty host', () {
    expect(() => normalizeBaseUrl(''), throwsFormatException);
  });

  test('previousMonthKey wraps January', () {
    expect(previousMonthKey('2026-01'), '2025-12');
    expect(previousMonthKey('2026-08'), '2026-07');
  });

  test('FinanceAccount.fromJson reads balances', () {
    final a = FinanceAccount.fromJson({
      'id': 'a1',
      'name': 'Checking',
      'institution': 'WF',
      'account_type': 'checking',
      'posted_cents': 12345,
    });
    expect(a.balanceCents, 12345);
    expect(a.postedCents, 12345);
  });

  test('money privacy hides figures', () {
    expect(money(199, privacy: true), '••••');
    expect(money(-250, privacy: false), contains('2.50'));
  });
}

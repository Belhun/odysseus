import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:phone_app/main.dart';

/// Live Connect against a running Odysseus.
///
///   flutter test integration_test/connect_live_test.dart -d chrome \
///     --dart-define=ODY_URL=http://127.0.0.1:7000 \
///     --dart-define=ODY_TOKEN=ody_… \
///     --dart-define=ODY_USER=belhun \
///     --dart-define=ODY_PASSWORD=…
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const url = String.fromEnvironment('ODY_URL', defaultValue: 'http://127.0.0.1:7000');
  const token = String.fromEnvironment('ODY_TOKEN');
  const user = String.fromEnvironment('ODY_USER', defaultValue: 'belhun');
  const password = String.fromEnvironment('ODY_PASSWORD');

  testWidgets('G token Connect loads finance accounts', (tester) async {
    expect(token.startsWith('ody_'), isTrue, reason: 'pass --dart-define=ODY_TOKEN=ody_…');
    await tester.pumpWidget(const PhoneApp());
    await tester.pumpAndSettle();

    await tester.enterText(find.byKey(const Key('server-url')), url);
    await tester.enterText(find.byKey(const Key('api-token')), token);
    await tester.tap(find.byKey(const Key('connect-token')));
    await tester.pumpAndSettle(const Duration(seconds: 20));

    expect(find.text('Accounts'), findsOneWidget);
    expect(find.textContaining('Finance plugin is installed'), findsOneWidget);
  });

  testWidgets('H password Connect on this target documents cookie visibility', (
    tester,
  ) async {
    expect(password.isNotEmpty, isTrue, reason: 'pass --dart-define=ODY_PASSWORD');
    await tester.pumpWidget(const PhoneApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Password'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('server-url')), url);
    await tester.enterText(find.byKey(const Key('password-username')), user);
    await tester.enterText(find.byKey(const Key('password-password')), password);
    await tester.tap(find.byKey(const Key('connect-password')));
    await tester.pumpAndSettle(const Duration(seconds: 20));

    // Flutter web: HttpOnly cookie is invisible to Dart → stay on Connect with
    // the documented error. Native dart:io: session cookie is captured → Accounts.
    final accounts = find.text('Accounts');
    final cookieError = find.textContaining('session cookie was not visible');
    expect(
      accounts.evaluate().isNotEmpty || cookieError.evaluate().isNotEmpty,
      isTrue,
    );
  });
}

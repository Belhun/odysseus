import 'package:flutter_test/flutter_test.dart';
import 'package:phone_app/main.dart';

void main() {
  testWidgets('Connect screen shows token and password tabs', (tester) async {
    await tester.pumpWidget(const PhoneApp());
    expect(find.text('PhoneApp Connect'), findsOneWidget);
    expect(find.text('API token'), findsWidgets);
    expect(find.text('Password'), findsOneWidget);
    expect(find.text('Server URL'), findsOneWidget);
    expect(find.text('Connect with token'), findsOneWidget);
  });

  testWidgets('empty token stays on Connect and does not crash', (tester) async {
    await tester.pumpWidget(const PhoneApp());
    await tester.tap(find.text('Connect with token'));
    await tester.pump();
    expect(find.text('Paste an ody_ API token'), findsOneWidget);
    expect(find.text('PhoneApp Connect'), findsOneWidget);
  });
}

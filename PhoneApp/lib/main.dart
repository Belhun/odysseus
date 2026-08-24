import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'debug_log.dart';
import 'state/app_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  FlutterError.onError = (details) {
    odyLog('FlutterError ${details.exception}', error: details.exception, stack: details.stack);
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    odyLog('Uncaught $error', error: error, stack: stack);
    return true;
  };
  final prefs = await SharedPreferences.getInstance();
  final controller = AppController(prefs: prefs);
  odyLog('PhoneApp start restore v8 connected=${controller.isConnected}');
  await controller.restore();
  odyLog(
    'PhoneApp restored url=${controller.baseUrl} '
    'token=${controller.token.isNotEmpty} cookie=${controller.sessionCookie.isNotEmpty}',
  );
  runApp(OdysseusPhoneApp(controller: controller));
}

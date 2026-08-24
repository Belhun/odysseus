import 'package:flutter/services.dart';

import 'debug_log.dart';
import 'state/app_controller.dart';

const _method = MethodChannel('odysseus/setup_link');
const _events = EventChannel('odysseus/setup_link/events');

void listenPhoneAppSetupLinks(AppController controller) {
  _method.invokeMethod<String>('getInitialLink').then((link) {
    if (link != null && link.isNotEmpty) {
      odyLog('setup link cold-start');
      controller.applySetupLink(link);
    }
  }).catchError((Object e) {
    odyLog('setup link initial failed $e');
  });
  _events.receiveBroadcastStream().listen((event) {
    if (event is String && event.isNotEmpty) {
      odyLog('setup link warm');
      controller.applySetupLink(event);
    }
  }, onError: (Object e) {
    odyLog('setup link stream failed $e');
  });
}

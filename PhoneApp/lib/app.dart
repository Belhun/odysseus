import 'package:flutter/material.dart';

import 'app_gate.dart';
import 'state/app_controller.dart';
import 'theme/ody_theme.dart';

class OdysseusPhoneApp extends StatelessWidget {
  const OdysseusPhoneApp({super.key, required this.controller});

  final AppController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final themeMode = switch (controller.themeIndex) {
          1 => ThemeMode.light,
          2 => ThemeMode.system,
          _ => ThemeMode.dark,
        };
        return MaterialApp(
          title: 'Odysseus',
          debugShowCheckedModeBanner: false,
          theme: OdyTheme.light(),
          darkTheme: OdyTheme.dark(),
          themeMode: themeMode,
          home: AppGate(controller: controller),
        );
      },
    );
  }
}

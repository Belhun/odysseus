import 'package:flutter/material.dart';

/// Odysseus web tokens from `static/style.css` (`:root` / `:root.light`).
class OdyColors {
  static const bg = Color(0xFF282C34);
  static const fg = Color(0xFF9CDEF2);
  static const panel = Color(0xFF111111);
  static const border = Color(0xFF355A66);
  static const red = Color(0xFFE06C75);
  static const green = Color(0xFF50FA7B);
  static const warn = Color(0xFFF0AD4E);
  static const accent = Color(0xFF00AAFF);
  static const muted = Color(0xFF888888);
  static const subheader = Color(0xFF6B8A94);
  static const hlBg = Color(0xFF1E2228);

  static const lightBg = Color(0xFFF5F5F5);
  static const lightFg = Color(0xFF2B2B2B);
  static const lightPanel = Color(0xFFFFFFFF);
  static const lightBorder = Color(0xFFBBBBBB);
}

class OdyTheme {
  static ThemeData dark() => _build(
        brightness: Brightness.dark,
        bg: OdyColors.bg,
        fg: OdyColors.fg,
        panel: OdyColors.panel,
        border: OdyColors.border,
        muted: OdyColors.muted,
      );

  static ThemeData light() => _build(
        brightness: Brightness.light,
        bg: OdyColors.lightBg,
        fg: OdyColors.lightFg,
        panel: OdyColors.lightPanel,
        border: OdyColors.lightBorder,
        muted: const Color(0xFF6B7280),
      );

  static ThemeData _build({
    required Brightness brightness,
    required Color bg,
    required Color fg,
    required Color panel,
    required Color border,
    required Color muted,
  }) {
    final scheme = ColorScheme(
      brightness: brightness,
      primary: OdyColors.red,
      onPrimary: Colors.white,
      secondary: OdyColors.accent,
      onSecondary: Colors.black,
      error: OdyColors.red,
      onError: Colors.white,
      surface: panel,
      onSurface: fg,
      surfaceContainerHighest: bg,
      outline: border,
    );
    final base = ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: bg,
      fontFamily: 'monospace',
    );
    return base.copyWith(
      appBarTheme: AppBarTheme(
        backgroundColor: panel,
        foregroundColor: fg,
        elevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: fg,
          fontSize: 18,
          fontWeight: FontWeight.w600,
          fontFamily: 'monospace',
        ),
      ),
      cardTheme: CardThemeData(
        color: panel,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(color: border),
        ),
      ),
      dividerColor: border,
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: OdyColors.red,
        foregroundColor: Colors.white,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: panel,
        indicatorColor: OdyColors.red.withValues(alpha: 0.22),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            fontSize: 11,
            fontFamily: 'monospace',
            color: selected ? OdyColors.red : muted,
          );
        }),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return IconThemeData(color: selected ? OdyColors.red : muted, size: 22);
        }),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: bg,
        labelStyle: TextStyle(color: muted),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide(color: border),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: BorderRadius.all(Radius.circular(8)),
          borderSide: BorderSide(color: OdyColors.accent),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: panel,
        contentTextStyle: TextStyle(color: fg, fontFamily: 'monospace'),
      ),
    );
  }
}

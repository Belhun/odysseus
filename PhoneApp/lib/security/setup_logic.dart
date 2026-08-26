import '../connect_logic.dart';

/// Pure validation for first-time PhoneApp setup.
class SetupLogic {
  /// Server URL, username, and ody_ token (password entered separately at login).
  static String? validateProfile({
    required String url,
    required String username,
    required String token,
  }) {
    final urlErr = ConnectLogic.validateServerUrl(url);
    if (urlErr != null) return urlErr;
    if (username.trim().isEmpty) return 'Username is required';
    return ConnectLogic.validateToken(token);
  }

  static String? validateLogin({required String password}) {
    if (password.isEmpty) return 'Password is required';
    return null;
  }

  /// Full first-time submit: profile fields plus password.
  static String? validate({
    required String url,
    required String username,
    required String password,
    required String token,
  }) {
    final profile = validateProfile(url: url, username: username, token: token);
    if (profile != null) return profile;
    return validateLogin(password: password);
  }
}

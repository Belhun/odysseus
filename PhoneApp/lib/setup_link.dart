class PhoneAppSetupLink {
  const PhoneAppSetupLink({
    required this.url,
    this.token = '',
    this.user = '',
  });

  final String url;
  final String token;
  final String user;

  static const scheme = 'odyphone';

  static PhoneAppSetupLink? tryParse(String raw) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null || uri.scheme != scheme) return null;
    final url = uri.queryParameters['url']?.trim() ?? '';
    if (url.isEmpty) return null;
    return PhoneAppSetupLink(
      url: url,
      token: uri.queryParameters['token']?.trim() ?? '',
      user: uri.queryParameters['user']?.trim() ?? '',
    );
  }
}

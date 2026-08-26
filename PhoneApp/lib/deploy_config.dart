/// Build-time deploy hints from --dart-define / .ody_dart_defines.json.
/// No real hostnames in source; set ODY_URL, ODY_MAGICDNS_HOST, ODY_TAILSCALE_IP locally.
class DeployConfig {
  static const defaultUrl = String.fromEnvironment('ODY_URL', defaultValue: '');
  static const magicDnsHost =
      String.fromEnvironment('ODY_MAGICDNS_HOST', defaultValue: '');
  static const tailscaleIp =
      String.fromEnvironment('ODY_TAILSCALE_IP', defaultValue: '');
  static const defaultUser = String.fromEnvironment('ODY_USER', defaultValue: '');

  /// MagicDNS → Tailscale IP when Android Private DNS blocks *.ts.net resolution.
  static Map<String, String> get magicDnsIpOverrides {
    final host = magicDnsHost.trim();
    final ip = tailscaleIp.trim();
    if (host.isEmpty || ip.isEmpty) return const {};
    return {host: ip};
  }

  static String get connectUrlPlaceholder =>
      defaultUrl.isNotEmpty ? defaultUrl : 'https://your-host.tailXXXXXX.ts.net';
}

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http/io_client.dart';

import '../debug_log.dart';
import '../deploy_config.dart';

Map<String, String> get magicDnsFallbackIps => DeployConfig.magicDnsIpOverrides;

bool odyUsesRawHttps(Uri uri) => magicDnsFallbackIps.containsKey(uri.host);

final _pool = _TunHttpsPool();

http.Client createOdyClient({String? connectIp}) {
  return _ResolveHttpsClient(connectIp: connectIp);
}

class _ResolveHttpsClient extends http.BaseClient {
  _ResolveHttpsClient({this.connectIp});

  final String? connectIp;
  final http.Client _inner = IOClient();

  InternetAddress? _overrideFor(String host) {
    final extra = connectIp?.trim();
    if (extra != null && extra.isNotEmpty) {
      return InternetAddress.tryParse(extra);
    }
    final mapped = magicDnsFallbackIps[host.toLowerCase()];
    return mapped == null ? null : InternetAddress.tryParse(mapped);
  }

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final addr = _overrideFor(request.url.host);
    if (addr == null || request.url.scheme != 'https') {
      return _inner.send(request);
    }
    odyLog('raw-https ${request.method} ${request.url} via ${addr.address}');
    final bodyBytes = await request.finalize().fold<BytesBuilder>(
      BytesBuilder(copy: false),
      (b, chunk) {
        b.add(chunk);
        return b;
      },
    ).then((b) => b.takeBytes());
    final res = await httpsViaIp(
      method: request.method,
      url: request.url,
      addr: addr,
      headers: request.headers,
      body: bodyBytes,
    );
    return http.StreamedResponse(
      Stream<List<int>>.fromIterable([res.bodyBytes]),
      res.statusCode,
      contentLength: res.bodyBytes.length,
      request: request,
      headers: res.headers,
      reasonPhrase: res.reasonPhrase,
    );
  }

  @override
  void close() {
    _inner.close();
  }
}

Future<http.Response> httpsViaIp({
  required String method,
  required Uri url,
  required InternetAddress addr,
  required Map<String, String> headers,
  required List<int> body,
}) {
  return _pool.request(method: method, url: url, addr: addr, headers: headers, body: body);
}

/// Pixel Tailscale accepts the first TCP 443 from tun0, then black-holes a
/// second connect(). Keep one TLS session and HTTP/1.1 keep-alive instead.
class _TunHttpsPool {
  Future<void> _busy = Future.value();
  SecureSocket? _tls;
  StreamIterator<Uint8List>? _iter;
  final _buf = <int>[];
  String? _key;
  InternetAddress? _tunSrc;
  InternetAddress? _lastAddr;
  Uri? _lastUrl;
  Map<String, String>? _lastHeaders;
  Timer? _heartbeat;

  Future<http.Response> request({
    required String method,
    required Uri url,
    required InternetAddress addr,
    required Map<String, String> headers,
    required List<int> body,
  }) {
    final done = Completer<http.Response>();
    _busy = _busy.catchError((_) {}).then((_) async {
      try {
        done.complete(await _roundTrip(method, url, addr, headers, body, retry: true));
      } catch (e, st) {
        done.completeError(e, st);
      }
    });
    return done.future;
  }

  Future<http.Response> _roundTrip(
    String method,
    Uri url,
    InternetAddress addr,
    Map<String, String> headers,
    List<int> body, {
    required bool retry,
  }) async {
    try {
      await _ensure(addr, url.host, url.hasPort ? url.port : 443);
      _lastAddr = addr;
      _lastUrl = url;
      _lastHeaders = headers;
      return await _writeRead(method, url, headers, body);
    } catch (e) {
      odyLog('raw-https session error $e');
      await _drop();
      if (!retry) rethrow;
      await Future<void>.delayed(const Duration(milliseconds: 200));
      return _roundTrip(method, url, addr, headers, body, retry: false);
    }
  }

  Future<InternetAddress?> _tun4() async {
    if (_tunSrc != null) return _tunSrc;
    for (final nic in await NetworkInterface.list(type: InternetAddressType.IPv4)) {
      odyLog('nic ${nic.name} ${nic.addresses.map((a) => a.address).join(',')}');
      for (final a in nic.addresses) {
        if (a.address.startsWith('100.')) _tunSrc = a;
      }
    }
    return _tunSrc;
  }

  Future<void> _ensure(InternetAddress addr, String host, int port) async {
    final key = '${addr.address}:$port@$host';
    if (_tls != null && _key == key) return;
    await _drop();
    final src = await _tun4();
    odyLog('tls connect dest=${addr.address}:$port sni=$host src=${src?.address ?? 'default'}');
    final raw = await Socket.connect(
      addr,
      port,
      sourceAddress: src,
      timeout: const Duration(seconds: 12),
    );
    _tls = await SecureSocket.secure(
      raw,
      host: host,
      supportedProtocols: const ['http/1.1'],
      onBadCertificate: (cert) {
        odyLog('tls cert host=$host subject=${cert.subject}');
        return host.endsWith('.ts.net');
      },
    ).timeout(const Duration(seconds: 12));
    odyLog('tls alpn=${_tls!.selectedProtocol ?? 'none'}');
    _iter = StreamIterator(_tls!);
    _key = key;
    _buf.clear();
  }

  Future<http.Response> _writeRead(
    String method,
    Uri url,
    Map<String, String> headers,
    List<int> body,
  ) async {
    final path = url.hasQuery ? '${url.path}?${url.query}' : (url.path.isEmpty ? '/' : url.path);
    final hdrs = <String, String>{
      ...headers,
      'Host': url.host,
      'Connection': 'keep-alive',
      'Accept-Encoding': 'identity',
    };
    if (!hdrs.keys.any((k) => k.toLowerCase() == 'content-length')) {
      if (body.isNotEmpty || method == 'POST' || method == 'PUT' || method == 'PATCH') {
        hdrs['Content-Length'] = '${body.length}';
      }
    }
    final req = StringBuffer()
      ..write(method)
      ..write(' ')
      ..write(path)
      ..write(' HTTP/1.1\r\n');
    hdrs.forEach((k, v) {
      req.write(k);
      req.write(': ');
      req.write(v);
      req.write('\r\n');
    });
    req.write('\r\n');
    _tls!.add(ascii.encode(req.toString()));
    if (body.isNotEmpty) _tls!.add(body);
    await _tls!.flush();

    while (_indexOfHeaderEnd(_buf) < 0) {
      await _readChunk();
    }
    final split = _indexOfHeaderEnd(_buf);
    final head = ascii.decode(_buf.sublist(0, split));
    _buf.removeRange(0, split + 4);
    final lines = head.split('\r\n');
    final status = int.tryParse(lines.first.split(' ').elementAt(1)) ?? 0;
    final reason = lines.first.split(' ').skip(2).join(' ');
    final respHeaders = <String, String>{};
    for (final line in lines.skip(1)) {
      final i = line.indexOf(':');
      if (i > 0) {
        respHeaders[line.substring(0, i).toLowerCase()] = line.substring(i + 1).trim();
      }
    }

    List<int> respBody;
    final te = respHeaders['transfer-encoding']?.toLowerCase() ?? '';
    if (te.contains('chunked')) {
      respBody = await _readChunked();
    } else {
      final n = int.tryParse(respHeaders['content-length'] ?? '') ?? -1;
      if (n < 0) {
        throw const SocketException('Mini PC HTTPS missing Content-Length');
      }
      while (_buf.length < n) {
        await _readChunk();
      }
      respBody = _buf.sublist(0, n);
      _buf.removeRange(0, n);
    }
    final ce = respHeaders['content-encoding']?.toLowerCase() ?? '';
    if (ce.contains('gzip')) {
      respBody = gzip.decode(respBody);
    }
    odyLog('raw-https -> $status $reason bytes=${respBody.length}');
    final conn = respHeaders['connection']?.toLowerCase() ?? '';
    if (conn.contains('close')) {
      await _drop();
    } else {
      _armHeartbeat();
    }
    return http.Response.bytes(respBody, status, headers: respHeaders, reasonPhrase: reason);
  }

  Future<List<int>> _readChunked() async {
    final out = BytesBuilder(copy: false);
    while (true) {
      var lineEnd = _indexOfCrlf(_buf, 0);
      while (lineEnd < 0) {
        await _readChunk();
        lineEnd = _indexOfCrlf(_buf, 0);
      }
      final sizeHex = ascii.decode(_buf.sublist(0, lineEnd)).split(';').first.trim();
      final size = int.parse(sizeHex, radix: 16);
      _buf.removeRange(0, lineEnd + 2);
      if (size == 0) {
        if (_buf.length >= 2 && _buf[0] == 13 && _buf[1] == 10) {
          _buf.removeRange(0, 2);
        }
        break;
      }
      while (_buf.length < size + 2) {
        await _readChunk();
      }
      out.add(_buf.sublist(0, size));
      _buf.removeRange(0, size + 2);
    }
    return out.takeBytes();
  }

  Future<void> _readChunk() async {
    final iter = _iter;
    if (iter == null) {
      throw const SocketException('Mini PC TLS not connected');
    }
    final ok = await iter.moveNext().timeout(const Duration(seconds: 20));
    if (!ok) {
      await _drop();
      throw const SocketException('Mini PC closed TLS');
    }
    _buf.addAll(iter.current);
  }

  void _armHeartbeat() {
    _heartbeat?.cancel();
    if (_tls == null || _lastUrl == null || _lastAddr == null) return;
    final url = _lastUrl!;
    final addr = _lastAddr!;
    final headers = Map<String, String>.from(_lastHeaders ?? const {});
    _heartbeat = Timer(const Duration(seconds: 2), () {
      request(
        method: 'GET',
        url: url.replace(path: '/api/companion/ping', query: ''),
        addr: addr,
        headers: headers,
        body: const [],
      ).then((res) {
        odyLog('heartbeat -> ${res.statusCode}');
      }).catchError((Object e) {
        odyLog('heartbeat failed $e');
      });
    });
  }

  Future<void> _drop() async {
    _heartbeat?.cancel();
    _heartbeat = null;
    _buf.clear();
    _key = null;
    try {
      await _iter?.cancel();
    } catch (_) {}
    try {
      _tls?.destroy();
    } catch (_) {}
    _iter = null;
    _tls = null;
  }
}

int _indexOfCrlf(List<int> data, int start) {
  for (var i = start; i < data.length - 1; i++) {
    if (data[i] == 13 && data[i + 1] == 10) return i;
  }
  return -1;
}

int _indexOfHeaderEnd(List<int> data) {
  for (var i = 0; i < data.length - 3; i++) {
    if (data[i] == 13 && data[i + 1] == 10 && data[i + 2] == 13 && data[i + 3] == 10) {
      return i;
    }
  }
  return -1;
}

HttpClient buildOdyHttpClient({String? connectIp}) {
  final client = HttpClient();
  client.connectionTimeout = const Duration(seconds: 20);
  client.findProxy = (_) => 'DIRECT';
  client.badCertificateCallback = (cert, host, port) => host.endsWith('.ts.net');
  return client;
}

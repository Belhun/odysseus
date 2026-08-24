import 'dart:convert';

import 'package:http/http.dart' as http;

import 'ody_http.dart';

class ChatSession {
  ChatSession({
    required this.id,
    required this.name,
    this.updatedAt,
    this.messageCount = 0,
  });

  final String id;
  final String name;
  final String? updatedAt;
  final int messageCount;

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    return ChatSession(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? 'Chat'}',
      updatedAt: json['last_message_at']?.toString() ?? json['updated_at']?.toString(),
      messageCount: (json['message_count'] as num?)?.toInt() ?? 0,
    );
  }
}

class ChatLine {
  ChatLine({required this.role, required this.content});

  final String role;
  final String content;
}

/// Parse one SSE `data:` payload from `/api/chat_stream`.
String? parseChatSseData(String data) {
  final trimmed = data.trim();
  if (trimmed.isEmpty || trimmed == '[DONE]') return null;
  try {
    final decoded = jsonDecode(trimmed);
    if (decoded is Map) {
      if (decoded['thinking'] == true) return '';
      final delta = decoded['delta'];
      if (delta is String) return delta;
    }
  } catch (_) {}
  return null;
}

class ChatClient {
  ChatClient(this.httpClient);

  final OdyHttp httpClient;

  ApiException _scope(ApiException e) {
    if (e.statusCode != 403) return e;
    if (e.message.contains('finance:read')) {
      return ApiException(
        403,
        'This token cannot use Chat. It needs the chat scope. '
        'A finance-only token is not enough. Cookie login still works.',
        body: e.body,
      );
    }
    return e;
  }

  Future<T> _guard<T>(Future<T> Function() run) async {
    try {
      return await run();
    } on ApiException catch (e) {
      throw _scope(e);
    }
  }

  List<ChatSession> _parseSessions(dynamic data) {
    final list = data is List
        ? data
        : (data is Map ? data['sessions'] : null);
    return (list as List? ?? [])
        .whereType<Map>()
        .map((e) => ChatSession.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<ChatSession>> sessions() async {
    return _guard(() async {
      try {
        return _parseSessions(await httpClient.get('/api/mobile/chat/sessions'));
      } on ApiException catch (e) {
        if (e.statusCode == 404) {
          return _parseSessions(await httpClient.get('/api/sessions'));
        }
        rethrow;
      }
    });
  }

  Future<String> createSession({String name = 'Phone'}) async {
    return _guard(() async {
      try {
        final data = await httpClient.sendJson(
          'POST',
          '/api/mobile/chat/sessions',
          body: {'name': name},
        );
        if (data is Map && data['id'] != null) return '${data['id']}';
        throw ApiException(500, 'Session create did not return an id');
      } on ApiException catch (e) {
        if (e.statusCode == 404) return _createLegacy(name);
        rethrow;
      }
    });
  }

  Future<String> _createLegacy(String name) async {
    String endpointUrl = '';
    String model = '';
    String endpointId = '';
    try {
      final raw = await httpClient.get('/api/companion/models');
      final list = raw is List ? raw : const [];
      if (list.isNotEmpty && list.first is Map) {
        final first = Map<String, dynamic>.from(list.first as Map);
        endpointUrl = '${first['endpoint_url'] ?? ''}';
        endpointId = '${first['endpoint_id'] ?? ''}';
        final models = first['models'];
        if (models is List && models.isNotEmpty) {
          model = '${models.first}';
        }
      }
    } on ApiException {
      rethrow;
    }
    if (model.isEmpty) {
      throw ApiException(400, 'No models configured');
    }
    final data = await httpClient.postForm('/api/session', {
      'name': name,
      'endpoint_url': endpointUrl,
      'model': model,
      'skip_validation': 'true',
      if (endpointId.isNotEmpty) 'endpoint_id': endpointId,
    });
    if (data is Map && data['id'] != null) return '${data['id']}';
    throw ApiException(500, 'Session create did not return an id');
  }

  Future<List<ChatLine>> history(String sessionId) async {
    return _guard(() async {
      final data = await httpClient.get('/api/history/$sessionId');
      final map = data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
      return (map['history'] as List? ?? [])
          .whereType<Map>()
          .map((e) {
            final m = Map<String, dynamic>.from(e);
            return ChatLine(
              role: '${m['role'] ?? ''}',
              content: '${m['content'] ?? ''}',
            );
          })
          .toList();
    });
  }

  Future<String> send({required String sessionId, required String message}) async {
    return _guard(() async {
      final data = await httpClient.sendJson('POST', '/api/chat', body: {
        'session': sessionId,
        'message': message,
      });
      if (data is Map) return '${data['response'] ?? ''}';
      return '$data';
    });
  }

  Future<String> sendStream({
    required String sessionId,
    required String message,
    void Function(String delta)? onDelta,
  }) async {
    try {
      final req = http.MultipartRequest('POST', httpClient.uri('/api/chat_stream'));
      req.fields['message'] = message;
      req.fields['session'] = sessionId;
      final streamed = await httpClient.sendMultipart(req);
      if (streamed.statusCode >= 400) {
        final res = await http.Response.fromStream(streamed);
        try {
          httpClient.parseResponse(res);
        } on ApiException catch (e) {
          throw _scope(e);
        }
      }
      final out = StringBuffer();
      var carry = '';
      await for (final chunk in streamed.stream.transform(utf8.decoder)) {
        carry += chunk;
        final lines = carry.split('\n');
        carry = lines.removeLast();
        for (final line in lines) {
          final payload = _ssePayload(line);
          if (payload == null) continue;
          final delta = parseChatSseData(payload);
          if (delta == null || delta.isEmpty) continue;
          out.write(delta);
          onDelta?.call(delta);
        }
      }
      final tail = parseChatSseData(_ssePayload('data: $carry') ?? carry);
      if (tail != null && tail.isNotEmpty) {
        out.write(tail);
        onDelta?.call(tail);
      }
      if (out.isEmpty) {
        return send(sessionId: sessionId, message: message);
      }
      return out.toString();
    } on ApiException catch (e) {
      if (e.statusCode == 404 || e.statusCode == 405) {
        return send(sessionId: sessionId, message: message);
      }
      throw _scope(e);
    }
  }

  Future<void> stop(String sessionId) async {
    try {
      await httpClient.sendJson('POST', '/api/chat/stop/$sessionId');
    } on ApiException catch (e) {
      throw _scope(e);
    }
  }

  String? _ssePayload(String line) {
    final trimmed = line.trimRight();
    if (trimmed.isEmpty) return null;
    if (trimmed.startsWith('data:')) {
      return trimmed.substring(5).trim();
    }
    return null;
  }
}

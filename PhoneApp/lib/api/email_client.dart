import 'ody_http.dart';

String emailErrorMessage(Object error) {
  if (error is ApiException && error.statusCode == 403) {
    return 'This token needs email:read (and email:send to compose). '
        'Cookie login works. A phone_finance token is not enough.';
  }
  return '$error';
}

/// Best-effort HTML → plain text for phone read view (no WebView in v1).
String htmlToPlainText(String raw) {
  var s = raw;
  s = s.replaceAll(RegExp(r'<script[^>]*>[\s\S]*?</script>', caseSensitive: false), '');
  s = s.replaceAll(RegExp(r'<style[^>]*>[\s\S]*?</style>', caseSensitive: false), '');
  s = s.replaceAll(RegExp(r'<br\s*/?>', caseSensitive: false), '\n');
  s = s.replaceAll(RegExp(r'</p>', caseSensitive: false), '\n\n');
  s = s.replaceAll(RegExp(r'</div>', caseSensitive: false), '\n');
  s = s.replaceAll(RegExp(r'</tr>', caseSensitive: false), '\n');
  s = s.replaceAll(RegExp(r'</h[1-6]>', caseSensitive: false), '\n\n');
  s = s.replaceAll(RegExp(r'</li>', caseSensitive: false), '\n');
  s = s.replaceAll(RegExp(r'<[^>]+>'), '');
  s = s.replaceAll('&nbsp;', ' ');
  s = s.replaceAll('&amp;', '&');
  s = s.replaceAll('&lt;', '<');
  s = s.replaceAll('&gt;', '>');
  s = s.replaceAll('&quot;', '"');
  s = s.replaceAll('&#39;', "'");
  s = s.replaceAll('&apos;', "'");
  s = s.replaceAllMapped(RegExp(r'&#(\d+);'), (m) {
    final n = int.tryParse(m.group(1)!);
    if (n == null || n <= 0 || n > 0x10FFFF) return m.group(0)!;
    return String.fromCharCode(n);
  });
  s = s.replaceAll(RegExp(r'\n{3,}'), '\n\n');
  return htmlUnescapeBasic(s).trim();
}

String htmlUnescapeBasic(String s) => s;

class EmailAccount {
  EmailAccount({
    required this.id,
    required this.name,
    required this.fromAddress,
    this.displayName = '',
    this.isDefault = false,
    this.enabled = true,
    this.oauthProvider = '',
  });

  final String id;
  final String name;
  final String fromAddress;
  final String displayName;
  final bool isDefault;
  final bool enabled;
  final String oauthProvider;

  String get label {
    if (name.trim().isNotEmpty) return name.trim();
    if (displayName.trim().isNotEmpty) return displayName.trim();
    if (fromAddress.trim().isNotEmpty) return fromAddress.trim();
    return 'Account';
  }

  factory EmailAccount.fromJson(Map<String, dynamic> json) {
    return EmailAccount(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? ''}',
      fromAddress: '${json['from_address'] ?? json['email'] ?? ''}',
      displayName: '${json['display_name'] ?? ''}',
      isDefault: json['is_default'] == true,
      enabled: json['enabled'] != false,
      oauthProvider: '${json['oauth_provider'] ?? ''}',
    );
  }
}

class EmailHeader {
  EmailHeader({
    required this.uid,
    required this.subject,
    required this.fromName,
    required this.fromAddress,
    required this.date,
    this.dateEpoch = 0,
    this.isRead = true,
    this.hasAttachments = false,
    this.folder = '',
  });

  final String uid;
  final String subject;
  final String fromName;
  final String fromAddress;
  final String date;
  final double dateEpoch;
  final bool isRead;
  final bool hasAttachments;
  final String folder;

  bool get unread => !isRead;

  String get fromLabel {
    if (fromName.trim().isNotEmpty) return fromName.trim();
    if (fromAddress.trim().isNotEmpty) return fromAddress.trim();
    return '(unknown)';
  }

  factory EmailHeader.fromJson(Map<String, dynamic> json) {
    final epochRaw = json['date_epoch'];
    double epoch = 0;
    if (epochRaw is num) epoch = epochRaw.toDouble();
    return EmailHeader(
      uid: '${json['uid'] ?? json['id'] ?? ''}',
      subject: '${json['subject'] ?? '(no subject)'}',
      fromName: '${json['from_name'] ?? ''}',
      fromAddress: '${json['from_address'] ?? json['from'] ?? json['from_addr'] ?? ''}',
      date: '${json['date'] ?? json['date_display'] ?? ''}',
      dateEpoch: epoch,
      isRead: json['is_read'] == true,
      hasAttachments: json['has_attachments'] == true,
      folder: '${json['folder'] ?? ''}',
    );
  }
}

class EmailAttachment {
  EmailAttachment({required this.filename, this.size = 0});

  final String filename;
  final int size;

  factory EmailAttachment.fromJson(Map<String, dynamic> json) {
    final sizeRaw = json['size'];
    return EmailAttachment(
      filename: '${json['filename'] ?? json['name'] ?? 'attachment'}',
      size: sizeRaw is num ? sizeRaw.toInt() : int.tryParse('$sizeRaw') ?? 0,
    );
  }
}

class EmailMessage {
  EmailMessage({
    required this.uid,
    required this.subject,
    required this.fromName,
    required this.fromAddress,
    required this.to,
    required this.cc,
    required this.date,
    required this.body,
    required this.bodyHtml,
    required this.messageId,
    required this.inReplyTo,
    required this.references,
    required this.folder,
    this.attachments = const [],
  });

  final String uid;
  final String subject;
  final String fromName;
  final String fromAddress;
  final String to;
  final String cc;
  final String date;
  final String body;
  final String bodyHtml;
  final String messageId;
  final String inReplyTo;
  final String references;
  final String folder;
  final List<EmailAttachment> attachments;

  String get fromLabel {
    if (fromName.trim().isNotEmpty && fromAddress.trim().isNotEmpty) {
      return '$fromName <$fromAddress>';
    }
    if (fromName.trim().isNotEmpty) return fromName.trim();
    return fromAddress.trim();
  }

  String get plainBody {
    final text = body.trim();
    if (text.isNotEmpty) return text;
    if (bodyHtml.trim().isNotEmpty) return htmlToPlainText(bodyHtml);
    return '';
  }

  factory EmailMessage.fromJson(Map<String, dynamic> json) {
    final atts = <EmailAttachment>[];
    final raw = json['attachments'];
    if (raw is List) {
      for (final item in raw) {
        if (item is Map) {
          atts.add(EmailAttachment.fromJson(Map<String, dynamic>.from(item)));
        }
      }
    }
    return EmailMessage(
      uid: '${json['uid'] ?? json['id'] ?? ''}',
      subject: '${json['subject'] ?? '(no subject)'}',
      fromName: '${json['from_name'] ?? ''}',
      fromAddress: '${json['from_address'] ?? json['from'] ?? json['from_addr'] ?? ''}',
      to: '${json['to'] ?? ''}',
      cc: '${json['cc'] ?? ''}',
      date: '${json['date'] ?? json['date_display'] ?? ''}',
      body: '${json['body'] ?? json['body_text'] ?? json['text'] ?? ''}',
      bodyHtml: '${json['body_html'] ?? ''}',
      messageId: '${json['message_id'] ?? ''}',
      inReplyTo: '${json['in_reply_to'] ?? ''}',
      references: '${json['references'] ?? ''}',
      folder: '${json['folder'] ?? ''}',
      attachments: atts,
    );
  }
}

class EmailClient {
  EmailClient(this.http);

  final OdyHttp http;

  Map<String, dynamic> _asMap(dynamic data) {
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    return <String, dynamic>{};
  }

  void _throwIfError(Map<String, dynamic> map) {
    final err = map['error'];
    if (err is String && err.trim().isNotEmpty) {
      throw ApiException(502, err);
    }
  }

  Future<List<EmailAccount>> listAccounts() async {
    final map = _asMap(await http.get('/api/email/accounts'));
    return (map['accounts'] as List? ?? [])
        .whereType<Map>()
        .map((e) => EmailAccount.fromJson(Map<String, dynamic>.from(e)))
        .where((a) => a.enabled && a.id.isNotEmpty)
        .toList();
  }

  Future<List<String>> listFolders({String? accountId}) async {
    final map = _asMap(await http.get('/api/email/folders', query: {
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
    }));
    final folders = (map['folders'] as List? ?? [])
        .map((e) {
          if (e is Map) return '${e['name'] ?? e['path'] ?? ''}';
          return '$e';
        })
        .where((s) => s.isNotEmpty)
        .toList();
    if (folders.isEmpty) {
      _throwIfError(map);
    }
    return folders;
  }

  Future<List<EmailHeader>> listMessages({
    String folder = 'INBOX',
    String? accountId,
    String filter = 'all',
    int limit = 50,
    int offset = 0,
    bool bustCache = false,
  }) async {
    final map = _asMap(await http.get('/api/email/list', query: {
      'folder': folder,
      'limit': '$limit',
      'offset': '$offset',
      'filter': filter,
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      if (bustCache) '_': '${DateTime.now().millisecondsSinceEpoch}',
    }));
    _throwIfError(map);
    return (map['emails'] as List? ?? [])
        .whereType<Map>()
        .map((e) => EmailHeader.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<List<EmailHeader>> search({
    required String query,
    String folder = 'INBOX',
    String? accountId,
    int limit = 50,
  }) async {
    final map = _asMap(await http.get('/api/email/search', query: {
      'q': query,
      'folder': folder,
      'limit': '$limit',
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
    }));
    _throwIfError(map);
    return (map['emails'] as List? ?? [])
        .whereType<Map>()
        .map((e) => EmailHeader.fromJson(Map<String, dynamic>.from(e)))
        .toList();
  }

  Future<EmailMessage> read(
    String uid, {
    String folder = 'INBOX',
    String? accountId,
    bool markSeen = true,
  }) async {
    final map = _asMap(await http.get('/api/email/read/$uid', query: {
      'folder': folder,
      'mark_seen': markSeen ? 'true' : 'false',
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
    }));
    _throwIfError(map);
    return EmailMessage.fromJson(map);
  }

  Future<void> markRead(
    String uid, {
    String folder = 'INBOX',
    String? accountId,
  }) async {
    final map = _asMap(await http.sendJson(
      'POST',
      '/api/email/mark-read/$uid',
      query: {
        'folder': folder,
        if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      },
    ));
    if (map['success'] == false) {
      throw ApiException(502, '${map['error'] ?? 'Mark read failed'}');
    }
  }

  Future<void> markUnread(
    String uid, {
    String folder = 'INBOX',
    String? accountId,
  }) async {
    final map = _asMap(await http.sendJson(
      'POST',
      '/api/email/mark-unread/$uid',
      query: {
        'folder': folder,
        if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      },
    ));
    if (map['success'] == false) {
      throw ApiException(502, '${map['error'] ?? 'Mark unread failed'}');
    }
  }

  Future<void> send({
    required String to,
    required String subject,
    required String body,
    String? cc,
    String? accountId,
    String? inReplyTo,
    String? references,
    bool waitForDelivery = false,
  }) async {
    final map = _asMap(await http.sendJson('POST', '/api/email/send', body: {
      'to': to,
      'subject': subject,
      'body': body,
      if (cc != null && cc.trim().isNotEmpty) 'cc': cc.trim(),
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      if (inReplyTo != null && inReplyTo.isNotEmpty) 'in_reply_to': inReplyTo,
      if (references != null && references.isNotEmpty) 'references': references,
      'wait_for_delivery': waitForDelivery,
    }));
    if (map['success'] == false) {
      throw ApiException(502, '${map['error'] ?? 'Send failed'}');
    }
  }

  Future<void> saveDraft({
    required String to,
    required String subject,
    required String body,
    String? cc,
    String? accountId,
    String? inReplyTo,
    String? references,
  }) async {
    final map = _asMap(await http.sendJson('POST', '/api/email/draft', body: {
      'to': to,
      'subject': subject,
      'body': body,
      if (cc != null && cc.trim().isNotEmpty) 'cc': cc.trim(),
      if (accountId != null && accountId.isNotEmpty) 'account_id': accountId,
      if (inReplyTo != null && inReplyTo.isNotEmpty) 'in_reply_to': inReplyTo,
      if (references != null && references.isNotEmpty) 'references': references,
    }));
    if (map['success'] == false) {
      throw ApiException(502, '${map['error'] ?? 'Draft failed'}');
    }
  }
}

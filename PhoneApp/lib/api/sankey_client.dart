import 'ody_http.dart';
import 'models.dart';

class SankeyNode {
  SankeyNode({
    required this.id,
    required this.label,
    required this.cents,
    required this.kind,
    this.categoryId,
    this.color,
  });

  final String id;
  final String label;
  final int cents;
  final String kind;
  final String? categoryId;
  final String? color;

  factory SankeyNode.fromJson(Map<String, dynamic> json) {
    return SankeyNode(
      id: asString(json['id']),
      label: asString(json['label']),
      cents: asInt(json['cents']),
      kind: asString(json['kind']),
      categoryId: json['category_id']?.toString(),
      color: json['color']?.toString(),
    );
  }
}

class SankeyLink {
  SankeyLink({
    required this.source,
    required this.target,
    required this.cents,
  });

  final String source;
  final String target;
  final int cents;

  factory SankeyLink.fromJson(Map<String, dynamic> json) {
    return SankeyLink(
      source: asString(json['source']),
      target: asString(json['target']),
      cents: asInt(json['cents']),
    );
  }
}

class SankeyReport {
  SankeyReport({
    required this.month,
    required this.incomeCents,
    required this.nodes,
    required this.links,
    required this.unclassifiedCount,
    required this.unclassifiedOutflowCents,
    required this.incomplete,
  });

  final String month;
  final int incomeCents;
  final List<SankeyNode> nodes;
  final List<SankeyLink> links;
  final int unclassifiedCount;
  final int unclassifiedOutflowCents;
  final bool incomplete;

  List<SankeyNode> get categoryNodes =>
      nodes.where((n) => n.kind == 'category').toList();

  SankeyNode? get leftoverNode {
    for (final n in nodes) {
      if (n.kind == 'leftover') return n;
    }
    return null;
  }

  factory SankeyReport.fromJson(Map<String, dynamic> json) {
    return SankeyReport(
      month: asString(json['month']),
      incomeCents: asInt(json['income_cents']),
      nodes: (json['nodes'] as List? ?? [])
          .whereType<Map>()
          .map((e) => SankeyNode.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      links: (json['links'] as List? ?? [])
          .whereType<Map>()
          .map((e) => SankeyLink.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      unclassifiedCount: asInt(json['unclassified_count']),
      unclassifiedOutflowCents: asInt(json['unclassified_outflow_cents']),
      incomplete: asBool(json['incomplete']) || asInt(json['unclassified_count']) > 0,
    );
  }
}

class SankeyClient {
  SankeyClient(this.http);

  final OdyHttp http;

  Future<SankeyReport> forMonth(String month) async {
    final data = await http.get('/api/finance/reports/sankey', query: {'month': month});
    final map = data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
    return SankeyReport.fromJson(map);
  }
}

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

class DocumentViewException implements Exception {
  DocumentViewException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Mints a fresh signed Cloudinary URL for viewing a case document. Never
/// caches or returns anything reusable beyond the immediate call — the
/// URL is a short-lived bearer token for that file
/// (GET /api/v2/documents/{caseId}/{docId}/download-url re-authorizes and
/// re-mints on every call), so the only correct way to handle an expired
/// or failed open is to call this again, not to retry the same URL.
class DocumentViewService {
  final _apiClient = ApiClient.instance;

  Future<String> fetchDownloadUrl({
    required String caseId,
    required String docId,
  }) async {
    final response = await _apiClient.get(
      '/documents/$caseId/$docId/download-url',
    );
    if (response.statusCode != 200) {
      throw DocumentViewException(_readableError(response));
    }
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['url'] as String;
  }

  String _readableError(http.Response response) {
    try {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      return json['detail']?.toString() ?? response.body;
    } catch (_) {
      return 'Request failed (${response.statusCode}).';
    }
  }
}

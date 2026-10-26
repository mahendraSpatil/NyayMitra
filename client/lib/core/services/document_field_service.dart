import 'dart:convert';

import 'package:http/http.dart' as http;

import '../models/document_field.dart';
import 'api_client.dart';

class DocumentFieldException implements Exception {
  DocumentFieldException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Confirm / correct / reject a key fact read from a case document
/// (POST /api/v2/cases/{caseId}/document-fields/{fieldId}/confirm|reject).
/// The backend decides who may do this (advocate, NGO, or case manager)
/// and validates corrected values — this only relays its answer.
class DocumentFieldService {
  final _apiClient = ApiClient.instance;

  /// [value] null = "what was read is right". Otherwise a correction:
  /// DD/MM/YYYY for dates, e.g. "436A CrPC" for sections, "214/2026" for
  /// FIR numbers.
  Future<DocumentField> confirm({
    required String caseId,
    required String fieldId,
    String? value,
    String? role,
  }) async {
    final response = await _apiClient.post(
      '/cases/$caseId/document-fields/$fieldId/confirm',
      body: {
        'value': ?value,
        'role': ?role,
      },
    );
    return _parse(response);
  }

  /// A fact the extractors missed, typed in from the paper original.
  Future<DocumentField> addFact({
    required String caseId,
    required String documentId,
    required String kind,
    String? role,
    required String value,
  }) async {
    final response = await _apiClient.post(
      '/cases/$caseId/documents/$documentId/fields',
      body: {'kind': kind, 'role': ?role, 'value': value},
    );
    return _parse(response);
  }

  // Above the backend's LLM_TIMEOUT_S (120s) — same reasoning as
  // chat_service.dart: never cancel first and hide the server's answer.
  static const _findTimeout = Duration(seconds: 150);

  /// Ask the AI to point at facts the automatic passes missed. Everything
  /// it finds still needs a person to confirm it.
  Future<FindFactsResult> findMoreFacts({
    required String caseId,
    required String documentId,
  }) async {
    final response = await _apiClient
        .post('/cases/$caseId/documents/$documentId/find-facts')
        .timeout(
          _findTimeout,
          onTimeout: () => throw DocumentFieldException(
            'The AI took too long. Try again in a minute.',
          ),
        );
    if (response.statusCode == 503) {
      throw DocumentFieldException(
        'NyayMitra AI is offline right now. Please try again in a minute.',
      );
    }
    if (response.statusCode != 200) {
      throw DocumentFieldException(_readableError(response));
    }
    return FindFactsResult.fromApi(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<DocumentField> reject({
    required String caseId,
    required String fieldId,
  }) async {
    final response = await _apiClient.post(
      '/cases/$caseId/document-fields/$fieldId/reject',
    );
    return _parse(response);
  }

  DocumentField _parse(http.Response response) {
    if (response.statusCode != 200) {
      throw DocumentFieldException(_readableError(response));
    }
    return DocumentField.fromApi(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
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

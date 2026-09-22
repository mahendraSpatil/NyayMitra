import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

class CaseServiceException implements Exception {
  CaseServiceException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Everything that mutates cases/ — creation and hearing CRUD — goes
/// through here rather than a direct write. The backend denies all
/// direct writes to the cases/case_members/hearings tables from
/// anywhere but its own routes: ownerType/createdBy/advocateUid/ngoUids/
/// familyUids are set from the caller's own verified role and uid
/// server-side, never from anything the client asserts.
class CaseService {
  final _apiClient = ApiClient.instance;

  /// Creates a case owned according to the caller's own role (advocate,
  /// ngo, or a family user with no lawyer creating their own tracker).
  /// Returns the new caseId.
  Future<String> createCase({
    required String undertrialName,
    String firNumber = '',
    String court = '',
  }) async {
    final response = await _apiClient.post(
      '/cases',
      body: {
        'undertrialName': undertrialName,
        'firNumber': firNumber,
        'court': court,
      },
    );
    if (response.statusCode != 200) {
      throw CaseServiceException(_readableError(response));
    }
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['caseId'] as String;
  }

  Future<void> addHearing({
    required String caseId,
    required DateTime date,
    String court = '',
    String purpose = '',
    String status = 'scheduled',
    String notes = '',
  }) async {
    final response = await _apiClient.post(
      '/cases/$caseId/hearings',
      body: {
        'date': date.toUtc().toIso8601String(),
        'court': court,
        'purpose': purpose,
        'status': status,
        'notes': notes,
      },
    );
    if (response.statusCode != 200) {
      throw CaseServiceException(_readableError(response));
    }
  }

  Future<void> updateHearing({
    required String caseId,
    required String hearingId,
    required DateTime date,
    String court = '',
    String purpose = '',
    String status = 'scheduled',
    String notes = '',
  }) async {
    final response = await _apiClient.put(
      '/cases/$caseId/hearings/$hearingId',
      body: {
        'date': date.toUtc().toIso8601String(),
        'court': court,
        'purpose': purpose,
        'status': status,
        'notes': notes,
      },
    );
    if (response.statusCode != 200) {
      throw CaseServiceException(_readableError(response));
    }
  }

  Future<void> deleteHearing({
    required String caseId,
    required String hearingId,
  }) async {
    final response = await _apiClient.delete(
      '/cases/$caseId/hearings/$hearingId',
    );
    if (response.statusCode != 200) {
      throw CaseServiceException(_readableError(response));
    }
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

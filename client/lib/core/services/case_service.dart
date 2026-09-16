import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

/// TODO: same dev-only placeholder as chat_service.dart / document_upload
/// _baseUrl — needs real build-time configuration before this reaches any
/// device but this machine.
const _baseUrl = 'http://localhost:8000';

class CaseServiceException implements Exception {
  CaseServiceException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// Everything that mutates cases/ — creation and hearing CRUD — goes
/// through here rather than direct Firestore writes. firestore.rules
/// denies all client writes to cases/ outright: ownerType/createdBy/
/// advocateUid/ngoUids/familyUids are set from the caller's own verified
/// role and uid server-side, never from anything the client asserts.
class CaseService {
  Future<Map<String, String>> _authHeaders() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      throw StateError('CaseService called with no signed-in user');
    }
    final token = await user.getIdToken();
    return {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
  }

  /// Creates a case owned according to the caller's own role (advocate,
  /// ngo, or a family user with no lawyer creating their own tracker).
  /// Returns the new caseId.
  Future<String> createCase({
    required String undertrialName,
    String firNumber = '',
    String court = '',
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/cases'),
      headers: await _authHeaders(),
      body: jsonEncode({
        'undertrialName': undertrialName,
        'firNumber': firNumber,
        'court': court,
      }),
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
    final response = await http.post(
      Uri.parse('$_baseUrl/cases/$caseId/hearings'),
      headers: await _authHeaders(),
      body: jsonEncode({
        'date': date.toUtc().toIso8601String(),
        'court': court,
        'purpose': purpose,
        'status': status,
        'notes': notes,
      }),
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
    final response = await http.put(
      Uri.parse('$_baseUrl/cases/$caseId/hearings/$hearingId'),
      headers: await _authHeaders(),
      body: jsonEncode({
        'date': date.toUtc().toIso8601String(),
        'court': court,
        'purpose': purpose,
        'status': status,
        'notes': notes,
      }),
    );
    if (response.statusCode != 200) {
      throw CaseServiceException(_readableError(response));
    }
  }

  Future<void> deleteHearing({required String caseId, required String hearingId}) async {
    final response = await http.delete(
      Uri.parse('$_baseUrl/cases/$caseId/hearings/$hearingId'),
      headers: await _authHeaders(),
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

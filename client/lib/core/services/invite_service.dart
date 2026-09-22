import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_client.dart';

class InviteServiceException implements Exception {
  InviteServiceException(this.message);

  final String message;

  @override
  String toString() => message;
}

class GeneratedInvite {
  const GeneratedInvite({required this.code, required this.expiresAt});

  final String code;
  final DateTime expiresAt;
}

/// Invite generation and redemption both go through the backend — there
/// is no client write path to invites/invite_attempts at all in this
/// schema.
class InviteService {
  final _apiClient = ApiClient.instance;

  /// Only a case manager can call this successfully — the backend
  /// re-checks that independently, this is not a client-side gate.
  Future<GeneratedInvite> generateInvite(String caseId) async {
    final response = await _apiClient.post('/cases/$caseId/invites');
    if (response.statusCode != 200) {
      throw InviteServiceException(_readableError(response));
    }
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return GeneratedInvite(
      code: json['code'] as String,
      expiresAt: DateTime.parse(json['expiresAt'] as String),
    );
  }

  /// Returns the caseId the code granted access to.
  Future<String> redeemInvite(String code) async {
    final response = await _apiClient.post(
      '/invites/redeem',
      body: {'code': code},
    );
    if (response.statusCode != 200) {
      throw InviteServiceException(_readableError(response));
    }
    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['caseId'] as String;
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

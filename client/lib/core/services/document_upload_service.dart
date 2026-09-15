import 'dart:convert';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:http/http.dart' as http;

/// TODO: same dev-only placeholder as chat_service.dart's _baseUrl — needs
/// real build-time configuration before this reaches any device but this
/// machine.
const _baseUrl = 'http://localhost:8000';

class DocumentUploadOutcome {
  const DocumentUploadOutcome({required this.ocrStatus, required this.hasText});

  final String ocrStatus;
  final bool hasText;
}

class DocumentUploadException implements Exception {
  DocumentUploadException(this.message);

  final String message;

  @override
  String toString() => message;
}

/// The three-step signed-upload flow: ask the backend for a Cloudinary
/// signature, upload the file bytes directly to Cloudinary (the backend
/// never sees the file in transit), then tell the backend the upload
/// succeeded so it can download the file itself, extract text, and write
/// the Firestore record. Shared by the Advocate Console and Family Portal
/// — both use the same UploadDocumentSheet.
class DocumentUploadService {
  Future<DocumentUploadOutcome> upload({
    required String caseId,
    required String docTypeApiValue,
    required PlatformFile file,
  }) async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      throw StateError('upload called with no signed-in user');
    }
    final token = await user.getIdToken();
    final authHeaders = {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };

    final signResponse = await http.post(
      Uri.parse('$_baseUrl/documents/sign-upload'),
      headers: authHeaders,
      body: jsonEncode({'caseId': caseId, 'docType': docTypeApiValue}),
    );
    if (signResponse.statusCode != 200) {
      throw DocumentUploadException(_readableError(signResponse));
    }
    final signed = jsonDecode(signResponse.body) as Map<String, dynamic>;

    final secureUrl = await _uploadToCloudinary(signed: signed, file: file);

    final confirmResponse = await http.post(
      Uri.parse('$_baseUrl/documents/confirm-upload'),
      headers: authHeaders,
      body: jsonEncode({
        'caseId': caseId,
        'docId': signed['docId'],
        'docType': docTypeApiValue,
        'secureUrl': secureUrl,
      }),
    );
    if (confirmResponse.statusCode != 200) {
      throw DocumentUploadException(_readableError(confirmResponse));
    }
    final confirmed = jsonDecode(confirmResponse.body) as Map<String, dynamic>;
    return DocumentUploadOutcome(
      ocrStatus: confirmed['ocrStatus'] as String? ?? 'failed',
      hasText: confirmed['hasText'] as bool? ?? false,
    );
  }

  Future<String> _uploadToCloudinary({
    required Map<String, dynamic> signed,
    required PlatformFile file,
  }) async {
    final cloudName = signed['cloudName'] as String;
    final resourceType = signed['resourceType'] as String;
    final uploadUri =
        Uri.parse('https://api.cloudinary.com/v1_1/$cloudName/$resourceType/upload');

    final request = http.MultipartRequest('POST', uploadUri)
      ..fields['api_key'] = signed['apiKey'] as String
      ..fields['timestamp'] = '${signed['timestamp']}'
      ..fields['signature'] = signed['signature'] as String
      ..fields['public_id'] = signed['publicId'] as String;

    final Uint8List bytes;
    try {
      bytes = await file.readAsBytes();
    } catch (e) {
      throw DocumentUploadException('Selected file could not be read: $e');
    }
    request.files.add(http.MultipartFile.fromBytes('file', bytes, filename: file.name));

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 200) {
      throw DocumentUploadException('Cloudinary upload failed: ${response.body}');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    return json['secure_url'] as String;
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

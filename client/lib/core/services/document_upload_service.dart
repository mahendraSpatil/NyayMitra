import 'dart:convert';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;

import 'api_client.dart';

class DocumentUploadOutcome {
  const DocumentUploadOutcome({
    required this.ocrStatus,
    required this.hasText,
    this.fieldsNeedingReview = 0,
  });

  final String ocrStatus;
  final bool hasText;

  /// Dates/sections/FIR numbers read from a scan that a person must
  /// confirm before the AI uses them.
  final int fieldsNeedingReview;
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
/// the case-document record. Shared by the Advocate Console and Family
/// Portal — both use the same UploadDocumentSheet.
///
/// Only the first and third steps go through ApiClient — the middle step
/// uploads directly to Cloudinary's own API (a different host entirely,
/// authenticated by the signature itself, not a Bearer token), so it
/// stays a plain http.MultipartRequest.
class DocumentUploadService {
  final _apiClient = ApiClient.instance;

  Future<DocumentUploadOutcome> upload({
    required String caseId,
    required String docTypeApiValue,
    required PlatformFile file,
  }) async {
    final signResponse = await _apiClient.post(
      '/documents/sign-upload',
      body: {'caseId': caseId, 'docType': docTypeApiValue},
    );
    if (signResponse.statusCode != 200) {
      throw DocumentUploadException(_readableError(signResponse));
    }
    final signed = jsonDecode(signResponse.body) as Map<String, dynamic>;

    final actualPublicId = await _uploadToCloudinary(
      signed: signed,
      file: file,
    );

    final confirmResponse = await _apiClient.post(
      '/documents/confirm-upload',
      body: {
        'caseId': caseId,
        'docId': signed['docId'],
        'docType': docTypeApiValue,
        'publicId': actualPublicId,
      },
    );
    if (confirmResponse.statusCode != 200) {
      throw DocumentUploadException(_readableError(confirmResponse));
    }
    final confirmed = jsonDecode(confirmResponse.body) as Map<String, dynamic>;
    return DocumentUploadOutcome(
      ocrStatus: confirmed['ocrStatus'] as String? ?? 'failed',
      hasText: confirmed['hasText'] as bool? ?? false,
      fieldsNeedingReview: confirmed['fieldsNeedingReview'] as int? ?? 0,
    );
  }

  /// Returns Cloudinary's actual assigned public_id (not a URL — see
  /// confirm-upload's comment on ConfirmUploadRequest for why). Goes
  /// straight to Cloudinary, not through ApiClient/our backend — this
  /// request carries no access token at all, only the signature the
  /// backend minted for it.
  Future<String> _uploadToCloudinary({
    required Map<String, dynamic> signed,
    required PlatformFile file,
  }) async {
    final cloudName = signed['cloudName'] as String;
    final resourceType = signed['resourceType'] as String;
    final uploadUri = Uri.parse(
      'https://api.cloudinary.com/v1_1/$cloudName/$resourceType/upload',
    );

    final request = http.MultipartRequest('POST', uploadUri)
      ..fields['api_key'] = signed['apiKey'] as String
      ..fields['timestamp'] = '${signed['timestamp']}'
      ..fields['signature'] = signed['signature'] as String
      ..fields['public_id'] = signed['publicId'] as String
      // Must exactly match what the backend signed — an authenticated-type
      // asset is never publicly fetchable by URL, only through a signed
      // delivery URL the backend mints on demand.
      ..fields['type'] = signed['type'] as String;

    final Uint8List bytes;
    try {
      bytes = await file.readAsBytes();
    } catch (e) {
      throw DocumentUploadException('Selected file could not be read: $e');
    }
    request.files.add(
      http.MultipartFile.fromBytes('file', bytes, filename: file.name),
    );

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);
    if (response.statusCode != 200) {
      throw DocumentUploadException(
        'Cloudinary upload failed: ${response.body}',
      );
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    // Cloudinary's actual assigned public_id, not our pre-upload guess:
    // for resource_type=raw it appends the file extension, so this can
    // differ from the publicId we sent in the signed request.
    return json['public_id'] as String;
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

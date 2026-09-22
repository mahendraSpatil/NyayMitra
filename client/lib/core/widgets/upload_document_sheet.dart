import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../models/case_document.dart';
import '../services/document_upload_service.dart';
import '../theme/app_theme.dart';

const _uploadableDocTypes = [
  DocType.fir,
  DocType.chargeSheet,
  DocType.bailApplication,
  DocType.bailOrder,
  DocType.remandOrder,
];

/// What the sheet hands back to whoever opened it, once it closes after a
/// completed (not cancelled) upload attempt — the caller decides how to
/// tell the user about it (a SnackBar today), since the sheet itself is
/// gone by the time this is read.
class UploadSheetResult {
  const UploadSheetResult({required this.ocrStatus, required this.hasText});

  final String ocrStatus;
  final bool hasText;
}

/// Opens the sheet and, once it closes after a completed (not cancelled)
/// attempt, tells the user the outcome — including the two non-happy
/// paths NyayMitra.md requires surfacing rather than silently swallowing:
/// no text layer (a scan) and unreadable as a PDF at all. The single
/// entry point both Advocate Console and Family Portal call, so this
/// outcome messaging exists in exactly one place.
Future<void> openUploadDocumentSheet(
  BuildContext context, {
  required String caseId,
}) async {
  final result = await showModalBottomSheet<UploadSheetResult>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => UploadDocumentSheet(caseId: caseId),
  );
  if (result == null || !context.mounted) return;

  final message = switch (result.ocrStatus) {
    'extracted' => 'Document uploaded.',
    'no_text_layer' =>
      "Uploaded, but no readable text was found — this looks like a "
          "scan. Text extraction isn't available for scans yet.",
    _ => "Uploaded, but the file couldn't be read as a PDF.",
  };
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}

/// Upload entry point for a case's documents, shared by the Advocate
/// Console and Family Portal.
class UploadDocumentSheet extends StatefulWidget {
  const UploadDocumentSheet({super.key, required this.caseId});

  final String caseId;

  @override
  State<UploadDocumentSheet> createState() => _UploadDocumentSheetState();
}

class _UploadDocumentSheetState extends State<UploadDocumentSheet> {
  final _uploadService = DocumentUploadService();

  DocType _docType = DocType.fir;
  PlatformFile? _pickedFile;
  bool _isUploading = false;
  String? _errorText;

  Future<void> _pickFile() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (result.isEmpty) return;
    setState(() {
      _pickedFile = result.single;
      _errorText = null;
    });
  }

  Future<void> _submit() async {
    final file = _pickedFile;
    if (file == null || _isUploading) return;

    setState(() {
      _isUploading = true;
      _errorText = null;
    });

    try {
      final outcome = await _uploadService.upload(
        caseId: widget.caseId,
        docTypeApiValue: _docType.apiValue,
        file: file,
      );
      if (!mounted) return;
      Navigator.of(context).pop(
        UploadSheetResult(
          ocrStatus: outcome.ocrStatus,
          hasText: outcome.hasText,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isUploading = false;
        _errorText = '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('Upload Case Document', style: AppTextStyles.portalTitle),
          const SizedBox(height: 16),
          const Text('Document type', style: AppTextStyles.cardSubtitle),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final type in _uploadableDocTypes)
                ChoiceChip(
                  label: Text(type.label),
                  selected: _docType == type,
                  onSelected: _isUploading
                      ? null
                      : (_) => setState(() => _docType = type),
                  selectedColor: AppColors.ink,
                  labelStyle: AppTextStyles.badgeLabel.copyWith(
                    color: _docType == type ? AppColors.surface : AppColors.ink,
                    fontWeight: FontWeight.w500,
                  ),
                  backgroundColor: AppColors.surface,
                  side: BorderSide(
                    color: _docType == type ? AppColors.ink : AppColors.border,
                  ),
                  showCheckmark: false,
                ),
            ],
          ),
          const SizedBox(height: 20),
          OutlinedButton.icon(
            onPressed: _isUploading ? null : _pickFile,
            icon: const Icon(Icons.attach_file),
            label: Text(_pickedFile == null ? 'Choose PDF' : _pickedFile!.name),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: (_pickedFile == null || _isUploading) ? null : _submit,
            child: _isUploading
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.surface,
                    ),
                  )
                : const Text('Upload'),
          ),
          if (_errorText != null) ...[
            const SizedBox(height: 8),
            Text(
              _errorText!,
              textAlign: TextAlign.center,
              style: AppTextStyles.cardSubtitle.copyWith(
                color: AppColors.danger,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

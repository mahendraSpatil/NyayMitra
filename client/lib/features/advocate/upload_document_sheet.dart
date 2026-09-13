import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../core/models/case_document.dart';
import '../../core/theme/app_theme.dart';

const _uploadableDocTypes = [
  DocType.fir,
  DocType.chargeSheet,
  DocType.bailApplication,
  DocType.bailOrder,
  DocType.remandOrder,
];

/// Upload entry point for a case's documents. The submit action is
/// deliberately disabled: CLAUDE.md requires PDF uploads to be signed
/// server-side by FastAPI, and that signing endpoint doesn't exist yet
/// (it's Phase 7+ backend work). This builds the real UI shell now
/// without an unsigned client-side upload standing in for it.
class UploadDocumentSheet extends StatefulWidget {
  const UploadDocumentSheet({super.key});

  @override
  State<UploadDocumentSheet> createState() => _UploadDocumentSheetState();
}

class _UploadDocumentSheetState extends State<UploadDocumentSheet> {
  DocType _docType = DocType.fir;
  PlatformFile? _pickedFile;

  Future<void> _pickFile() async {
    final result = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: ['pdf']);
    if (result.isEmpty) return;
    setState(() => _pickedFile = result.single);
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
                  onSelected: (_) => setState(() => _docType = type),
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
            onPressed: _pickFile,
            icon: const Icon(Icons.attach_file),
            label: Text(_pickedFile == null ? 'Choose PDF' : _pickedFile!.name),
          ),
          const SizedBox(height: 20),
          const FilledButton(
            onPressed: null,
            child: Text('Upload'),
          ),
          const SizedBox(height: 8),
          const Text(
            'Uploads open once document signing is enabled.',
            textAlign: TextAlign.center,
            style: AppTextStyles.cardSubtitle,
          ),
        ],
      ),
    );
  }
}

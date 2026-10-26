import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/case_document.dart';
import '../services/document_opener.dart';
import '../services/document_view_service.dart';
import '../theme/app_theme.dart';
import 'document_fields_sheet.dart';
import 'status_badge.dart';

final _dateFormat = DateFormat('MMM d, yyyy');

/// One document row — shared by the Advocate/NGO case detail screen and
/// the Family Portal's document list (the same case document, the same
/// signed-URL-per-view flow, the same extraction-status badge, so it's
/// one widget, not two copies that would drift). Tapping mints a fresh
/// signed Cloudinary URL and opens it — see document_opener.dart for why
/// opening itself is platform-conditional (url_launcher on native,
/// window.open on web).
class DocumentTile extends StatefulWidget {
  const DocumentTile({super.key, required this.caseId, required this.document});

  final String caseId;
  final CaseDocument document;

  @override
  State<DocumentTile> createState() => _DocumentTileState();
}

class _DocumentTileState extends State<DocumentTile> {
  final _documentViewService = DocumentViewService();

  // Guards against a second tap firing a second fetch while the first is
  // still in flight — not a cache of the URL itself, which is never kept
  // around once used: every open mints a fresh one (a signed Cloudinary
  // URL is a time-limited bearer token for that file).
  bool _opening = false;

  Future<void> _open() async {
    if (_opening) return;
    setState(() => _opening = true);
    try {
      final url = await _documentViewService.fetchDownloadUrl(
        caseId: widget.caseId,
        docId: widget.document.id,
      );
      final opened = await openDocumentUrl(url);
      if (!opened) throw DocumentViewException('Could not open document.');
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not open document: $e'),
          action: SnackBarAction(label: 'Retry', onPressed: _open),
        ),
      );
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  StatusTone get _extractionTone {
    switch (widget.document.ocrStatus) {
      case 'extracted':
        return StatusTone.success;
      case 'ocr_extracted':
        return StatusTone.info;
      case 'ocr_low_confidence':
        return StatusTone.danger;
      case 'no_text_layer':
        return StatusTone.warning;
      case 'failed':
        return StatusTone.danger;
      default:
        return StatusTone.info;
    }
  }

  String get _extractionLabel {
    switch (widget.document.ocrStatus) {
      case 'extracted':
        return 'Extracted';
      // Honest wording: OCR is probabilistic, so a scan is never labelled
      // "Extracted" the way a PDF's own text layer is.
      case 'ocr_extracted':
        return 'Scanned — text may be unreliable';
      case 'ocr_low_confidence':
        return 'Scan unclear — not used by AI';
      case 'no_text_layer':
        return 'No Text Layer';
      case 'failed':
        return 'Extraction Failed';
      default:
        return 'Processing';
    }
  }

  String _factsSummary(CaseDocument document) {
    final parts = <String>[
      if (document.fieldsNeedingReview > 0)
        '${document.fieldsNeedingReview} fact(s) to check',
      if (document.missingFacts.isNotEmpty)
        '${document.missingFacts.length} not found',
    ];
    if (parts.isEmpty) return 'Key facts (${document.fields.length}) →';
    return '${parts.join(' · ')} →';
  }

  @override
  Widget build(BuildContext context) {
    final document = widget.document;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        onTap: _opening ? null : _open,
        leading: _opening
            ? const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.description_outlined, color: AppColors.inkMuted),
        title: Text(document.docType.label, style: AppTextStyles.cardTitle),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              document.uploadedAt == null
                  ? 'Upload pending'
                  : _dateFormat.format(document.uploadedAt!),
              style: AppTextStyles.cardSubtitle,
            ),
            if (document.fields.isNotEmpty || document.missingFacts.isNotEmpty)
              InkWell(
                onTap: () => openDocumentFieldsSheet(
                  context,
                  caseId: widget.caseId,
                  document: document,
                ),
                child: Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    _factsSummary(document),
                    style: AppTextStyles.cardSubtitle.copyWith(
                      color: document.fieldsNeedingReview > 0 ||
                              document.missingFacts.isNotEmpty
                          ? AppColors.warning
                          : AppColors.info,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
          ],
        ),
        trailing: StatusBadge(label: _extractionLabel, tone: _extractionTone),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/case_document.dart';
import '../services/document_opener.dart';
import '../services/document_view_service.dart';
import '../theme/app_theme.dart';
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
      case 'no_text_layer':
        return 'No Text Layer';
      case 'failed':
        return 'Extraction Failed';
      default:
        return 'Processing';
    }
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
        subtitle: Text(
          document.uploadedAt == null
              ? 'Upload pending'
              : _dateFormat.format(document.uploadedAt!),
          style: AppTextStyles.cardSubtitle,
        ),
        trailing: StatusBadge(label: _extractionLabel, tone: _extractionTone),
      ),
    );
  }
}

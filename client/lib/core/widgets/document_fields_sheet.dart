import 'package:flutter/material.dart';

import '../models/case_document.dart';
import '../models/document_field.dart';
import '../services/document_field_service.dart';
import '../theme/app_theme.dart';
import 'status_badge.dart';

const _dateRoles = <String, String>{
  'arrest': 'Arrest date',
  'fir_registered': 'FIR registration date',
  'offence_date': 'Offence date',
  'hearing': 'Hearing date',
  'document_date': 'Document date',
};

const _kinds = <String, String>{
  'date': 'Date',
  'section': 'Section',
  'fir_number': 'FIR number',
};

String _hintFor(String kind) {
  switch (kind) {
    case 'date':
      return 'DD/MM/YYYY';
    case 'section':
      return 'e.g. 436A CrPC';
    case 'fir_number':
      return 'e.g. 214/2026';
    default:
      return '';
  }
}

String _capitalise(String s) =>
    s.isEmpty ? s : '${s[0].toUpperCase()}${s.substring(1)}';

/// Key facts read from one document (FIR number, sections, dates), each
/// with its own confidence; facts the document should have but didn't
/// (with "add it"); and the confirm / correct / reject step. The AI is
/// not shown an unconfirmed fact's value; this sheet is how it becomes
/// usable.
Future<void> openDocumentFieldsSheet(
  BuildContext context, {
  required String caseId,
  required CaseDocument document,
}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => DocumentFieldsSheet(caseId: caseId, document: document),
  );
}

class DocumentFieldsSheet extends StatefulWidget {
  const DocumentFieldsSheet({
    super.key,
    required this.caseId,
    required this.document,
  });

  final String caseId;
  final CaseDocument document;

  @override
  State<DocumentFieldsSheet> createState() => _DocumentFieldsSheetState();
}

class _DocumentFieldsSheetState extends State<DocumentFieldsSheet> {
  final _service = DocumentFieldService();
  late List<DocumentField> _fields;
  late List<MissingFact> _missing;
  String? _busyFieldId;
  bool _finding = false;

  @override
  void initState() {
    super.initState();
    _fields = [...widget.document.fields];
    _missing = [...widget.document.missingFacts];
    _sort();
  }

  // Needs-review first, weakest first — the facts most likely to be
  // wrong are the ones a reviewer should see first.
  void _sort() {
    _fields.sort((a, b) {
      if (a.needsReview != b.needsReview) return a.needsReview ? -1 : 1;
      return a.confidence.compareTo(b.confidence);
    });
  }

  void _upsert(DocumentField updated) {
    setState(() {
      final i = _fields.indexWhere((f) => f.id == updated.id);
      if (i >= 0) {
        _fields[i] = updated;
      } else {
        _fields.add(updated);
      }
      // A required fact counts as found once any non-rejected field of
      // that kind/role exists (same rule as the backend).
      _missing.removeWhere(
        (m) => _fields.any(
          (f) =>
              f.kind == m.kind &&
              (m.role == null || f.role == m.role) &&
              f.status != 'rejected',
        ),
      );
      _sort();
      _busyFieldId = null;
    });
  }

  void _showError(Object e) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
  }

  Future<void> _run(String busyId, Future<DocumentField> Function() action) async {
    setState(() => _busyFieldId = busyId);
    try {
      final updated = await action();
      if (!mounted) return;
      _upsert(updated);
    } catch (e) {
      if (mounted) setState(() => _busyFieldId = null);
      _showError(e);
    }
  }

  Future<void> _confirm(DocumentField field) => _run(
        field.id,
        () => _service.confirm(caseId: widget.caseId, fieldId: field.id),
      );

  Future<void> _reject(DocumentField field) => _run(
        field.id,
        () => _service.reject(caseId: widget.caseId, fieldId: field.id),
      );

  Future<void> _correct(DocumentField field) async {
    final result = await _askForValue(
      context,
      title: 'Correct ${field.label}',
      kind: field.kind,
      initialRole: field.role,
    );
    if (result == null) return;
    await _run(
      field.id,
      () => _service.confirm(
        caseId: widget.caseId,
        fieldId: field.id,
        value: result.value,
        role: result.role != field.role ? result.role : null,
      ),
    );
  }

  Future<void> _add({String? kind, String? role, String? label}) async {
    final result = await _askForValue(
      context,
      title: label == null ? 'Add a fact' : 'Add the ${label.toLowerCase()}',
      kind: kind,
      initialRole: role,
    );
    if (result == null) return;
    await _run(
      'add',
      () => _service.addFact(
        caseId: widget.caseId,
        documentId: widget.document.id,
        kind: result.kind,
        role: result.kind == 'date' ? result.role : null,
        value: result.value,
      ),
    );
  }

  Future<void> _findMore() async {
    setState(() => _finding = true);
    try {
      final result = await _service.findMoreFacts(
        caseId: widget.caseId,
        documentId: widget.document.id,
      );
      if (!mounted) return;
      for (final f in result.added) {
        _upsert(f);
      }
      final String message;
      if (result.unparseableReply) {
        message = "The AI's answer couldn't be read. Nothing was added.";
      } else if (result.added.isEmpty) {
        message = 'The AI found nothing new in the document.';
      } else {
        message = 'The AI found ${result.added.length} more — check each '
            'against the original.'
            '${result.dropped > 0 ? ' (${result.dropped} suggestion(s) were not in the document and were ignored.)' : ''}';
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    } catch (e) {
      _showError(e);
    } finally {
      if (mounted) setState(() => _finding = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scanned = _fields.any((f) => f.isScanned);
    final pending = _fields.where((f) => f.needsReview).length;
    final hasText = widget.document.rawText != null;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 20,
          bottom: 20 + MediaQuery.of(context).viewInsets.bottom,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Key facts — ${widget.document.docType.label}',
                  style: AppTextStyles.portalTitle,
                ),
                const SizedBox(height: 6),
                Text(
                  scanned
                      ? 'Some of these were read from a scan, which can '
                          'misread numbers. The AI will not use a fact until '
                          'someone checks it against the original paper.'
                      : 'Facts found in this document. Anything marked '
                          '"Needs checking" is hidden from the AI until confirmed.',
                  style: AppTextStyles.cardSubtitle,
                ),
                if (pending > 0) ...[
                  const SizedBox(height: 6),
                  Text(
                    '$pending to check',
                    style: AppTextStyles.cardTitle.copyWith(color: AppColors.warning),
                  ),
                ],
                if (_missing.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  const Text('Not found in this document', style: AppTextStyles.cardTitle),
                  const SizedBox(height: 4),
                  for (final m in _missing)
                    Card(
                      margin: const EdgeInsets.only(bottom: 8),
                      child: ListTile(
                        dense: true,
                        leading: const Icon(Icons.help_outline, color: AppColors.warning),
                        title: Text(_capitalise(m.label), style: AppTextStyles.body),
                        subtitle: const Text(
                          "Couldn't find it. If it's on the paper, add it.",
                          style: AppTextStyles.cardSubtitle,
                        ),
                        trailing: TextButton(
                          onPressed: _busyFieldId == null
                              ? () => _add(kind: m.kind, role: m.role, label: m.label)
                              : null,
                          child: const Text('Add'),
                        ),
                      ),
                    ),
                ],
                const SizedBox(height: 12),
                if (_fields.isEmpty)
                  const Text(
                    'No dates, sections or FIR numbers were found in this document.',
                    style: AppTextStyles.body,
                  )
                else
                  for (final field in _fields)
                    _FieldCard(
                      field: field,
                      busy: _busyFieldId == field.id,
                      onConfirm: () => _confirm(field),
                      onCorrect: () => _correct(field),
                      onReject: () => _reject(field),
                    ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    OutlinedButton.icon(
                      onPressed: _busyFieldId == null ? () => _add() : null,
                      icon: const Icon(Icons.add),
                      label: const Text('Add a fact'),
                    ),
                    if (hasText)
                      OutlinedButton.icon(
                        onPressed: _finding ? null : _findMore,
                        icon: _finding
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.auto_awesome),
                        label: Text(_finding ? 'Looking… (can take a minute)' : 'Find more facts with AI'),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FieldCard extends StatelessWidget {
  const _FieldCard({
    required this.field,
    required this.busy,
    required this.onConfirm,
    required this.onCorrect,
    required this.onReject,
  });

  final DocumentField field;
  final bool busy;
  final VoidCallback onConfirm;
  final VoidCallback onCorrect;
  final VoidCallback onReject;

  (String, StatusTone) get _status {
    switch (field.status) {
      case 'auto_accepted':
        return ('From typed text', StatusTone.success);
      case 'confirmed':
        return (field.isManual ? 'Added by hand' : 'Confirmed', StatusTone.success);
      case 'rejected':
        return ('Marked unclear', StatusTone.danger);
      default:
        return ('Needs checking', StatusTone.warning);
    }
  }

  Color get _confidenceColor {
    if (field.confidence >= 90) return AppColors.success;
    if (field.confidence >= 70) return AppColors.warning;
    return AppColors.danger;
  }

  String? get _foundBy {
    switch (field.extractor) {
      case 'form':
        return 'Found from a label on the form';
      case 'llm':
        return 'Suggested by the AI — check carefully';
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final (statusLabel, statusTone) = _status;
    final foundBy = _foundBy;
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _capitalise(field.label.isEmpty ? field.kind : field.label),
                    style: AppTextStyles.cardTitle,
                  ),
                ),
                StatusBadge(label: statusLabel, tone: statusTone),
              ],
            ),
            const SizedBox(height: 6),
            Text(field.displayValue, style: AppTextStyles.body),
            const SizedBox(height: 4),
            if (field.rawText != null)
              Text(
                'Read as "${field.rawText}"'
                '${field.page != null ? ' · page ${field.page}' : ''}',
                style: AppTextStyles.cardSubtitle,
              ),
            if (foundBy != null)
              Text(foundBy, style: AppTextStyles.cardSubtitle),
            if (field.isScanned && !field.foundByAi)
              Text(
                'Scan confidence: ${field.confidence.round()}%',
                style: AppTextStyles.cardSubtitle.copyWith(color: _confidenceColor),
              ),
            for (final issue in field.issues)
              Text(
                '• ${issue.message}',
                style: AppTextStyles.cardSubtitle.copyWith(
                  color: issue.blocking ? AppColors.danger : AppColors.inkMuted,
                ),
              ),
            if (field.status == 'confirmed' && field.reviewedRole != null)
              Text(
                '${field.isManual ? 'Added' : 'Confirmed'} by ${field.reviewedRole}'
                '${field.wasCorrected ? ' (corrected)' : ''}',
                style: AppTextStyles.cardSubtitle,
              ),
            if (field.needsReview) ...[
              const SizedBox(height: 10),
              if (busy)
                const Align(
                  alignment: Alignment.centerRight,
                  child: SizedBox(
                    width: 22,
                    height: 22,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                )
              else
                Wrap(
                  alignment: WrapAlignment.end,
                  spacing: 8,
                  children: [
                    TextButton(onPressed: onReject, child: const Text("Can't tell")),
                    OutlinedButton(onPressed: onCorrect, child: const Text('Correct it')),
                    FilledButton(
                      // Nothing readable to confirm — it has to be corrected.
                      onPressed: field.value == null ? null : onConfirm,
                      child: const Text('Matches original'),
                    ),
                  ],
                ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Entry {
  const _Entry(this.kind, this.value, this.role);
  final String kind;
  final String value;
  final String? role;
}

/// Dialog for typing a value from the paper original. [kind] null lets the
/// user choose it (free "Add a fact"); dates also get a "this date is
/// the…" choice.
Future<_Entry?> _askForValue(
  BuildContext context, {
  required String title,
  String? kind,
  String? initialRole,
}) async {
  final controller = TextEditingController();
  var chosenKind = kind ?? 'date';
  String? role = initialRole;
  final result = await showDialog<_Entry>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (dialogContext, setDialogState) => AlertDialog(
        title: Text(title),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Type it exactly as it appears on the original paper.',
                style: AppTextStyles.cardSubtitle,
              ),
              const SizedBox(height: 10),
              if (kind == null) ...[
                DropdownButtonFormField<String>(
                  initialValue: chosenKind,
                  decoration: const InputDecoration(
                    labelText: 'What is it?',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final entry in _kinds.entries)
                      DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                  ],
                  onChanged: (value) =>
                      setDialogState(() => chosenKind = value ?? 'date'),
                ),
                const SizedBox(height: 12),
              ],
              TextField(
                controller: controller,
                autofocus: true,
                decoration: InputDecoration(
                  hintText: _hintFor(chosenKind),
                  border: const OutlineInputBorder(),
                ),
              ),
              if (chosenKind == 'date') ...[
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  initialValue: role,
                  decoration: const InputDecoration(
                    labelText: 'This date is the…',
                    border: OutlineInputBorder(),
                  ),
                  items: [
                    for (final entry in _dateRoles.entries)
                      DropdownMenuItem(value: entry.key, child: Text(entry.value)),
                  ],
                  onChanged: (value) => setDialogState(() => role = value),
                ),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              final text = controller.text.trim();
              if (text.isEmpty) return;
              Navigator.of(dialogContext).pop(_Entry(chosenKind, text, role));
            },
            child: const Text('Save'),
          ),
        ],
      ),
    ),
  );
  controller.dispose();
  return result;
}

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/case_event.dart';
import '../services/case_service.dart';
import '../theme/app_theme.dart';

final _dateFormat = DateFormat('MMM d, yyyy');

/// Opens the "log a case event" sheet — add-only (no edit/delete, unlike
/// HearingFormSheet), matching the scope of what case_events needs right
/// now: a write path where none existed, not full CRUD nobody asked for.
/// Returns true if an event was added, so the caller can show a
/// confirmation — the timeline itself is a live StreamBuilder.
Future<bool?> openCaseEventFormSheet(
  BuildContext context, {
  required String caseId,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => CaseEventFormSheet(caseId: caseId),
  );
}

class CaseEventFormSheet extends StatefulWidget {
  const CaseEventFormSheet({super.key, required this.caseId});

  final String caseId;

  @override
  State<CaseEventFormSheet> createState() => _CaseEventFormSheetState();
}

class _CaseEventFormSheetState extends State<CaseEventFormSheet> {
  final _caseService = CaseService();
  final _titleController = TextEditingController();

  DateTime? _date;
  String _eventType = 'other';
  bool _isSubmitting = false;
  String? _errorText;

  @override
  void dispose() {
    _titleController.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _submit() async {
    final title = _titleController.text.trim();
    if (title.isEmpty || _isSubmitting) {
      setState(() => _errorText = title.isEmpty ? 'Enter a title.' : null);
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    try {
      await _caseService.addCaseEvent(
        caseId: widget.caseId,
        title: title,
        date: _date,
        eventType: _eventType,
      );
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSubmitting = false;
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
          const Text('Log Case Event', style: AppTextStyles.portalTitle),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            initialValue: _eventType,
            decoration: const InputDecoration(labelText: 'Type'),
            items: [
              for (final option in caseEventTypeOptions)
                DropdownMenuItem(
                  value: option,
                  child: Text(option.eventTypeLabel),
                ),
            ],
            onChanged: _isSubmitting
                ? null
                : (value) => setState(() => _eventType = value!),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _titleController,
            enabled: !_isSubmitting,
            decoration: const InputDecoration(
              labelText: 'Title (e.g. Charge sheet filed at Sessions Court)',
            ),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _isSubmitting ? null : _pickDate,
            icon: const Icon(Icons.calendar_today),
            label: Text(
              _date == null
                  ? 'Choose date (optional)'
                  : _dateFormat.format(_date!),
            ),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _isSubmitting ? null : _submit,
            child: _isSubmitting
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.surface,
                    ),
                  )
                : const Text('Add Event'),
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

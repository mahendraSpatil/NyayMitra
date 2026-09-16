import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/hearing.dart';
import '../services/case_service.dart';
import '../theme/app_theme.dart';

const _statusOptions = ['scheduled', 'completed', 'adjourned', 'cancelled'];
final _dateFormat = DateFormat('MMM d, yyyy');

/// Opens the add/edit sheet for a single hearing. Pass [existing] to edit;
/// omit it to add a new one. Returns true if the sheet made a change
/// (add, edit, or delete) the caller should refresh for — the hearings
/// list itself is a live StreamBuilder, so this is only used to decide
/// whether to show a confirmation SnackBar.
Future<bool?> openHearingFormSheet(
  BuildContext context, {
  required String caseId,
  Hearing? existing,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => HearingFormSheet(caseId: caseId, existing: existing),
  );
}

class HearingFormSheet extends StatefulWidget {
  const HearingFormSheet({super.key, required this.caseId, this.existing});

  final String caseId;
  final Hearing? existing;

  @override
  State<HearingFormSheet> createState() => _HearingFormSheetState();
}

class _HearingFormSheetState extends State<HearingFormSheet> {
  final _caseService = CaseService();
  late final _courtController =
      TextEditingController(text: widget.existing?.court ?? '');
  late final _purposeController =
      TextEditingController(text: widget.existing?.purpose ?? '');
  late final _notesController =
      TextEditingController(text: widget.existing?.notes ?? '');

  late DateTime? _date = widget.existing?.date;
  late String _status = widget.existing?.status ?? 'scheduled';
  bool _isSubmitting = false;
  String? _errorText;

  bool get _isEditing => widget.existing != null;

  @override
  void dispose() {
    _courtController.dispose();
    _purposeController.dispose();
    _notesController.dispose();
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
    final date = _date;
    if (date == null || _isSubmitting) {
      setState(() => _errorText = date == null ? 'Choose a hearing date.' : null);
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    try {
      if (_isEditing) {
        await _caseService.updateHearing(
          caseId: widget.caseId,
          hearingId: widget.existing!.id,
          date: date,
          court: _courtController.text.trim(),
          purpose: _purposeController.text.trim(),
          status: _status,
          notes: _notesController.text.trim(),
        );
      } else {
        await _caseService.addHearing(
          caseId: widget.caseId,
          date: date,
          court: _courtController.text.trim(),
          purpose: _purposeController.text.trim(),
          status: _status,
          notes: _notesController.text.trim(),
        );
      }
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

  Future<void> _delete() async {
    if (!_isEditing || _isSubmitting) return;
    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });
    try {
      await _caseService.deleteHearing(caseId: widget.caseId, hearingId: widget.existing!.id);
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
          Text(_isEditing ? 'Edit Hearing' : 'Add Hearing', style: AppTextStyles.portalTitle),
          const SizedBox(height: 16),
          OutlinedButton.icon(
            onPressed: _isSubmitting ? null : _pickDate,
            icon: const Icon(Icons.calendar_today),
            label: Text(_date == null ? 'Choose date' : _dateFormat.format(_date!)),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _courtController,
            enabled: !_isSubmitting,
            decoration: const InputDecoration(labelText: 'Court'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _purposeController,
            enabled: !_isSubmitting,
            decoration: const InputDecoration(labelText: 'Purpose (e.g. Arguments)'),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _status,
            decoration: const InputDecoration(labelText: 'Status'),
            items: [
              for (final option in _statusOptions)
                DropdownMenuItem(value: option, child: Text(option)),
            ],
            onChanged: _isSubmitting ? null : (value) => setState(() => _status = value!),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _notesController,
            enabled: !_isSubmitting,
            maxLines: 2,
            decoration: const InputDecoration(labelText: 'Notes (optional)'),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _isSubmitting ? null : _submit,
            child: _isSubmitting
                ? const SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.surface),
                  )
                : Text(_isEditing ? 'Save Changes' : 'Add Hearing'),
          ),
          if (_isEditing) ...[
            const SizedBox(height: 8),
            TextButton(
              onPressed: _isSubmitting ? null : _delete,
              child: const Text('Remove Hearing', style: TextStyle(color: AppColors.danger)),
            ),
          ],
          if (_errorText != null) ...[
            const SizedBox(height: 8),
            Text(
              _errorText!,
              textAlign: TextAlign.center,
              style: AppTextStyles.cardSubtitle.copyWith(color: AppColors.danger),
            ),
          ],
        ],
      ),
    );
  }
}

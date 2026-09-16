import 'package:flutter/material.dart';

import '../services/case_service.dart';
import '../theme/app_theme.dart';

/// Opens the case-creation sheet and, once it closes after a completed
/// (not cancelled) submission, returns the new caseId — the caller
/// decides what to do next (usually pushing the case detail screen).
/// Shared by the Advocate Console and NGO Portal.
Future<String?> openCreateCaseSheet(BuildContext context) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => const CreateCaseSheet(),
  );
}

class CreateCaseSheet extends StatefulWidget {
  const CreateCaseSheet({super.key});

  @override
  State<CreateCaseSheet> createState() => _CreateCaseSheetState();
}

class _CreateCaseSheetState extends State<CreateCaseSheet> {
  final _caseService = CaseService();
  final _undertrialController = TextEditingController();
  final _firNumberController = TextEditingController();
  final _courtController = TextEditingController();

  bool _isSubmitting = false;
  String? _errorText;

  @override
  void dispose() {
    _undertrialController.dispose();
    _firNumberController.dispose();
    _courtController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final undertrialName = _undertrialController.text.trim();
    if (undertrialName.isEmpty || _isSubmitting) {
      setState(() => _errorText = undertrialName.isEmpty ? 'Enter a name.' : null);
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    try {
      final caseId = await _caseService.createCase(
        undertrialName: undertrialName,
        firNumber: _firNumberController.text.trim(),
        court: _courtController.text.trim(),
      );
      if (!mounted) return;
      Navigator.of(context).pop(caseId);
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
          const Text('New Case', style: AppTextStyles.portalTitle),
          const SizedBox(height: 16),
          TextField(
            controller: _undertrialController,
            enabled: !_isSubmitting,
            decoration: const InputDecoration(labelText: 'Undertrial name'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _firNumberController,
            enabled: !_isSubmitting,
            decoration: const InputDecoration(labelText: 'FIR number (if known)'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _courtController,
            enabled: !_isSubmitting,
            decoration: const InputDecoration(labelText: 'Court (if known)'),
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
                : const Text('Create Case'),
          ),
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

import 'package:flutter/material.dart';

import '../../core/services/case_service.dart';
import '../../core/theme/app_theme.dart';
import 'family_strings.dart';

/// Opens the sheet for a family user with no lawyer to create and own a
/// case themselves. Returns true if a case was created — FamilyHome's
/// familyCases stream picks it up on its own once created (the creator
/// is written as the case's own sole familyUids entry server-side).
///
/// NyayMitra.md's guardrail applies here directly, not just to AI output:
/// someone tracking a detained relative's case may reasonably assume an
/// app like this is pulling from real court records. It isn't — this is
/// whatever the family types in, nothing more — so the disclaimer is
/// shown on the form itself, not just documented in this codebase where
/// only a developer would ever read it.
Future<bool?> openCreateOwnCaseSheet(
  BuildContext context, {
  required FamilyStrings strings,
}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => CreateOwnCaseSheet(strings: strings),
  );
}

class CreateOwnCaseSheet extends StatefulWidget {
  const CreateOwnCaseSheet({super.key, required this.strings});

  final FamilyStrings strings;

  @override
  State<CreateOwnCaseSheet> createState() => _CreateOwnCaseSheetState();
}

class _CreateOwnCaseSheetState extends State<CreateOwnCaseSheet> {
  final _caseService = CaseService();
  final _nameController = TextEditingController();

  bool _isSubmitting = false;
  String? _errorText;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final name = _nameController.text.trim();
    if (name.isEmpty || _isSubmitting) {
      setState(() => _errorText = name.isEmpty ? 'Enter a name.' : null);
      return;
    }

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    try {
      await _caseService.createCase(undertrialName: name);
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
          Text(
            widget.strings.createOwnCaseTitle,
            style: AppTextStyles.portalTitle,
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.warningBg,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              widget.strings.createOwnCaseDisclaimer,
              style: AppTextStyles.cardSubtitle,
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _nameController,
            enabled: !_isSubmitting,
            decoration: InputDecoration(
              labelText: widget.strings.createOwnCaseNameFieldLabel,
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
                : Text(widget.strings.createOwnCaseSubmitLabel),
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

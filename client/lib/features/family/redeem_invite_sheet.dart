import 'package:flutter/material.dart';

import '../../core/services/invite_service.dart';
import '../../core/theme/app_theme.dart';
import 'family_strings.dart';

/// Opens the redeem-invite sheet. Returns true if redemption succeeded —
/// the caller doesn't need the caseId itself, since FamilyHome's
/// familyCases stream picks the newly-joined case up on its own the
/// moment familyUids updates.
Future<bool?> openRedeemInviteSheet(BuildContext context, {required FamilyStrings strings}) {
  return showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.background,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => RedeemInviteSheet(strings: strings),
  );
}

class RedeemInviteSheet extends StatefulWidget {
  const RedeemInviteSheet({super.key, required this.strings});

  final FamilyStrings strings;

  @override
  State<RedeemInviteSheet> createState() => _RedeemInviteSheetState();
}

class _RedeemInviteSheetState extends State<RedeemInviteSheet> {
  final _inviteService = InviteService();
  final _codeController = TextEditingController();

  bool _isSubmitting = false;
  String? _errorText;

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final code = _codeController.text.trim();
    if (code.isEmpty || _isSubmitting) return;

    setState(() {
      _isSubmitting = true;
      _errorText = null;
    });

    try {
      await _inviteService.redeemInvite(code);
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
          Text(widget.strings.redeemInviteDialogTitle, style: AppTextStyles.portalTitle),
          const SizedBox(height: 16),
          TextField(
            controller: _codeController,
            enabled: !_isSubmitting,
            autocorrect: false,
            decoration: InputDecoration(labelText: widget.strings.redeemInviteFieldLabel),
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
                : Text(widget.strings.redeemInviteSubmitLabel),
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

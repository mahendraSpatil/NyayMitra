import 'package:flutter/material.dart';

import '../localization/portal_strings.dart';
import '../services/auth_service.dart';
import '../theme/app_theme.dart';

/// Shared sign-out affordance for every portal header, sitting next to the
/// notification bell. Confirms before signing out; AuthService.signOut()
/// then drives RootRouter back to the sign-in screen.
///
/// No per-portal cleanup happens here — not because there's nothing to
/// clean up (step 5 of the Postgres migration, NyayMitra.md, added real
/// state to clean up: open WebSocket connections, the stored access/
/// refresh tokens), but because AuthService.signOut() already owns all
/// of it centrally: it calls POST /auth/logout, clears secure storage,
/// and force-closes every open socket via WsRegistry.closeAll(), on top
/// of (not instead of) each stream's own connect-on-listen/close-on-
/// cancel lifecycle. This app still has no ChangeNotifier/Provider
/// holding cached case or task data (checked), and each portal's data
/// still lives in `late final` fields on that portal's own State —
/// RootRouter shows SignInScreen for any signed-out user, which fully
/// unmounts and disposes whatever portal was showing, so a fresh sign-in
/// always builds a fresh State rather than reusing one holding a
/// previous session's data.
class PortalSignOutButton extends StatelessWidget {
  const PortalSignOutButton({super.key, required this.locale});

  final String locale;

  Future<void> _confirmAndSignOut(BuildContext context) async {
    final strings = PortalStrings(locale);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(strings.signOutDialogTitle, style: AppTextStyles.cardTitle),
        content: Text(strings.signOutDialogMessage, style: AppTextStyles.body),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: Text(strings.signOutDialogCancel),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(strings.signOutDialogConfirm),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await AuthService().signOut();
    }
  }

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.logout, color: AppColors.ink),
      tooltip: PortalStrings(locale).signOutTooltip,
      onPressed: () => _confirmAndSignOut(context),
    );
  }
}

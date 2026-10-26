import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../models/case.dart';
import '../models/case_document.dart';
import '../models/hearing.dart';
import '../services/auth_service.dart';
import '../services/case_data_service.dart';
import '../services/invite_service.dart';
import '../theme/app_theme.dart';
import '../widgets/case_event_form_sheet.dart';
import '../widgets/document_tile.dart';
import '../widgets/hearing_form_sheet.dart';
import '../widgets/status_badge.dart';
import '../widgets/upload_document_sheet.dart';

final _dateTimeFormat = DateFormat('MMM d, h:mm a');

final _dateFormat = DateFormat('MMM d, yyyy');

/// Shared by the Advocate Console and NGO Portal — a case looks the same
/// either way, but hearing add/edit/remove is only offered to whichever
/// of advocateUid/ngoUids the signed-in user actually is (a family member
/// reading the same case, including one who self-created it, only ever
/// sees the read-only view here). This is a UI convenience only: the
/// backend independently re-authorizes every hearing mutation itself
/// (authorize_case_manager), so hiding the button here is not what makes
/// this safe.
class CaseDetailScreen extends StatefulWidget {
  const CaseDetailScreen({super.key, required this.caseId});

  final String caseId;

  @override
  State<CaseDetailScreen> createState() => _CaseDetailScreenState();
}

class _CaseDetailScreenState extends State<CaseDetailScreen> {
  final _caseDataService = CaseDataService();
  final _inviteService = InviteService();

  // Created once, not inside build() — see the same note on
  // AdvocateHome/NgoHome/FamilyHome: a fresh Stream instance per build()
  // makes StreamBuilder tear down and re-subscribe on every rebuild,
  // including the several rebuilds a route-push animation alone fires.
  late final Stream<Case?> _caseStream = _caseDataService.caseById(
    widget.caseId,
  );
  late final Stream<List<CaseDocument>> _documentsStream = _caseDataService
      .caseDocuments(widget.caseId);
  late final Stream<List<Hearing>> _hearingsStream = _caseDataService
      .caseHearings(widget.caseId);

  // Mirrors CaseMember.is_manager (backend/app/db/models.py) exactly —
  // the advocate, an assigned NGO worker, or (for a self-managed family
  // case) whoever created it. A family member who only joined via invite
  // is a member, not a manager, same as on the backend.
  bool _isManager(Case theCase) {
    final uid = AuthService().currentUser?.uid;
    if (uid == null) return false;
    if (theCase.advocateUid == uid) return true;
    if (theCase.ngoUids.contains(uid)) return true;
    if (theCase.ownerType == 'family' && theCase.createdBy == uid) return true;
    return false;
  }

  Future<void> _generateInvite(BuildContext context) async {
    try {
      final invite = await _inviteService.generateInvite(widget.caseId);
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Invite Code'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Share this code with a family member. It works once and '
                'stops working after it\'s used or after it expires.',
                style: AppTextStyles.cardSubtitle,
              ),
              const SizedBox(height: 16),
              SelectableText(invite.code, style: AppTextStyles.portalTitle),
              const SizedBox(height: 8),
              Text(
                'Expires ${_dateTimeFormat.format(invite.expiresAt.toLocal())}',
                style: AppTextStyles.cardSubtitle,
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () =>
                  Clipboard.setData(ClipboardData(text: invite.code)),
              child: const Text('Copy'),
            ),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Done'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not generate an invite: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Case Details')),
      body: StreamBuilder<Case?>(
        stream: _caseStream,
        builder: (context, caseSnapshot) {
          if (caseSnapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          final theCase = caseSnapshot.data;
          if (theCase == null) {
            return const Center(
              child: Text('Case not found', style: AppTextStyles.body),
            );
          }
          final isManager = _isManager(theCase);

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _CaseInfoCard(theCase: theCase),
              const SizedBox(height: 20),
              FilledButton.icon(
                icon: const Icon(Icons.upload_file),
                label: const Text('Upload Case Document'),
                onPressed: () =>
                    openUploadDocumentSheet(context, caseId: widget.caseId),
              ),
              if (isManager) ...[
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.person_add_alt),
                  label: const Text('Invite Family Member'),
                  onPressed: () => _generateInvite(context),
                ),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  icon: const Icon(Icons.flag_outlined),
                  label: const Text('Log Case Event'),
                  onPressed: () =>
                      openCaseEventFormSheet(context, caseId: widget.caseId),
                ),
              ],
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Hearings', style: AppTextStyles.portalTitle),
                  if (isManager)
                    TextButton.icon(
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('Add'),
                      onPressed: () =>
                          openHearingFormSheet(context, caseId: widget.caseId),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              StreamBuilder<List<Hearing>>(
                stream: _hearingsStream,
                builder: (context, hearingsSnapshot) {
                  if (hearingsSnapshot.connectionState ==
                      ConnectionState.waiting) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  if (hearingsSnapshot.hasError) {
                    return Text(
                      'Could not load hearings: ${hearingsSnapshot.error}',
                      style: AppTextStyles.cardSubtitle.copyWith(
                        color: AppColors.accentRed,
                      ),
                    );
                  }
                  final hearings = hearingsSnapshot.data ?? const <Hearing>[];
                  if (hearings.isEmpty) {
                    return const Text(
                      'No hearings recorded yet.',
                      style: AppTextStyles.cardSubtitle,
                    );
                  }
                  return Column(
                    children: [
                      for (final hearing in hearings)
                        _HearingTile(
                          hearing: hearing,
                          onTap: isManager
                              ? () => openHearingFormSheet(
                                  context,
                                  caseId: widget.caseId,
                                  existing: hearing,
                                )
                              : null,
                        ),
                    ],
                  );
                },
              ),
              const SizedBox(height: 24),
              const Text('Documents', style: AppTextStyles.portalTitle),
              const SizedBox(height: 12),
              StreamBuilder<List<CaseDocument>>(
                stream: _documentsStream,
                builder: (context, docsSnapshot) {
                  if (docsSnapshot.connectionState == ConnectionState.waiting) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  // Surfaced distinctly from "no documents" on purpose: a
                  // permission-denied read (a 403 from the backend) would
                  // otherwise look identical to a genuinely empty document
                  // list.
                  if (docsSnapshot.hasError) {
                    return Text(
                      'Could not load documents: ${docsSnapshot.error}',
                      style: AppTextStyles.cardSubtitle.copyWith(
                        color: AppColors.accentRed,
                      ),
                    );
                  }
                  final documents = docsSnapshot.data ?? const <CaseDocument>[];
                  if (documents.isEmpty) {
                    return const Text(
                      'No documents yet.',
                      style: AppTextStyles.cardSubtitle,
                    );
                  }
                  return Column(
                    children: [
                      for (final document in documents)
                        DocumentTile(caseId: widget.caseId, document: document),
                    ],
                  );
                },
              ),
            ],
          );
        },
      ),
    );
  }
}

class _CaseInfoCard extends StatelessWidget {
  const _CaseInfoCard({required this.theCase});

  final Case theCase;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    theCase.undertrialName,
                    style: AppTextStyles.portalTitle,
                  ),
                ),
                StatusBadge(
                  label: theCase.stageLabel.isEmpty
                      ? theCase.stage
                      : theCase.stageLabel,
                  tone: _tone(theCase.stageTone),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'FIR: ${theCase.firNumber} | ${theCase.court}',
              style: AppTextStyles.cardSubtitle,
            ),
            const Divider(height: 28),
            Text('Advocate', style: AppTextStyles.cardSubtitle),
            const SizedBox(height: 2),
            Text(
              theCase.advocateName.isEmpty
                  ? 'No advocate attached'
                  : theCase.advocateName,
              style: AppTextStyles.cardTitle,
            ),
            const SizedBox(height: 12),
            Text(
              theCase.nextHearingDate == null
                  ? 'No hearing scheduled'
                  : 'Hearing: ${_dateFormat.format(theCase.nextHearingDate!)}',
              style: AppTextStyles.cardSubtitle,
            ),
          ],
        ),
      ),
    );
  }

  StatusTone _tone(CaseStageTone tone) {
    switch (tone) {
      case CaseStageTone.warning:
        return StatusTone.warning;
      case CaseStageTone.success:
        return StatusTone.success;
      case CaseStageTone.info:
        return StatusTone.info;
    }
  }
}

class _HearingTile extends StatelessWidget {
  const _HearingTile({required this.hearing, required this.onTap});

  final Hearing hearing;
  final VoidCallback? onTap;

  StatusTone get _tone {
    switch (hearing.status) {
      case 'completed':
        return StatusTone.success;
      case 'cancelled':
        return StatusTone.danger;
      case 'adjourned':
        return StatusTone.warning;
      default:
        return StatusTone.info;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        onTap: onTap,
        leading: const Icon(Icons.gavel, color: AppColors.inkMuted),
        title: Text(
          hearing.purpose.isEmpty
              ? (hearing.date == null
                    ? 'Hearing'
                    : _dateFormat.format(hearing.date!))
              : hearing.purpose,
          style: AppTextStyles.cardTitle,
        ),
        subtitle: Text(
          [
            if (hearing.date != null) _dateFormat.format(hearing.date!),
            if (hearing.court.isNotEmpty) hearing.court,
          ].join(' • '),
          style: AppTextStyles.cardSubtitle,
        ),
        trailing: StatusBadge(label: hearing.status, tone: _tone),
      ),
    );
  }
}

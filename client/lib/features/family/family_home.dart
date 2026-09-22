import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/models/case.dart';
import '../../core/screens/case_detail_screen.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/case_data_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/case_timeline.dart';
import '../../core/widgets/nyaymitra_fab.dart';
import '../../core/widgets/portal_sign_out_button.dart';
import '../../core/widgets/stat_card.dart';
import '../../core/widgets/status_badge.dart';
import '../../core/widgets/upload_document_sheet.dart';
import '../chatbot/chat_sheet.dart';
import 'create_own_case_sheet.dart';
import 'family_strings.dart';
import 'redeem_invite_sheet.dart';

class FamilyHome extends StatefulWidget {
  const FamilyHome({super.key});

  @override
  State<FamilyHome> createState() => _FamilyHomeState();
}

class _FamilyHomeState extends State<FamilyHome> {
  final _caseDataService = CaseDataService();

  // Created once, not inside build() — see the same note on
  // AdvocateHome/NgoHome: a fresh Stream instance per build() makes
  // StreamBuilder tear down and re-subscribe unnecessarily.
  late final String _uid = AuthService().currentUser?.uid ?? '';

  // Server-side scoped by familyUids — not a broader query filtered
  // client-side. A family user can only ever match cases that list their
  // own uid; there is no path here that reads other families' cases.
  late final Stream<List<Case>> _casesStream = _caseDataService.familyCases(
    _uid,
  );

  @override
  Widget build(BuildContext context) {
    // AuthService().currentUser, not a stream: /me is the only source of
    // "my own profile" now, already loaded by the time RootRouter ever
    // shows this screen (it only does once AuthService reports a
    // signed-in user), so there's nothing to wait on here the way the
    // old Firestore-backed profile stream needed a StreamBuilder for.
    final locale = resolveFamilyLocale(
      AuthService().currentUser?.preferredLanguage,
    );
    final strings = FamilyStrings(locale);

    // The whole Scaffold (not just the body) is built inside the cases
    // StreamBuilder below: the FAB needs theCase.id to open a
    // case-scoped chat, and that's only available once the cases stream
    // has actually delivered data.
    return StreamBuilder<List<Case>>(
      stream: _casesStream,
      builder: (context, casesSnapshot) {
        if (casesSnapshot.connectionState == ConnectionState.waiting) {
          return _scaffold(
            context: context,
            strings: strings,
            locale: locale,
            caseId: null,
            body: const Center(child: CircularProgressIndicator()),
          );
        }
        if (casesSnapshot.hasError) {
          return _scaffold(
            context: context,
            strings: strings,
            locale: locale,
            caseId: null,
            body: Center(
              child: Text('${casesSnapshot.error}', style: AppTextStyles.body),
            ),
          );
        }

        final cases = casesSnapshot.data ?? const <Case>[];
        if (cases.isEmpty) {
          return _scaffold(
            context: context,
            strings: strings,
            locale: locale,
            caseId: null,
            body: Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(strings.noCaseFound, style: AppTextStyles.body),
                    const SizedBox(height: 20),
                    FilledButton(
                      onPressed: () async {
                        await openRedeemInviteSheet(context, strings: strings);
                      },
                      child: Text(strings.joinCaseButtonLabel),
                    ),
                    const SizedBox(height: 12),
                    OutlinedButton(
                      onPressed: () async {
                        await openCreateOwnCaseSheet(context, strings: strings);
                      },
                      child: Text(strings.createOwnCaseButtonLabel),
                    ),
                  ],
                ),
              ),
            ),
          );
        }

        // Single-case layout, matching the design: a family account
        // maps to one undertrial's case in practice, and nothing
        // here asks for a multi-case switcher.
        final theCase = cases.first;
        final isSelfManaged =
            theCase.ownerType == 'family' && theCase.createdBy == _uid;

        return _scaffold(
          context: context,
          strings: strings,
          locale: locale,
          caseId: theCase.id,
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _FamilyStatRow(
                strings: strings,
                locale: locale,
                theCase: theCase,
              ),
              const SizedBox(height: 20),
              _CaseSummaryCard(
                strings: strings,
                locale: locale,
                theCase: theCase,
              ),
              const SizedBox(height: 24),
              Text(
                strings.actionsSectionHeader,
                style: AppTextStyles.portalTitle,
              ),
              const SizedBox(height: 12),
              FilledButton.icon(
                icon: const Icon(Icons.upload_file),
                label: Text(strings.uploadButtonLabel),
                onPressed: () =>
                    openUploadDocumentSheet(context, caseId: theCase.id),
              ),
              if (isSelfManaged) ...[
                const SizedBox(height: 12),
                // Only for a case this family user created themselves
                // — hearings and invites for an advocate's case are
                // the advocate's to manage, this is the "no lawyer
                // yet" path from CreateOwnCaseSheet catching up to
                // itself: someone has to be able to add hearings and
                // invite the rest of the family, and here nobody but
                // the creator can be that person.
                OutlinedButton.icon(
                  icon: const Icon(Icons.event_note),
                  label: const Text('Manage Hearings & Invites'),
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => CaseDetailScreen(caseId: theCase.id),
                    ),
                  ),
                ),
              ],
              const SizedBox(height: 24),
              Text(
                strings.caseTimelineSectionHeader,
                style: AppTextStyles.portalTitle,
              ),
              const SizedBox(height: 12),
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: CaseTimeline(
                    entries: _timelineEntries(theCase, locale),
                  ),
                ),
              ),
              const SizedBox(height: 80),
            ],
          ),
        );
      },
    );
  }

  Widget _scaffold({
    required BuildContext context,
    required FamilyStrings strings,
    required String locale,
    required String? caseId,
    required Widget body,
  }) {
    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(strings.portalTitle, style: AppTextStyles.portalTitle),
            Text(strings.portalSubtitle, style: AppTextStyles.portalSubtitle),
          ],
        ),
        actions: [
          const Icon(Icons.notifications_none, color: AppColors.ink),
          const SizedBox(width: 8),
          PortalSignOutButton(locale: locale),
        ],
      ),
      floatingActionButton: NyayMitraFab(
        onPressed: () => showChatSheet(context, caseId: caseId),
      ),
      body: body,
    );
  }

  List<CaseTimelineEntry> _timelineEntries(Case theCase, String locale) {
    final dateFormat = DateFormat('d MMM yyyy', locale);
    return theCase.timeline
        .map(
          (entry) => CaseTimelineEntry(
            title: entry.title,
            dateLabel: entry.date == null ? '' : dateFormat.format(entry.date!),
            done: entry.done,
          ),
        )
        .toList();
  }
}

class _FamilyStatRow extends StatelessWidget {
  const _FamilyStatRow({
    required this.strings,
    required this.locale,
    required this.theCase,
  });

  final FamilyStrings strings;
  final String locale;
  final Case theCase;

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('MMM d', locale);
    final numberFormat = NumberFormat.decimalPattern(locale);

    return Row(
      children: [
        Expanded(
          child: StatCard(
            icon: Icons.event,
            accentColor: AppColors.accentRed,
            value: theCase.nextHearingDate == null
                ? '—'
                : dateFormat.format(theCase.nextHearingDate!),
            caption: strings.statNextHearing,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: StatCard(
            icon: Icons.balance,
            accentColor: AppColors.ink,
            value: theCase.stageLabel.isEmpty
                ? theCase.stage
                : theCase.stageLabel,
            caption: strings.statCurrentStage,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: StatCard(
            icon: Icons.folder_outlined,
            accentColor: AppColors.info,
            value: numberFormat.format(theCase.documentCount),
            caption: strings.statDocumentsUploaded,
          ),
        ),
      ],
    );
  }
}

class _CaseSummaryCard extends StatelessWidget {
  const _CaseSummaryCard({
    required this.strings,
    required this.locale,
    required this.theCase,
  });

  final FamilyStrings strings;
  final String locale;
  final Case theCase;

  @override
  Widget build(BuildContext context) {
    final dateFormat = DateFormat('MMM d, yyyy', locale);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const CircleAvatar(
                  backgroundColor: AppColors.background,
                  foregroundColor: AppColors.ink,
                  child: Icon(Icons.person_outline),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        theCase.undertrialName,
                        style: AppTextStyles.cardTitle,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'FIR: ${theCase.firNumber} | ${theCase.court}',
                        style: AppTextStyles.cardSubtitle,
                      ),
                    ],
                  ),
                ),
                StatusBadge(
                  label: strings.activeCaseBadge,
                  tone: StatusTone.success,
                ),
              ],
            ),
            const Divider(height: 28),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        strings.legalRepresentativeLabel,
                        style: AppTextStyles.cardSubtitle,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        theCase.advocateName,
                        style: AppTextStyles.cardTitle,
                      ),
                    ],
                  ),
                ),
                _HearingPill(
                  label: strings.hearingPillLabel,
                  text: theCase.nextHearingDate == null
                      ? strings.noHearingScheduled
                      : dateFormat.format(theCase.nextHearingDate!),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Not a StatusBadge: this pill highlights a value (the hearing date),
/// it doesn't convey a status/tone, so stretching StatusBadge's meaning
/// for a one-off visual match isn't the right call the way extending it
/// with a new tone was in Phase 5.
class _HearingPill extends StatelessWidget {
  const _HearingPill({required this.label, required this.text});

  final String label;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AppColors.ink,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.calendar_today, size: 14, color: AppColors.surface),
          const SizedBox(width: 6),
          Text(
            '$label: $text',
            style: AppTextStyles.badgeLabel.copyWith(color: AppColors.surface),
          ),
        ],
      ),
    );
  }
}

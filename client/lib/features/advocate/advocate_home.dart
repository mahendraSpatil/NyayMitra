import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/models/case.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/firestore_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/filter_chip_row.dart';
import '../../core/widgets/nyaymitra_fab.dart';
import '../../core/widgets/portal_search_field.dart';
import '../../core/widgets/stat_card.dart';
import '../../core/widgets/status_badge.dart';
import '../chatbot/chat_sheet.dart';
import 'case_detail_screen.dart';

const _filterLabels = ['All', 'Hearings Today', 'Bail Pending', 'Drafting'];
final _dateFormat = DateFormat('MMM d, yyyy');

class AdvocateHome extends StatefulWidget {
  const AdvocateHome({super.key});

  @override
  State<AdvocateHome> createState() => _AdvocateHomeState();
}

class _AdvocateHomeState extends State<AdvocateHome> {
  final _firestoreService = FirestoreService();
  final _searchController = TextEditingController();
  int _filterIndex = 0;
  String _query = '';

  // Created once, not inside build(): StreamBuilder treats a new Stream
  // instance as a stream *change* and resubscribes, resetting to its
  // loading state in the process. Search text and filter chips change on
  // every keystroke/tap — if this stream were built fresh in build(),
  // every one of those would tear down and re-establish the Firestore
  // listener instead of just recomputing _filtered() over already-loaded
  // data.
  late final Stream<List<Case>> _docketStream =
      _firestoreService.advocateDocket(FirebaseAuth.instance.currentUser?.uid ?? '');

  @override
  void initState() {
    super.initState();
    _searchController.addListener(() {
      setState(() => _query = _searchController.text.trim().toLowerCase());
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  List<Case> _filtered(List<Case> cases) {
    var result = cases;
    if (_query.isNotEmpty) {
      result = result
          .where((c) =>
              c.undertrialName.toLowerCase().contains(_query) ||
              c.firNumber.toLowerCase().contains(_query))
          .toList();
    }
    switch (_filterIndex) {
      case 1:
        result = result.where((c) => _isToday(c.nextHearingDate)).toList();
      case 2:
        result = result.where((c) => c.stage == 'bail').toList();
      case 3:
        result = result.where((c) => c.stage == 'drafting').toList();
    }
    return result;
  }

  bool _isToday(DateTime? date) {
    if (date == null) return false;
    final now = DateTime.now();
    return date.year == now.year && date.month == now.month && date.day == now.day;
  }

  bool _isWithinWeek(DateTime? date) {
    if (date == null) return false;
    final today = DateTime.now();
    final startOfToday = DateTime(today.year, today.month, today.day);
    final days = date.difference(startOfToday).inDays;
    return days >= 0 && days < 7;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Lawyer Portal', style: AppTextStyles.portalTitle),
            Text('Advocate Console', style: AppTextStyles.portalSubtitle),
          ],
        ),
        actions: [
          const Icon(Icons.notifications_none, color: AppColors.ink),
          const SizedBox(width: 8),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => AuthService().signOut(),
          ),
        ],
      ),
      floatingActionButton: NyayMitraFab(onPressed: () => showChatSheet(context)),
      body: StreamBuilder<List<Case>>(
        stream: _docketStream,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Text('Could not load cases.', style: AppTextStyles.body),
            );
          }

          final docket = snapshot.data ?? const <Case>[];
          final hearingsThisWeek = docket.where((c) => _isWithinWeek(c.nextHearingDate)).length;
          final casesAwaitingFirstDoc = docket.where((c) => c.documentCount == 0).length;
          final visible = _filtered(docket);

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                children: [
                  Expanded(
                    child: StatCard(
                      icon: Icons.gavel,
                      accentColor: AppColors.ink,
                      value: '${docket.length}',
                      caption: 'Active Cases',
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatCard(
                      icon: Icons.event,
                      accentColor: AppColors.accentRed,
                      value: '$hearingsThisWeek',
                      caption: 'Hearings (Wk)',
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatCard(
                      icon: Icons.description_outlined,
                      accentColor: AppColors.info,
                      value: '$casesAwaitingFirstDoc',
                      caption: 'Awaiting First Doc',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              PortalSearchField(
                controller: _searchController,
                hintText: 'Search by client name or FIR number…',
              ),
              const SizedBox(height: 16),
              FilterChipRow(
                labels: _filterLabels,
                selectedIndex: _filterIndex,
                onSelected: (index) => setState(() => _filterIndex = index),
              ),
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Assigned Cases', style: AppTextStyles.portalTitle),
                  Text('Sort by date', style: AppTextStyles.cardSubtitle),
                ],
              ),
              const SizedBox(height: 12),
              if (visible.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text('No cases match.', style: AppTextStyles.cardSubtitle),
                )
              else
                for (final theCase in visible) _CaseListItem(theCase: theCase),
              const SizedBox(height: 80),
            ],
          );
        },
      ),
    );
  }
}

class _CaseListItem extends StatelessWidget {
  const _CaseListItem({required this.theCase});

  final Case theCase;

  String get _initials {
    final parts = theCase.undertrialName.trim().split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first.substring(0, 1).toUpperCase();
    return (parts.first.substring(0, 1) + parts[1].substring(0, 1)).toUpperCase();
  }

  StatusTone get _tone {
    switch (theCase.stageTone) {
      case CaseStageTone.warning:
        return StatusTone.warning;
      case CaseStageTone.success:
        return StatusTone.success;
      case CaseStageTone.info:
        return StatusTone.info;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => CaseDetailScreen(caseId: theCase.id)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: AppColors.background,
                foregroundColor: AppColors.ink,
                child: Text(_initials, style: AppTextStyles.cardTitle),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'State vs. ${theCase.undertrialName}',
                      style: AppTextStyles.cardTitle,
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'FIR: ${theCase.firNumber} | ${theCase.court}',
                      style: AppTextStyles.cardSubtitle,
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        StatusBadge(
                          label: theCase.stageLabel.isEmpty ? theCase.stage : theCase.stageLabel,
                          tone: _tone,
                        ),
                        const Spacer(),
                        if (theCase.nextHearingDate != null) ...[
                          const Icon(Icons.calendar_today, size: 13, color: AppColors.inkMuted),
                          const SizedBox(width: 4),
                          Text(
                            _dateFormat.format(theCase.nextHearingDate!),
                            style: AppTextStyles.cardSubtitle,
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/models/case.dart';
import '../../core/screens/case_detail_screen.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/firestore_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/create_case_sheet.dart';
import '../../core/widgets/status_badge.dart';

final _dateFormat = DateFormat('MMM d, yyyy');

/// NGO Portal's own case list — cases this NGO worker is assigned to via
/// ngoUids, plus the entry point to create a new one. Kept separate from
/// NgoHome (which is task-first) rather than folded in, since tasks and
/// cases are different lists with different filters.
class NgoCaseListScreen extends StatefulWidget {
  const NgoCaseListScreen({super.key});

  @override
  State<NgoCaseListScreen> createState() => _NgoCaseListScreenState();
}

class _NgoCaseListScreenState extends State<NgoCaseListScreen> {
  final _firestoreService = FirestoreService();

  late final Stream<List<Case>> _casesStream = _firestoreService.ngoCases(
    AuthService().currentUser?.uid ?? '',
  );

  Future<void> _createCase(BuildContext context) async {
    final caseId = await openCreateCaseSheet(context);
    if (caseId == null || !context.mounted) return;
    Navigator.of(
      context,
    ).push(MaterialPageRoute(builder: (_) => CaseDetailScreen(caseId: caseId)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('My Cases'),
        actions: [
          IconButton(
            icon: const Icon(Icons.add),
            tooltip: 'New Case',
            onPressed: () => _createCase(context),
          ),
        ],
      ),
      body: StreamBuilder<List<Case>>(
        stream: _casesStream,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Text(
                'Could not load cases: ${snapshot.error}',
                style: AppTextStyles.body,
              ),
            );
          }

          final cases = snapshot.data ?? const <Case>[];
          if (cases.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'No cases assigned yet. Tap + to create one.',
                  style: AppTextStyles.cardSubtitle,
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              for (final theCase in cases) _CaseListItem(theCase: theCase),
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
      child: ListTile(
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => CaseDetailScreen(caseId: theCase.id),
          ),
        ),
        title: Text(
          'State vs. ${theCase.undertrialName}',
          style: AppTextStyles.cardTitle,
        ),
        subtitle: Text(
          'FIR: ${theCase.firNumber} | ${theCase.court}',
          style: AppTextStyles.cardSubtitle,
        ),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            StatusBadge(
              label: theCase.stageLabel.isEmpty
                  ? theCase.stage
                  : theCase.stageLabel,
              tone: _tone,
            ),
            if (theCase.nextHearingDate != null) ...[
              const SizedBox(height: 4),
              Text(
                _dateFormat.format(theCase.nextHearingDate!),
                style: AppTextStyles.cardSubtitle,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/models/case.dart';
import '../../core/models/case_document.dart';
import '../../core/services/firestore_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/status_badge.dart';
import '../../core/widgets/upload_document_sheet.dart';

final _dateFormat = DateFormat('MMM d, yyyy');

class CaseDetailScreen extends StatelessWidget {
  const CaseDetailScreen({super.key, required this.caseId});

  final String caseId;

  @override
  Widget build(BuildContext context) {
    final firestoreService = FirestoreService();

    return Scaffold(
      appBar: AppBar(title: const Text('Case Details')),
      body: StreamBuilder<Case?>(
        stream: firestoreService.caseById(caseId),
        builder: (context, caseSnapshot) {
          if (caseSnapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          final theCase = caseSnapshot.data;
          if (theCase == null) {
            return const Center(child: Text('Case not found', style: AppTextStyles.body));
          }

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              _CaseInfoCard(theCase: theCase),
              const SizedBox(height: 20),
              FilledButton.icon(
                icon: const Icon(Icons.upload_file),
                label: const Text('Upload Case Document'),
                onPressed: () => showModalBottomSheet(
                  context: context,
                  isScrollControlled: true,
                  backgroundColor: AppColors.background,
                  shape: const RoundedRectangleBorder(
                    borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
                  ),
                  builder: (_) => const UploadDocumentSheet(),
                ),
              ),
              const SizedBox(height: 24),
              const Text('Documents', style: AppTextStyles.portalTitle),
              const SizedBox(height: 12),
              StreamBuilder<List<CaseDocument>>(
                stream: firestoreService.caseDocuments(caseId),
                builder: (context, docsSnapshot) {
                  if (docsSnapshot.connectionState == ConnectionState.waiting) {
                    return const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(child: CircularProgressIndicator()),
                    );
                  }
                  // Surfaced distinctly from "no documents" on purpose: a
                  // permission-denied read (e.g. firestore.rules not yet
                  // redeployed with the documents/ subcollection rule)
                  // would otherwise look identical to a genuinely empty
                  // document list.
                  if (docsSnapshot.hasError) {
                    return Text(
                      'Could not load documents: ${docsSnapshot.error}',
                      style: AppTextStyles.cardSubtitle.copyWith(color: AppColors.accentRed),
                    );
                  }
                  final documents = docsSnapshot.data ?? const <CaseDocument>[];
                  if (documents.isEmpty) {
                    return const Text('No documents yet.', style: AppTextStyles.cardSubtitle);
                  }
                  return Column(
                    children: [
                      for (final document in documents) _DocumentTile(document: document),
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
                  child: Text(theCase.undertrialName, style: AppTextStyles.portalTitle),
                ),
                StatusBadge(
                  label: theCase.stageLabel.isEmpty ? theCase.stage : theCase.stageLabel,
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
            Text(theCase.advocateName, style: AppTextStyles.cardTitle),
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

class _DocumentTile extends StatelessWidget {
  const _DocumentTile({required this.document});

  final CaseDocument document;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: ListTile(
        leading: const Icon(Icons.description_outlined, color: AppColors.inkMuted),
        title: Text(document.docType.label, style: AppTextStyles.cardTitle),
        subtitle: Text(
          document.uploadedAt == null
              ? 'Upload pending'
              : _dateFormat.format(document.uploadedAt!),
          style: AppTextStyles.cardSubtitle,
        ),
      ),
    );
  }
}

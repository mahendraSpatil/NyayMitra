import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../widgets/filter_chip_row.dart';
import '../widgets/nyaymitra_fab.dart';
import '../widgets/portal_search_field.dart';
import '../widgets/stat_card.dart';
import '../widgets/status_badge.dart';

/// Every core widget, in every state, on one screen. Debug-only — reached
/// via a floating button RootRouter overlays when kDebugMode is true. Not
/// a portal; nothing here reads Firestore or auth state.
class WidgetGallery extends StatefulWidget {
  const WidgetGallery({super.key});

  @override
  State<WidgetGallery> createState() => _WidgetGalleryState();
}

class _WidgetGalleryState extends State<WidgetGallery> {
  int _filterIndex = 0;
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Widget gallery')),
      floatingActionButton: NyayMitraFab(onPressed: () {}),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const _Section('StatCard'),
          Row(
            children: const [
              Expanded(
                child: StatCard(
                  icon: Icons.event,
                  accentColor: AppColors.accentRed,
                  value: 'Oct 24',
                  caption: 'Next hearing',
                ),
              ),
              SizedBox(width: 12),
              Expanded(
                child: StatCard(
                  icon: Icons.balance,
                  accentColor: AppColors.ink,
                  value: 'Bail Stage',
                  caption: 'Current stage',
                ),
              ),
              SizedBox(width: 12),
              Expanded(
                child: StatCard(
                  icon: Icons.folder,
                  accentColor: AppColors.info,
                  value: '4',
                  caption: 'Uploaded documents',
                ),
              ),
            ],
          ),
          const _Section('PortalSearchField'),
          PortalSearchField(
            controller: _searchController,
            hintText: 'Search by client name or FIR number…',
          ),
          const _Section('FilterChipRow'),
          FilterChipRow(
            labels: const ['All', 'Hearings Today', 'Bail Pending', 'Drafting'],
            selectedIndex: _filterIndex,
            onSelected: (index) => setState(() => _filterIndex = index),
          ),
          const _Section('StatusBadge'),
          const Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              StatusBadge(label: 'Document Review', tone: StatusTone.info),
              StatusBadge(label: 'Bail Hearing Scheduled', tone: StatusTone.warning),
              StatusBadge(label: 'Active Case', tone: StatusTone.success),
            ],
          ),
          const _Section('NyayMitraFab'),
          const Text(
            'Bottom-right of this screen.',
            style: AppTextStyles.cardSubtitle,
          ),
          const SizedBox(height: 80),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 12),
      child: Text(title, style: AppTextStyles.portalTitle),
    );
  }
}

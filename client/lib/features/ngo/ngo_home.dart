import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../core/models/task.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/case_data_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/filter_chip_row.dart';
import '../../core/widgets/nyaymitra_fab.dart';
import '../../core/widgets/portal_search_field.dart';
import '../../core/widgets/portal_sign_out_button.dart';
import '../../core/widgets/stat_card.dart';
import '../../core/widgets/status_badge.dart';
import '../chatbot/chat_sheet.dart';
import 'ngo_case_list_screen.dart';

const _filterLabels = ['All', 'High Priority', 'Visit Needed', 'Documents'];
final _dateFormat = DateFormat('MMM d, yyyy');

class NgoHome extends StatefulWidget {
  const NgoHome({super.key});

  @override
  State<NgoHome> createState() => _NgoHomeState();
}

class _NgoHomeState extends State<NgoHome> {
  final _caseDataService = CaseDataService();
  final _searchController = TextEditingController();
  int _filterIndex = 0;
  String _query = '';

  // Created once, not inside build() — see the same note on AdvocateHome's
  // _docketStream: a fresh Stream instance per build() makes StreamBuilder
  // tear down and re-subscribe on every keystroke/filter tap.
  late final Stream<List<Task>> _taskStream = _caseDataService.ngoTaskList(
    AuthService().currentUser?.uid ?? '',
  );

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

  List<Task> _filtered(List<Task> tasks) {
    var result = tasks;
    if (_query.isNotEmpty) {
      result = result
          .where(
            (t) =>
                t.description.toLowerCase().contains(_query) ||
                t.taskType.taskCategoryLabel.toLowerCase().contains(_query),
          )
          .toList();
    }
    switch (_filterIndex) {
      case 1:
        result = result.where((t) => t.priority == 'high').toList();
      case 2:
        result = result
            .where((t) => t.taskType == 'verification_visit')
            .toList();
      case 3:
        result = result.where((t) => t.taskType == 'translation').toList();
    }
    return result;
  }

  Future<void> _markComplete(BuildContext context, Task task) async {
    try {
      await _caseDataService.markTaskComplete(task.id);
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not mark task complete: $e')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('NGO Portal', style: AppTextStyles.portalTitle),
            Text(
              'Undertrial Support & Legal Aid',
              style: AppTextStyles.portalSubtitle,
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.gavel, color: AppColors.ink),
            tooltip: 'My Cases',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const NgoCaseListScreen()),
            ),
          ),
          const Icon(Icons.notifications_none, color: AppColors.ink),
          const SizedBox(width: 8),
          const PortalSignOutButton(locale: 'en'),
        ],
      ),
      floatingActionButton: NyayMitraFab(
        onPressed: () => showChatSheet(context),
      ),
      body: StreamBuilder<List<Task>>(
        stream: _taskStream,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Text(
                'Could not load tasks: ${snapshot.error}',
                style: AppTextStyles.body,
              ),
            );
          }

          final tasks = snapshot.data ?? const <Task>[];
          final assignedCases = tasks.map((t) => t.caseId).toSet().length;
          final fieldVisitsDue = tasks
              .where((t) => t.taskType == 'verification_visit' && !t.completed)
              .length;
          final highPriorityCount = tasks
              .where((t) => t.priority == 'high' && !t.completed)
              .length;
          final visible = _filtered(tasks);

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                children: [
                  Expanded(
                    child: StatCard(
                      icon: Icons.groups_outlined,
                      accentColor: AppColors.ink,
                      value: '$assignedCases',
                      caption: 'Assigned Cases',
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: StatCard(
                      icon: Icons.directions_walk,
                      accentColor: AppColors.accentRed,
                      value: '$fieldVisitsDue',
                      caption: 'Field Visits Due',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              PortalSearchField(
                controller: _searchController,
                hintText: 'Search by undertrial, task, or location…',
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
                  const Text(
                    'Pending Field & Legal Tasks',
                    style: AppTextStyles.portalTitle,
                  ),
                  Text(
                    '$highPriorityCount High Priority',
                    style: AppTextStyles.cardSubtitle.copyWith(
                      color: AppColors.accentRed,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (visible.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 24),
                  child: Text(
                    'No tasks match.',
                    style: AppTextStyles.cardSubtitle,
                  ),
                )
              else
                for (final task in visible)
                  _TaskListItem(
                    task: task,
                    onMarkComplete: () => _markComplete(context, task),
                  ),
              const SizedBox(height: 80),
            ],
          );
        },
      ),
    );
  }
}

class _TaskListItem extends StatelessWidget {
  const _TaskListItem({required this.task, required this.onMarkComplete});

  final Task task;
  final VoidCallback onMarkComplete;

  IconData get _icon {
    switch (task.taskType) {
      case 'translation':
        return Icons.translate;
      case 'legal_aid_coordination':
        return Icons.diamond_outlined;
      case 'verification_visit':
        return Icons.location_on_outlined;
      default:
        return Icons.assignment_outlined;
    }
  }

  (Color, Color) get _iconColors {
    switch (task.taskType) {
      case 'translation':
        return (AppColors.info, AppColors.infoBg);
      case 'legal_aid_coordination':
        return (AppColors.warning, AppColors.warningBg);
      case 'verification_visit':
        return (AppColors.success, AppColors.successBg);
      default:
        return (AppColors.inkMuted, AppColors.background);
    }
  }

  StatusTone get _priorityTone {
    switch (task.priority) {
      case 'high':
        return StatusTone.danger;
      case 'medium':
        return StatusTone.warning;
      default:
        return StatusTone.info;
    }
  }

  String get _priorityLabel {
    if (task.priority.isEmpty) return '—';
    return task.priority[0].toUpperCase() + task.priority.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final (iconColor, iconBg) = _iconColors;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: iconBg,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(_icon, color: iconColor, size: 20),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(task.description, style: AppTextStyles.cardTitle),
                      const SizedBox(height: 2),
                      Text(
                        task.taskType.taskCategoryLabel,
                        style: AppTextStyles.cardSubtitle,
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                StatusBadge(label: _priorityLabel, tone: _priorityTone),
              ],
            ),
            const Divider(height: 24),
            if (task.completed)
              Row(
                children: [
                  const Icon(
                    Icons.check_circle,
                    size: 18,
                    color: AppColors.success,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    task.completedAt == null
                        ? 'Completed'
                        : 'Completed ${_dateFormat.format(task.completedAt!)}',
                    style: AppTextStyles.cardSubtitle,
                  ),
                ],
              )
            else
              InkWell(
                onTap: onMarkComplete,
                child: Row(
                  children: [
                    const Icon(
                      Icons.check_circle_outline,
                      size: 18,
                      color: AppColors.inkMuted,
                    ),
                    const SizedBox(width: 8),
                    const Text(
                      'Mark Complete',
                      style: AppTextStyles.cardSubtitle,
                    ),
                    const Spacer(),
                    const Icon(
                      Icons.chevron_right,
                      size: 18,
                      color: AppColors.inkMuted,
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// One row in a CaseTimeline. Presentational only — the date is a
/// pre-formatted label, not a DateTime, so locale-specific formatting
/// (Marathi/Hindi included) stays the caller's decision, not this widget's.
class CaseTimelineEntry {
  const CaseTimelineEntry({
    required this.title,
    required this.dateLabel,
    required this.done,
  });

  final String title;
  final String dateLabel;
  final bool done;
}

/// Vertical stepper: a dot per entry connected by a short line. Completed
/// entries get a filled dark dot with a white check; the pending entry
/// gets a hollow outlined dot with muted text.
class CaseTimeline extends StatelessWidget {
  const CaseTimeline({super.key, required this.entries});

  final List<CaseTimelineEntry> entries;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < entries.length; i++)
          _TimelineRow(entry: entries[i], isLast: i == entries.length - 1),
      ],
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({required this.entry, required this.isLast});

  final CaseTimelineEntry entry;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              _Dot(done: entry.done),
              if (!isLast) Expanded(child: Container(width: 2, color: AppColors.border)),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    entry.title,
                    style: entry.done
                        ? AppTextStyles.timelineTitle
                        : AppTextStyles.timelineTitle.copyWith(color: AppColors.inkMuted),
                  ),
                  const SizedBox(height: 2),
                  Text(entry.dateLabel, style: AppTextStyles.cardSubtitle),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.done});

  final bool done;

  static const _size = 22.0;

  @override
  Widget build(BuildContext context) {
    if (done) {
      return Container(
        width: _size,
        height: _size,
        decoration: const BoxDecoration(color: AppColors.ink, shape: BoxShape.circle),
        child: const Icon(Icons.check, size: 14, color: AppColors.surface),
      );
    }
    return Container(
      width: _size,
      height: _size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: AppColors.border, width: 2),
      ),
    );
  }
}

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../core/models/case_document.dart';
import '../../core/models/chat_message.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/verification_tag.dart';
import 'chat_service.dart';

/// Opens the AI Legal Assistant sheet, reachable via NyayMitraFab on every
/// portal. A DraggableScrollableSheet, not a fixed-height dialog, so it can
/// be dragged to expand/collapse like the reference design.
///
/// [caseId] is optional: the FAB is still portal-home-level for Advocate/
/// NGO (no single "current case" there, unchanged from Phase 7), so only
/// Family Portal — which always has exactly one case — passes one.
Future<void> showChatSheet(BuildContext context, {String? caseId}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (context) => DraggableScrollableSheet(
      initialChildSize: 0.85,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      expand: false,
      builder: (context, scrollController) =>
          _ChatSheetBody(scrollController: scrollController, caseId: caseId),
    ),
  );
}

class _ChatSheetBody extends StatefulWidget {
  const _ChatSheetBody({required this.scrollController, this.caseId});

  final ScrollController scrollController;
  final String? caseId;

  @override
  State<_ChatSheetBody> createState() => _ChatSheetBodyState();
}

class _ChatSheetBodyState extends State<_ChatSheetBody> {
  final _chatService = ChatService();
  final _inputController = TextEditingController();
  final _messages = <ChatMessage>[];

  bool _isSending = false;
  PlatformFile? _attachedFile;
  String? _errorText;

  @override
  void dispose() {
    _inputController.dispose();
    super.dispose();
  }

  Future<void> _pickAttachment() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (result.isEmpty) return;
    setState(() => _attachedFile = result.single);
  }

  Future<void> _send() async {
    final text = _inputController.text.trim();
    if (text.isEmpty || _isSending) return;

    setState(() {
      _messages.add(
        ChatMessage(
          id: 'local-${DateTime.now().microsecondsSinceEpoch}',
          role: ChatRole.user,
          text: text,
        ),
      );
      _inputController.clear();
      _attachedFile = null;
      _isSending = true;
      _errorText = null;
    });
    _scrollToBottom();

    try {
      final reply = await _chatService.sendMessage(text, caseId: widget.caseId);
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(
            id: 'local-${DateTime.now().microsecondsSinceEpoch}',
            role: ChatRole.assistant,
            text: reply.text,
            citedDocuments: reply.citedDocuments,
            verificationStatus: reply.verified
                ? VerificationStatus.verified
                : VerificationStatus.unverified,
            citedSections: reply.citedSections,
          ),
        );
        _isSending = false;
      });
    } on ChatUnavailableException catch (e) {
      if (!mounted) return;
      setState(() {
        _isSending = false;
        _errorText = e.toString();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isSending = false;
        _errorText = "Couldn't reach the assistant. Please try again.";
      });
    }
    _scrollToBottom();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!widget.scrollController.hasClients) return;
      widget.scrollController.animateTo(
        widget.scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Column(
        children: [
          _Header(onClose: () => Navigator.of(context).pop()),
          const Divider(height: 1),
          Expanded(
            child: ListView(
              controller: widget.scrollController,
              padding: const EdgeInsets.all(16),
              children: [
                const _AssistantGreeting(),
                for (final message in _messages)
                  _MessageBubble(message: message),
                if (_isSending) const _PendingBubble(),
                if (_errorText != null) _ErrorBubble(text: _errorText!),
              ],
            ),
          ),
          if (_attachedFile != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Chip(
                  label: Text(_attachedFile!.name),
                  onDeleted: () => setState(() => _attachedFile = null),
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                IconButton(
                  icon: const Icon(
                    Icons.attach_file,
                    color: AppColors.inkMuted,
                  ),
                  onPressed: _pickAttachment,
                ),
                Expanded(
                  child: TextField(
                    controller: _inputController,
                    style: AppTextStyles.body,
                    decoration: const InputDecoration(
                      hintText: 'Ask in plain language…',
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton.filled(
                  style: IconButton.styleFrom(backgroundColor: AppColors.ink),
                  icon: const Icon(
                    Icons.send,
                    color: AppColors.surface,
                    size: 18,
                  ),
                  onPressed: _isSending ? null : _send,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.onClose});

  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 8, 12),
      child: Row(
        children: [
          const Icon(Icons.balance, color: AppColors.ink, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child: Text('AI Legal Assistant', style: AppTextStyles.portalTitle),
          ),
          IconButton(
            icon: const Icon(Icons.close, color: AppColors.inkMuted),
            onPressed: onClose,
          ),
        ],
      ),
    );
  }
}

class _AssistantGreeting extends StatelessWidget {
  const _AssistantGreeting();

  @override
  Widget build(BuildContext context) {
    // Static UI copy, not a ChatMessage: it's not a claim from the
    // backend, so it gets no VerificationTag — attaching one would
    // wrongly imply this canned greeting needs verification.
    return const Align(
      alignment: Alignment.centerLeft,
      child: _Bubble(
        text:
            'Namaste! I am NyayMitra AI. You can ask questions or upload a legal '
            'document for me to analyze.',
        isUser: false,
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message});

  final ChatMessage message;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == ChatRole.user;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        crossAxisAlignment: isUser
            ? CrossAxisAlignment.end
            : CrossAxisAlignment.start,
        children: [
          Align(
            alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
            child: _Bubble(text: message.text, isUser: isUser),
          ),
          if (!isUser) ...[
            const SizedBox(height: 6),
            VerificationTag(
              verified:
                  message.verificationStatus == VerificationStatus.verified,
              citedSections: message.citedSections,
            ),
            if (message.citedDocuments.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                'Referenced: ${message.citedDocuments.map((d) => docTypeFromApiValue(d.docType).label).join(", ")}',
                style: AppTextStyles.cardSubtitle,
              ),
            ],
          ],
        ],
      ),
    );
  }
}

class _PendingBubble extends StatelessWidget {
  const _PendingBubble();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(top: 12),
      child: Align(
        alignment: Alignment.centerLeft,
        child: _Bubble(
          isUser: false,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                height: 16,
                width: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.inkMuted,
                ),
              ),
              SizedBox(width: 10),
              // A single fixed label, not staged text — there's no
              // signal from the backend distinguishing "reading your
              // document" from "the model is still generating," and
              // guessing which phase is active would just be wrong some
              // of the time for no real benefit.
              Text('Reading your document…', style: AppTextStyles.body),
            ],
          ),
        ),
      ),
    );
  }
}

class _ErrorBubble extends StatelessWidget {
  const _ErrorBubble({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: AppColors.dangerBg,
            borderRadius: BorderRadius.circular(14),
          ),
          child: Text(
            text,
            style: AppTextStyles.body.copyWith(color: AppColors.danger),
          ),
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.isUser, this.text, this.child})
    : assert(text != null || child != null);

  final bool isUser;
  final String? text;
  final Widget? child;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxWidth: MediaQuery.of(context).size.width * 0.75,
      ),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? AppColors.ink : AppColors.border,
          borderRadius: BorderRadius.circular(14),
        ),
        child:
            child ??
            Text(
              text!,
              style: AppTextStyles.body.copyWith(
                color: isUser ? AppColors.surface : AppColors.ink,
              ),
            ),
      ),
    );
  }
}

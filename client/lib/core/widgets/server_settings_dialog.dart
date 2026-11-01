import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../theme/app_theme.dart';

/// Server settings. Normally there is nothing to do here: the app finds
/// the server's current address by itself. Typing one in is an override
/// for testing against a different server.
Future<void> showServerSettingsDialog(BuildContext context) {
  return showDialog<void>(
    context: context,
    builder: (_) => const _ServerSettingsDialog(),
  );
}

class _ServerSettingsDialog extends StatefulWidget {
  const _ServerSettingsDialog();

  @override
  State<_ServerSettingsDialog> createState() => _ServerSettingsDialogState();
}

class _ServerSettingsDialogState extends State<_ServerSettingsDialog> {
  late final TextEditingController _controller;
  bool _busy = false;
  String? _message;
  bool _ok = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: ServerConfig.current);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<bool> _check(String root) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final response = await http
          .get(Uri.parse('$root/health'))
          .timeout(const Duration(seconds: 20));
      final reachable = response.statusCode == 200;
      final aiOn = response.body.contains('"llm":true');
      setState(() {
        _ok = reachable;
        _message = reachable
            ? 'Connected.${aiOn ? ' AI is online.' : ' AI is offline (chat will not answer).'}'
            : 'Server answered with ${response.statusCode}.';
      });
      return reachable;
    } on TimeoutException {
      setState(() {
        _ok = false;
        _message = 'No answer in 20 seconds. Is the server running?';
      });
      return false;
    } catch (_) {
      setState(() {
        _ok = false;
        _message = "Can't reach the server. It may be switched off right now.";
      });
      return false;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _useAutomatic() async {
    setState(() => _busy = true);
    await ServerConfig.useAutomatic();
    if (!mounted) return;
    _controller.text = ServerConfig.current;
    await _check(ServerConfig.current);
  }

  Future<void> _saveManual() async {
    final root = ServerConfig.normalize(_controller.text);
    if (root.isEmpty) return;
    if (!await _check(root)) return;
    await ServerConfig.saveManual(root);
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    Navigator.of(context).pop();
    messenger.showSnackBar(SnackBar(content: Text('Server set to $root')));
  }

  @override
  Widget build(BuildContext context) {
    final manual = ServerConfig.isManual;
    return AlertDialog(
      title: const Text('Server'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              manual
                  ? 'Using an address typed in by hand. Tap "Automatic" to '
                      'let the app find the server by itself again.'
                  : 'Automatic: the app finds the server by itself. You '
                      "don't need to change anything here.",
              style: AppTextStyles.cardSubtitle,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _controller,
              keyboardType: TextInputType.url,
              autocorrect: false,
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                labelText: 'Server address',
              ),
            ),
            if (_message != null) ...[
              const SizedBox(height: 10),
              Text(
                _message!,
                style: AppTextStyles.cardSubtitle.copyWith(
                  color: _ok ? AppColors.success : AppColors.danger,
                ),
              ),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : _useAutomatic,
          child: const Text('Automatic'),
        ),
        TextButton(
          onPressed: _busy
              ? null
              : () => _check(ServerConfig.normalize(_controller.text)),
          child: const Text('Test'),
        ),
        FilledButton(
          onPressed: _busy ? null : _saveManual,
          child: _busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Use this'),
        ),
      ],
    );
  }
}

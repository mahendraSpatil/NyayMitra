import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../theme/app_theme.dart';

/// Lets the person point the app at a different backend without a new
/// APK — e.g. today's tunnel address for a demo, or the cloud server.
/// Checks /health before saving so a typo can't strand the app.
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
  bool _checking = false;
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
      _checking = true;
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
    } catch (e) {
      setState(() {
        _ok = false;
        _message = 'Could not reach it: $e';
      });
      return false;
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  Future<void> _save() async {
    final root = ServerConfig.normalize(_controller.text);
    if (root.isEmpty) return;
    if (!await _check(root)) return;
    await ServerConfig.save(root);
    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    Navigator.of(context).pop();
    messenger.showSnackBar(SnackBar(content: Text('Server set to $root')));
  }

  Future<void> _reset() async {
    await ServerConfig.reset();
    if (!mounted) return;
    setState(() {
      _controller.text = ServerConfig.current;
      _message = 'Reset to the built-in default.';
      _ok = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Server'),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Paste the server address you were given, for example '
              'https://something.trycloudflare.com',
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
        if (ServerConfig.isCustom)
          TextButton(
            onPressed: _checking ? null : _reset,
            child: const Text('Reset'),
          ),
        TextButton(
          onPressed: _checking
              ? null
              : () => _check(ServerConfig.normalize(_controller.text)),
          child: const Text('Test'),
        ),
        FilledButton(
          onPressed: _checking ? null : _save,
          child: _checking
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text('Save'),
        ),
      ],
    );
  }
}

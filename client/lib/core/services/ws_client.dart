import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/api_config.dart';
import 'token_storage.dart';

/// Tracks every currently-open WsChannel so sign-out can force-close all
/// of them in one call, on top of (not instead of) each channel's normal
/// close-when-nobody's-listening lifecycle (DataService's
/// _caseStream/_userStream helpers — see firestore_service.dart). Belt
/// and suspenders deliberately: the normal path already closes a
/// channel once its last StreamBuilder unsubscribes, but sign-out
/// shouldn't depend on every widget having unmounted in the right order
/// first.
class WsRegistry {
  WsRegistry._();

  static final _open = <WsChannel>{};

  static void _register(WsChannel channel) => _open.add(channel);
  static void _unregister(WsChannel channel) => _open.remove(channel);

  static void closeAll() {
    for (final channel in _open.toList()) {
      channel.close();
    }
  }
}

/// One reconnecting WebSocket connection to a single /ws/... channel
/// (either /ws/cases/{caseId} or /ws/me), performing the first-message
/// token handshake the backend requires (app/security/ws_auth.py) and
/// reconnecting with exponential backoff on any drop.
///
/// Exposes two streams rather than one: [events] carries the
/// invalidation payloads themselves, and [onConnected] fires once per
/// successful (re)connection, including the very first one.
/// DataService's stream helpers listen to onConnected, not just events,
/// to decide when to refetch — an invalidation sent by the server while
/// this client was disconnected is simply never delivered, so
/// "reconnected" has to be its own trigger to refetch, not just
/// "received an invalidation".
class WsChannel {
  WsChannel(this._path);

  final String _path;

  final _eventsController = StreamController<Map<String, dynamic>>.broadcast();
  final _connectedController = StreamController<void>.broadcast();

  Stream<Map<String, dynamic>> get events => _eventsController.stream;
  Stream<void> get onConnected => _connectedController.stream;

  WebSocketChannel? _socket;
  StreamSubscription<dynamic>? _subscription;
  bool _closed = false;
  int _attempt = 0;

  Future<void> connect() async {
    if (_closed) return;
    WsRegistry._register(this);

    final token = await TokenStorage().accessToken;
    if (token == null || _closed) return; // signed out while this was pending

    try {
      final socket = WebSocketChannel.connect(Uri.parse('$wsBaseUrl$_path'));
      await socket.ready;
      if (_closed) {
        await socket.sink.close();
        return;
      }
      _socket = socket;
      socket.sink.add(jsonEncode({'accessToken': token}));
      _attempt = 0;
      _connectedController.add(null);

      _subscription = socket.stream.listen(
        (raw) {
          try {
            final data = jsonDecode(raw as String) as Map<String, dynamic>;
            _eventsController.add(data);
          } catch (_) {
            // Not a message shape we understand — ignore rather than
            // crash the listener over one bad frame.
          }
        },
        onDone: _scheduleReconnect,
        onError: (_) => _scheduleReconnect(),
        cancelOnError: true,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_closed) return;
    _attempt++;
    final seconds = math.min(30, math.pow(2, _attempt).toInt());
    Future.delayed(Duration(seconds: seconds), connect);
  }

  void close() {
    if (_closed) return;
    _closed = true;
    WsRegistry._unregister(this);
    _subscription?.cancel();
    _socket?.sink.close();
    if (!_eventsController.isClosed) _eventsController.close();
    if (!_connectedController.isClosed) _connectedController.close();
  }
}

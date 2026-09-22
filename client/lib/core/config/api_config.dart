import 'package:flutter/foundation.dart'
    show TargetPlatform, defaultTargetPlatform, kIsWeb;

/// TODO: still a dev-only placeholder — the host is always this machine.
/// Before this reaches a real device, the host itself needs to come from
/// build-time configuration (--dart-define or similar), not a literal
/// "localhost". What already IS handled is per-platform loopback
/// addressing, which a real host config wouldn't remove the need for
/// anyway.
const _devHost = 'localhost';
const _port = 8000;

/// Every backend call in the app goes through this, directly or via
/// ApiClient/WsClient — one place that knows how a given platform reaches
/// this machine, instead of a hardcoded 'localhost' baked into every
/// service file (which is what this app had until step 5 of the Postgres
/// migration, NyayMitra.md).
String get apiBaseUrl {
  final host = _host();
  return 'http://$host:$_port/api/v2';
}

String get wsBaseUrl {
  final host = _host();
  return 'ws://$host:$_port/api/v2';
}

String _host() {
  if (kIsWeb) return _devHost;
  // The Android emulator's own loopback interface is not the host
  // machine's — 10.0.2.2 is the special alias the emulator provides for
  // that. A physical Android device would need the host's real LAN IP
  // instead, which is exactly the kind of thing the TODO above is about;
  // this at least gets the emulator (the actual dev target) working
  // without manual per-run configuration.
  if (defaultTargetPlatform == TargetPlatform.android) return '10.0.2.2';
  return _devHost;
}

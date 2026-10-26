import 'package:url_launcher/url_launcher.dart';

/// Non-web platforms (Windows/Android/iOS/macOS/Linux) — hand off to the
/// OS's own viewer/app via url_launcher, same as before.
Future<bool> openDocumentUrl(String url) {
  return launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
}

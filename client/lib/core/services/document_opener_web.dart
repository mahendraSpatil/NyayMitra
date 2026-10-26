import 'package:web/web.dart' as web;

/// Web only — url_launcher_web's launchUrl has been unreliable for an
/// external (Cloudinary) URL in this app's actual builds (a
/// MissingPluginException at the point of opening a document), so this
/// bypasses the url_launcher plugin channel entirely on web and calls
/// window.open() directly via package:web/dart:js_interop, which has no
/// plugin-channel indirection to go missing in the first place.
Future<bool> openDocumentUrl(String url) async {
  final opened = web.window.open(url, '_blank');
  return opened != null;
}

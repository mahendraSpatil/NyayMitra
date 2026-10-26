import 'document_opener_stub.dart'
    if (dart.library.js_interop) 'document_opener_web.dart'
    as impl;

/// Opens a (Cloudinary-signed) document URL in a new tab/external viewer.
/// The implementation is chosen at compile time — dart.library.js_interop
/// only exists when compiling for web, so a native build (Windows,
/// Android, ...) never even sees package:web's import, avoiding a
/// platform-availability compile error there.
Future<bool> openDocumentUrl(String url) => impl.openDocumentUrl(url);

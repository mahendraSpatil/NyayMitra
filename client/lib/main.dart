import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/debug/widget_gallery.dart';
import 'core/root_router.dart';
import 'core/theme/app_theme.dart';
import 'features/family/family_strings.dart';
import 'firebase_options.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  // Loads date-formatting data for every locale the Family Portal supports,
  // once, at startup — DateFormat(pattern, locale) throws for a locale
  // that hasn't been initialized, and doing this lazily inside the portal
  // would mean the first render with a new locale either needs to await
  // it or risk that throw.
  for (final locale in supportedFamilyLocales) {
    await initializeDateFormatting(locale);
  }
  runApp(const NyayMitraApp());
}

class NyayMitraApp extends StatelessWidget {
  const NyayMitraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NyayMitra AI',
      navigatorKey: _rootNavigatorKey,
      theme: AppTheme.light(),
      home: const RootRouter(),
      builder: (context, child) {
        if (!kDebugMode || child == null) return child ?? const SizedBox.shrink();
        // Debug-only entry point to the widget gallery — never present in
        // a release build, and not part of the real navigation flow.
        return Stack(
          children: [
            child,
            Positioned(
              top: 8,
              right: 8,
              child: SafeArea(
                child: FloatingActionButton.small(
                  heroTag: 'debug-gallery',
                  // No `tooltip:` here deliberately: Tooltip requires an
                  // Overlay ancestor, and this button sits in
                  // MaterialApp.builder's Stack, outside the Navigator
                  // (and therefore outside its Overlay). Adding one back
                  // throws "No Overlay widget found" the moment this
                  // button mounts.
                  onPressed: () => _rootNavigatorKey.currentState?.push(
                    MaterialPageRoute(builder: (_) => const WidgetGallery()),
                  ),
                  child: const Icon(Icons.palette_outlined),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

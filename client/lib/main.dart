import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/root_router.dart';
import 'core/theme/app_theme.dart';
import 'features/family/family_strings.dart';
import 'firebase_options.dart';

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
      theme: AppTheme.light(),
      home: const RootRouter(),
    );
  }
}

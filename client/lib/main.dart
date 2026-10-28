import 'package:flutter/material.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/config/api_config.dart';
import 'core/root_router.dart';
import 'core/theme/app_theme.dart';
import 'features/family/family_strings.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Loads date-formatting data for every locale the Family Portal supports,
  // once, at startup — DateFormat(pattern, locale) throws for a locale
  // that hasn't been initialized, and doing this lazily inside the portal
  // would mean the first render with a new locale either needs to await
  // it or risk that throw.
  for (final locale in supportedFamilyLocales) {
    await initializeDateFormatting(locale);
  }
  // Which backend to talk to — a server address saved in the app wins
  // over the build-time default (api_config.dart).
  await ServerConfig.load();
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

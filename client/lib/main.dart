import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'core/root_router.dart';
import 'firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(const NyayMitraApp());
}

class NyayMitraApp extends StatelessWidget {
  const NyayMitraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'NyayMitra AI',
      theme: ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo)),
      home: const RootRouter(),
    );
  }
}

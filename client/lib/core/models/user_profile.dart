import 'package:cloud_firestore/cloud_firestore.dart';

enum UserRole { advocate, ngo, family }

/// Shared by UserProfile.fromFirestore and RootRouter's ID-token claim
/// parsing — one mapping from the raw string to UserRole, used wherever a
/// role value shows up.
UserRole? parseUserRole(String? value) {
  switch (value) {
    case 'advocate':
      return UserRole.advocate;
    case 'ngo':
      return UserRole.ngo;
    case 'family':
      return UserRole.family;
    default:
      return null;
  }
}

String? _roleToString(UserRole? role) {
  switch (role) {
    case UserRole.advocate:
      return 'advocate';
    case UserRole.ngo:
      return 'ngo';
    case UserRole.family:
      return 'family';
    case null:
      return null;
  }
}

/// Mirrors users/{uid}. Display-only: authorization always reads `role`
/// from the Firebase ID token custom claim, never from this document.
class UserProfile {
  final String uid;
  final UserRole? role;
  final String displayName;
  final String? phone;
  final String? preferredLanguage;

  const UserProfile({
    required this.uid,
    this.role,
    this.displayName = '',
    this.phone,
    this.preferredLanguage,
  });

  factory UserProfile.fromFirestore(
    DocumentSnapshot<Map<String, dynamic>> doc,
  ) {
    final data = doc.data() ?? const {};
    return UserProfile(
      uid: doc.id,
      role: parseUserRole(data['role'] as String?),
      displayName: data['displayName'] as String? ?? '',
      phone: data['phone'] as String?,
      preferredLanguage: data['preferredLanguage'] as String?,
    );
  }

  /// GET /me's response shape (step 5 of the Postgres migration,
  /// NyayMitra.md) — the only source of "my own profile" now; there is
  /// no per-uid profile fetch anymore, only ever the caller's own.
  factory UserProfile.fromApi(Map<String, dynamic> json) {
    return UserProfile(
      uid: json['id'] as String,
      role: parseUserRole(json['role'] as String?),
      displayName: json['displayName'] as String? ?? '',
      phone: json['phone'] as String?,
      preferredLanguage: json['preferredLanguage'] as String?,
    );
  }

  Map<String, dynamic> toFirestore() {
    return {
      'role': _roleToString(role),
      'displayName': displayName,
      'phone': phone,
      'preferredLanguage': preferredLanguage,
    };
  }
}

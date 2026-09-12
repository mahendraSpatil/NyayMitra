import 'package:cloud_firestore/cloud_firestore.dart';

enum UserRole { advocate, ngo, family }

UserRole? _roleFromString(String? value) {
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

  factory UserProfile.fromFirestore(DocumentSnapshot<Map<String, dynamic>> doc) {
    final data = doc.data() ?? const {};
    return UserProfile(
      uid: doc.id,
      role: _roleFromString(data['role'] as String?),
      displayName: data['displayName'] as String? ?? '',
      phone: data['phone'] as String?,
      preferredLanguage: data['preferredLanguage'] as String?,
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

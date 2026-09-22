enum UserRole { advocate, ngo, family }

/// One mapping from the raw string to UserRole, used wherever a role
/// value shows up (UserProfile.fromApi, RootRouter).
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

/// The signed-in user's own profile. Display-only: authorization always
/// reads `role` from the JWT access token, never from this.
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

  /// GET /me's response shape — the only source of "my own profile" now;
  /// there is no per-uid profile fetch anymore, only ever the caller's
  /// own.
  factory UserProfile.fromApi(Map<String, dynamic> json) {
    return UserProfile(
      uid: json['id'] as String,
      role: parseUserRole(json['role'] as String?),
      displayName: json['displayName'] as String? ?? '',
      phone: json['phone'] as String?,
      preferredLanguage: json['preferredLanguage'] as String?,
    );
  }
}

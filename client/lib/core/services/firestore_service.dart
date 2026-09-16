import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';

import '../models/case.dart';
import '../models/case_document.dart';
import '../models/hearing.dart';
import '../models/task.dart';
import '../models/user_profile.dart';

/// The project uses a named Firestore database called "default" (Enterprise
/// edition), not the classic single database literally named "(default)".
/// FirebaseFirestore.instance targets "(default)" unconditionally — every
/// query through it would silently hit an empty, unrelated database.
/// Matches the databaseId in seed.py and firebase.json.
const _databaseId = 'default';

/// Typed reads for each portal, plus the writes each phase has actually
/// needed so far.
class FirestoreService {
  FirestoreService({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instanceFor(
          app: Firebase.app(),
          databaseId: _databaseId,
        );

  final FirebaseFirestore _firestore;

  /// Advocate Console docket: cases owned by this advocate, soonest
  /// hearing first. Uses the advocateUid + nextHearingDate composite index.
  Stream<List<Case>> advocateDocket(String advocateUid) {
    return _firestore
        .collection('cases')
        .where('advocateUid', isEqualTo: advocateUid)
        .orderBy('nextHearingDate')
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => Case.fromFirestore(doc)).toList());
  }

  /// NGO Portal task list for this field worker. Pass [completed] to filter
  /// by completion state; uses the assignedToUid + completed composite index.
  Stream<List<Task>> ngoTaskList(String ngoUid, {bool? completed}) {
    Query<Map<String, dynamic>> query = _firestore
        .collection('tasks')
        .where('assignedToUid', isEqualTo: ngoUid);
    if (completed != null) {
      query = query.where('completed', isEqualTo: completed);
    }
    return query.snapshots().map(
        (snapshot) => snapshot.docs.map((doc) => Task.fromFirestore(doc)).toList());
  }

  /// Family Portal: cases this family member is attached to via familyUids
  /// — including a case they self-created (the creator is also the case's
  /// sole familyUids entry) and cases they joined via an invite.
  Stream<List<Case>> familyCases(String familyUid) {
    return _firestore
        .collection('cases')
        .where('familyUids', arrayContains: familyUid)
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => Case.fromFirestore(doc)).toList());
  }

  /// NGO Portal: cases this NGO worker is assigned to via ngoUids, soonest
  /// hearing first. Uses the ngoUids + nextHearingDate composite index.
  Stream<List<Case>> ngoCases(String ngoUid) {
    return _firestore
        .collection('cases')
        .where('ngoUids', arrayContains: ngoUid)
        .orderBy('nextHearingDate')
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => Case.fromFirestore(doc)).toList());
  }

  /// A case's hearings, soonest first. Read-only here — adding, editing,
  /// or removing a hearing goes through CaseService (backend-mediated,
  /// since it also recomputes the case's nextHearingDate).
  Stream<List<Hearing>> caseHearings(String caseId) {
    return _firestore
        .collection('cases')
        .doc(caseId)
        .collection('hearings')
        .orderBy('date')
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => Hearing.fromFirestore(doc)).toList());
  }

  /// A single case's live document, for a detail screen reached from a list
  /// that already has the caseId. Null if the case doesn't exist (or the
  /// caller can no longer read it).
  Stream<Case?> caseById(String caseId) {
    return _firestore
        .collection('cases')
        .doc(caseId)
        .snapshots()
        .map((doc) => doc.exists ? Case.fromFirestore(doc) : null);
  }

  /// Documents attached to a case, for the Advocate Console's case detail
  /// document list.
  Stream<List<CaseDocument>> caseDocuments(String caseId) {
    return _firestore
        .collection('cases')
        .doc(caseId)
        .collection('documents')
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => CaseDocument.fromFirestore(doc)).toList());
  }

  /// A user's own profile doc — Family Portal reads this for
  /// preferredLanguage. Null if the doc doesn't exist.
  Stream<UserProfile?> userProfile(String uid) {
    return _firestore
        .collection('users')
        .doc(uid)
        .snapshots()
        .map((doc) => doc.exists ? UserProfile.fromFirestore(doc) : null);
  }

  /// NGO Portal completion toggle. Only ever writes completed/completedAt —
  /// firestore.rules enforces the same restriction server-side via
  /// affectedKeys().hasOnly(), so this isn't the only thing standing
  /// between an NGO user and rewriting a task's other fields, just the
  /// client-side half of it. Lets a rejected write surface as a thrown
  /// FirebaseException rather than something the caller has to guess at.
  Future<void> markTaskComplete(String taskId) {
    return _firestore.collection('tasks').doc(taskId).update({
      'completed': true,
      'completedAt': FieldValue.serverTimestamp(),
    });
  }
}

import 'package:cloud_firestore/cloud_firestore.dart';

import '../models/case.dart';
import '../models/task.dart';

/// Typed reads for each portal. Writes come in a later phase.
class FirestoreService {
  FirestoreService({FirebaseFirestore? firestore})
      : _firestore = firestore ?? FirebaseFirestore.instance;

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

  /// Family Portal: cases this family member is attached to via familyUids.
  Stream<List<Case>> familyCases(String familyUid) {
    return _firestore
        .collection('cases')
        .where('familyUids', arrayContains: familyUid)
        .snapshots()
        .map((snapshot) =>
            snapshot.docs.map((doc) => Case.fromFirestore(doc)).toList());
  }
}

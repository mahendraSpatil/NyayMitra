import 'dart:async';
import 'dart:convert';

import '../models/case.dart';
import '../models/case_document.dart';
import '../models/hearing.dart';
import '../models/task.dart';
import 'api_client.dart';
import 'ws_client.dart';

/// Kept named FirestoreService, not renamed, and every method keeps its
/// original signature — every widget does
/// `final _firestoreService = FirestoreService();` and step 5 of the
/// Postgres migration (NyayMitra.md) exists specifically so those call
/// sites don't need to change. It's REST + WebSocket backed now, not
/// Firestore; the name is a historical label at this point, not a
/// description of what's inside.
///
/// Every stream here is the same shape: an initial REST fetch, then a
/// refetch whenever a matching invalidation arrives over the relevant
/// WebSocket channel (app/routers/v2/ws.py) — including right after
/// every (re)connection, not only on an invalidation message, since an
/// invalidation sent while this client was disconnected is simply never
/// delivered and would otherwise leave the stream silently stale until
/// the next real change.
class FirestoreService {
  final _apiClient = ApiClient.instance;

  /// Advocate Console docket: cases owned by this advocate, soonest
  /// hearing first. [advocateUid] is unused — the backend infers "my
  /// cases" from the caller's own access token, not a client-supplied
  /// uid — kept only so this call's signature (and every call site of
  /// it) didn't need to change for step 5.
  Stream<List<Case>> advocateDocket(String advocateUid) => _myCases();

  /// NGO Portal: cases this NGO worker is a member of. Same underlying
  /// endpoint as advocateDocket/familyCases — GET /api/v2/cases already
  /// scopes to "cases I'm a member of" server-side, which is the same
  /// query regardless of role (case_members.role always matches the
  /// caller's own role for every case they've ever been added to).
  Stream<List<Case>> ngoCases(String ngoUid) => _myCases();

  /// Family Portal: cases this family member is attached to — including
  /// a case they self-created and cases they joined via invite. Same
  /// endpoint as the other two.
  Stream<List<Case>> familyCases(String familyUid) => _myCases();

  Stream<List<Case>> _myCases() {
    return _listStream<Case>(
      channel: WsChannel('/ws/me'),
      matchTypes: const {'cases_changed'},
      path: '/cases',
      fromApi: Case.fromApi,
    );
  }

  /// NGO Portal task list for this field worker. [completed] filters by
  /// completion state — passed through to the backend as a query param.
  Stream<List<Task>> ngoTaskList(String ngoUid, {bool? completed}) {
    final query = completed == null ? '' : '?completed=$completed';
    return _listStream<Task>(
      channel: WsChannel('/ws/me'),
      matchTypes: const {'tasks_changed'},
      path: '/tasks$query',
      fromApi: Task.fromApi,
    );
  }

  /// A case's hearings, soonest first. Read-only here — adding, editing,
  /// or removing a hearing goes through CaseService (backend-mediated,
  /// since it also recomputes the case's nextHearingDate).
  Stream<List<Hearing>> caseHearings(String caseId) {
    return _listStream<Hearing>(
      channel: WsChannel('/ws/cases/$caseId'),
      matchTypes: const {'hearings_changed'},
      path: '/cases/$caseId/hearings',
      fromApi: Hearing.fromApi,
    );
  }

  /// A single case's live document, for a detail screen reached from a
  /// list that already has the caseId. Null if the case doesn't exist
  /// (or the caller can no longer read it — a 403 from the backend
  /// collapses to the same "can't show this" null as a 404 would).
  Stream<Case?> caseById(String caseId) {
    return _singleStream<Case>(
      channel: WsChannel('/ws/cases/$caseId'),
      matchTypes: const {
        'hearings_changed',
        'documents_changed',
        'case_members_changed',
      },
      path: '/cases/$caseId',
      fromApi: Case.fromApi,
    );
  }

  /// Documents attached to a case, for the Advocate Console's case detail
  /// document list.
  Stream<List<CaseDocument>> caseDocuments(String caseId) {
    return _listStream<CaseDocument>(
      channel: WsChannel('/ws/cases/$caseId'),
      matchTypes: const {'documents_changed'},
      path: '/cases/$caseId/documents',
      fromApi: CaseDocument.fromApi,
    );
  }

  /// NGO Portal completion toggle. Only ever writes completed/completedAt
  /// — the backend route (PATCH /api/v2/tasks/{id}/complete) takes no
  /// request body at all and only ever touches those two columns, the
  /// structural replacement for what firestore.rules' hasOnly() used to
  /// enforce (NyayMitra.md).
  Future<void> markTaskComplete(String taskId) async {
    final response = await _apiClient.patch('/tasks/$taskId/complete');
    if (response.statusCode != 200) {
      throw FirestoreServiceException(
        _readableError(response.body, response.statusCode),
      );
    }
  }

  Stream<List<T>> _listStream<T>({
    required WsChannel channel,
    required Set<String> matchTypes,
    required String path,
    required T Function(Map<String, dynamic>) fromApi,
  }) {
    return _buildStream<List<T>>(
      channel: channel,
      matchTypes: matchTypes,
      fetch: () async {
        final response = await _apiClient.get(path);
        if (response.statusCode != 200) {
          throw FirestoreServiceException(
            _readableError(response.body, response.statusCode),
          );
        }
        final list = jsonDecode(response.body) as List<dynamic>;
        return list.map((e) => fromApi(e as Map<String, dynamic>)).toList();
      },
    );
  }

  Stream<T?> _singleStream<T>({
    required WsChannel channel,
    required Set<String> matchTypes,
    required String path,
    required T Function(Map<String, dynamic>) fromApi,
  }) {
    return _buildStream<T?>(
      channel: channel,
      matchTypes: matchTypes,
      fetch: () async {
        final response = await _apiClient.get(path);
        if (response.statusCode == 404 || response.statusCode == 403) {
          return null;
        }
        if (response.statusCode != 200) {
          throw FirestoreServiceException(
            _readableError(response.body, response.statusCode),
          );
        }
        return fromApi(jsonDecode(response.body) as Map<String, dynamic>);
      },
    );
  }

  /// The shared plumbing every *Stream method above delegates to: fetch
  /// once immediately (via onListen, not eagerly at call time — nobody
  /// pays for a socket connection or an HTTP round trip for a stream
  /// nobody's listening to yet), refetch on every WebSocket (re)connect
  /// and on every matching invalidation, and close the socket once the
  /// last listener unsubscribes (StreamBuilder's dispose path) rather
  /// than leaking it for the life of the app.
  Stream<T> _buildStream<T>({
    required WsChannel channel,
    required Set<String> matchTypes,
    required Future<T> Function() fetch,
  }) {
    late final StreamController<T> controller;
    StreamSubscription<void>? connectedSub;
    StreamSubscription<Map<String, dynamic>>? eventsSub;

    Future<void> refetch() async {
      try {
        final value = await fetch();
        if (!controller.isClosed) controller.add(value);
      } catch (e, stackTrace) {
        if (!controller.isClosed) controller.addError(e, stackTrace);
      }
    }

    controller = StreamController<T>.broadcast(
      onListen: () {
        connectedSub = channel.onConnected.listen((_) => refetch());
        eventsSub = channel.events.listen((event) {
          if (matchTypes.contains(event['type'])) refetch();
        });
        channel.connect();
      },
      onCancel: () {
        connectedSub?.cancel();
        eventsSub?.cancel();
        channel.close();
      },
    );

    return controller.stream;
  }

  String _readableError(String body, int statusCode) {
    try {
      final json = jsonDecode(body) as Map<String, dynamic>;
      return json['detail']?.toString() ?? body;
    } catch (_) {
      return 'Request failed ($statusCode).';
    }
  }
}

class FirestoreServiceException implements Exception {
  FirestoreServiceException(this.message);

  final String message;

  @override
  String toString() => message;
}

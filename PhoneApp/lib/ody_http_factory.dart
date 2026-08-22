import 'ody_http_factory_stub.dart'
    if (dart.library.io) 'ody_http_factory_io.dart'
    if (dart.library.js_interop) 'ody_http_factory_web.dart'
    if (dart.library.html) 'ody_http_factory_web.dart' as impl;
import 'ody_session.dart';

OdySession createOdySession() => impl.createOdySession();

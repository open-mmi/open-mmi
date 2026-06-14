# CAN runtime configuration roadmap

Current behaviour:

- the daemon currently expects `can0`
- the included udev rule brings up `can0` at `100000`
- this matches the current Seat 1P / VAG PQ35 maintainer-tested setup

This should be revisited in a dedicated beta branch because CAN interface setup affects core runtime behaviour.

Open questions:

- should interface name live in service environment?
- should bitrate live in service environment, udev config, profile metadata, or a separate runtime config?
- should open-mmi bring interfaces up itself or expect SocketCAN to be ready?
- how should `vcan`, `slcan`, USB adapters, OBD capture, and radio-harness capture be represented?
- how should tested capture points be documented per vehicle profile?

Do not mix this with documentation/trust cleanup.

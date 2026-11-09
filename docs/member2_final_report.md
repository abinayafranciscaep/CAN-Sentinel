# CAN-Sentinel — Member 2 Final Work Report

## 1. Project Information

- Project: CAN-Sentinel
- Role: Member 2 — Attack and Sniffer Engineer
- Branch: member-2
- Repository: CAN-Sentinel
- Work areas: attacker/ and sniffer/
- Project period: October–November 2026

## 2. Responsibilities

Member 2 is responsible for:

- Attacker script and attack scenario generation.
- C-based SocketCAN sniffer.
- Unix domain socket bridge.
- Labeled synthetic attack datasets.
- Frame forwarding and socket reliability validation.

## 3. Attacker Framework

The attacker framework supports the following scenarios:

1. Flood
2. Spoof-brake (synthetic)
3. Replay (offline)
4. Fuzz (offline)
5. Masquerade (offline)
6. Diagnostic abuse (synthetic)

Offline attack modules generate or validate synthetic records.
They do not transmit CAN frames.

### Flood safety restrictions

- Interface restricted to vcan0.
- Maximum duration: 5 seconds.
- Maximum rate: 100 frames per second.
- Maximum frame count: 500.
- Dry-run is the default.
- Explicit --execute is required for transmission.

Audit logging records execution events and handles logging failures.

## 4. Synthetic Attack Datasets

The offline dataset generator supports five scenarios:

- spoof_brake
- replay
- fuzz
- masquerade
- diag_abuse

Default generation:

- 3 runs per scenario.
- 5 scenarios.
- 15 total synthetic runs.
- 120-second timeline per run.
- 1-second interval.
- 121 records per run.
- CSV schema:
  timestamp,can_id,dlc,data_hex,label

Each run has a metadata JSON file identifying the data as
synthetic and not transmitted.

These datasets are generated examples, not real vehicle captures.

## 5. Offline Processing Modules

The following modules are implemented and validated:

- replay_offline.py
- fuzz_offline.py
- masquerade_offline.py

They validate or generate synthetic records and CSV outputs.
Offline processing does not transmit CAN frames.

## 6. C CAN Sniffer and Socket Bridge

Member 2 implemented and validated the C CAN sniffer and
Unix domain socket forwarding.

Validation included:

- Strict GCC compilation:
  -Wall -Wextra -Wpedantic -Werror -std=c11
- CAN interface: vcan0.
- Unix socket forwarding.
- Python receiver connection.
- JSON message validation.

A receiver validation completed successfully with 121 JSON
messages received and validated.

Socket access required restricted group permissions during
the latest root-launched validation. The socket was configured
with group adm and mode 0660.

## 7. Isolated vcan0 Replay

A separate vcan replay utility was implemented.

Restrictions:

- Interface fixed to vcan0.
- Maximum 121 frames.
- Maximum duration 120 seconds.
- Maximum rate 1 frame per second.
- Synthetic metadata required.
- Datasets marked as already transmitted are rejected.
- Dry-run is the default.

One fuzz_run_01 synthetic dataset was replayed on vcan0:
121 frames were sent successfully.

This validates isolated virtual-bus replay, not a physical
vehicle or real ECU attack.

## 8. Testing Results

Final Python compilation:

    python3 -m py_compile *.py

Result: Passed.

Final attacker test suite:

    python3 -m unittest discover -s . -p 'test_*.py' -v

Result:

- 111 tests run.
- 111 tests passed.
- 0 failures.
- 0 errors.

Additional validation:

- C sniffer strict compilation: Passed.
- Socket receiver tests: 10 passed.
- vcan replay unit tests: 19 passed.
- Synthetic fixture tests: 5 passed.
- git diff --check: Passed.

Some unit tests use mocks. Their results are not equivalent
to live CAN transmission tests.

## 9. Safety and Limitations

- Testing was restricted to the local virtual CAN interface.
- Offline attack scenarios use synthetic data.
- No physical vehicle or real ECU was targeted.
- The 15 generated scenario runs are offline datasets.
- Only fuzz_run_01 was replayed live on vcan0 in the recorded
  end-to-end replay validation.
- Three live runs for every attack scenario have not been
  established by the available validation evidence.
- No ML detection accuracy or physical attack effectiveness
  is claimed by this report.

## 10. Handoff

The C sniffer forwards CAN frame data as JSON lines through
a Unix domain socket.

The synthetic CSV dataset uses the agreed five-column schema:

    timestamp,can_id,dlc,data_hex,label

The injection log schema is:

    timestamp,can_id,data_hex

These interfaces are intended for integration with the
project's ML and dashboard modules.

## 11. Final Status

Member 2 implementation and automated attacker test suite
have passed the recorded validation.

The consolidated report documents the implemented modules,
synthetic datasets, virtual CAN replay, socket forwarding,
test results, and known limitations.

Git commit and pull request submission remain subject to
the member's final review and approval.

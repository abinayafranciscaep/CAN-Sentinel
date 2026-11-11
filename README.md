# CAN-Sentinel: Automotive ECU Intrusion Detection System

Detects spoofed and malicious CAN bus frames on a virtual Linux SocketCAN network
using rules, statistics and an Isolation Forest model, and flags the attack on a
live dashboard with the suspected ECU ID.

Infotact Solutions Cybersecurity Internship, Project 1 (Oct-Nov 2026)

## Team
| Member | Role |
|---|---|
| Abinaya Francisca EP | Team Lead, Security Lead (threat model, ML engine, integration) |
| Haleem | Member 1, CAN Systems (vcan0, ECU simulators) |
| Chetan | Member 2, Attack Engineer (attacker script, C sniffer) |
| Sadhamail | Member 3, Logging and Dashboard (CSV logger, PyQt dashboard) |

## Architecture
ECU simulators -> vcan0 -> C sniffer -> Unix socket -> ML engine -> alert JSON -> PyQt dashboard

## Folder structure
| Folder | Contents | Owner |
|---|---|---|
| ecu_sim/ | C ECU simulators, vcan0 setup script | Member 1 |
| attacker/ | Attack scripts (lab use on vcan0 only) | Member 2 |
| sniffer/ | C raw CAN socket sniffer, Unix socket bridge | Member 2 |
| ml_engine/ | Feature extraction, Isolation Forest, detection logic | Lead |
| dashboard/ | PyQt dashboard, CSV logger | Member 3 |
| data/ | Sample datasets (large CSVs are not committed) | All |
| docs/ | Threat model, schemas, reports | All |

## Git workflow
- Each member works only on their own branch (member-1, member-2, member-3, lead).
- Commit daily with clear messages.
- Open a Pull Request to main; the team lead reviews and merges.
- Never push to main.

## Safety
All attack code runs only on the isolated virtual bus vcan0 in our own lab setup.

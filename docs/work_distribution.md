# CAN-Sentinel: Work Distribution Document

Oct 6, 2026 · Prepared by Abinaya Francisca EP, Team Lead

Group 3 splits Project 1 (CAN-Sentinel, Automotive ECU Intrusion Detection System) into four owned modules, one per member, along the pipeline ECU simulators → vcan0 → C sniffer → ML engine → PyQt dashboard. Draft v1, to be confirmed at the team kickoff call.

## Team details

| Field | Detail |
| --- | --- |
| Program | Infotact Solutions Cybersecurity Internship |
| Team | Group 3 |
| Project 1 | CAN-Sentinel: Automotive ECU Intrusion Detection System (Advanced Cybersecurity Engineering, Vol. II) |
| Repository | [github.com/abinayafranciscaep/CAN-Sentinel](https://github.com/abinayafranciscaep/CAN-Sentinel) (private) |
| Project 1 period | Oct 5 - Nov 4, 2026 |

| Member | Role | Track | GitHub username | Branch | Owns (folder) |
| --- | --- | --- | --- | --- | --- |
| Abinaya Francisca EP | Team Lead, Security Lead | Track 2 (AI) | abinayafranciscaep | lead | Threat model, ML engine, detection logic, integration (ml\_engine/, docs/) |
| Haleem | Member 1, CAN Systems Engineer | Track 1 (Low-level C) | abdul0haleem | member-1 | vcan0 setup, C ECU simulators (ecu\_sim/) |
| Chetan | Member 2, Attack and Sniffer Engineer | Track 1 (Low-level C) | chetan1876 | member-2 | Attacker script, C sniffer, Unix socket bridge (attacker/, sniffer/) |
| Sadhamail | Member 3, Logging and Dashboard Engineer | Track 2 (UI) | Msadha27 | member-3 | CSV logger, PyQt dashboard, test plan (dashboard/) |

## Project 1: week-wise task distribution

Weeks 1-2 are checked at the mid review (proposed Oct 25); Weeks 3-4 at the final review (proposed Nov 10).

| Week | Abinaya (Lead) | Haleem (Member 1) | Chetan (Member 2) | Sadhamail (Member 3) |
| --- | --- | --- | --- | --- |
| Week 1 (Oct 5-11): environment and design | Repo, branches and workflow setup; threat model (STRIDE, MITRE ATT&CK for ICS); attack catalogue; data schemas; Week 1 design document | vcan0 setup guide for the team (WSL2 or Ubuntu VM); C ECU simulators for brake, steering, RPM, speed, temperature, infotainment | Attacker script skeleton with flood attack; start C sniffer on a raw CAN socket | CSV logger in the agreed 5-column format; first 10-minute normal-traffic CSV |
| Week 2 (Oct 12-18): data and model | Feature extraction (per-ID rate, inter-arrival variance, payload entropy, ID distribution); Isolation Forest training; rules and statistics layers; per-attack evaluation; reusable detection script with README | ECU timing jitter and realistic signal variation; 3 normal runs of 10 min each with Sadhamail | Remaining attacks (spoof\_brake, replay, fuzz, masquerade, diag\_abuse); 3 labeled runs of 2 min per attack; working C sniffer | Log all normal and attack datasets; dashboard layout mock-up; mid review social media video draft |
| Week 3 (Oct 19-25): live integration | Connect ML engine to live sniffer stream; alert JSON output; first threshold tuning; mid review viva preparation | One-command launch script for vcan0 and all ECUs; support socket bridge testing | Unix domain socket bridge from sniffer to ML engine; mid review demo run | Live PyQt dashboard: traffic view, threat gauge, car diagram fed by alert JSON |
| Week 4 (Oct 26-Nov 4): polish and bonus | Final threshold tuning; final evaluation (precision, recall, time-to-detect per attack); incident response playbook; final report | Code cleanup and setup documentation; support for error-frame countermeasure testing | Bonus: error-frame countermeasure against injected frames; attack demo scripts | Dashboard polish; test plan and QA; final demo video and social media video |

All members: one meaningful commit per day on their own branch, a Pull Request when a piece of work is complete, and attendance at both reviews.

## Hand-offs between members

Each module depends on the one before it, so these hand-offs set the critical path.

| From | To | What is handed over | Agreed format | Needed by |
| --- | --- | --- | --- | --- |
| Haleem | Everyone | Working vcan0 and ECU simulators | Setup guide + run script in ecu\_sim/ | Oct 10 |
| Sadhamail | Abinaya | Normal-traffic training data | CSV: timestamp, can\_id, dlc, data\_hex, label | Oct 10 (first file) |
| Chetan | Sadhamail | Labeled attack traffic | Same CSV, with attack injection log for labeling | Oct 16 |
| Chetan | Abinaya | Live frame stream | One JSON line per frame over a Unix domain socket | Oct 22 |
| Abinaya | Sadhamail | Alerts for the dashboard | Alert JSON: timestamp, attack\_type, suspect\_id, confidence, severity, affected\_system, detection\_layer, technique | Oct 22 |

Full schemas are in docs/week1\_design.md in the repository; any change needs team agreement.

## Reviews and GitHub rules

| Review | Window | What is checked | GitHub requirement |
| --- | --- | --- | --- |
| Mid review | Oct 25, 2026 (proposed; official window Oct 20-27) | Weeks 1-2: environment, datasets, trained model; project evaluation, viva, attendance, social media video | Commits on at least 10 different days in the 14 days before the review (Oct 12-25) |
| Final review | Nov 10, 2026 (proposed; official window Nov 5-10) | Weeks 3-4: live integration, dashboard, final report; project evaluation, viva, attendance, social media video | At least one commit every day in the 20 days before the review (Oct 22-Nov 10) |

- Each member commits only to their own branch; main holds merged code only.
- The team lead reviews and merges every Pull Request into main.
- Members reply in the team group within 24 hours; a member unresponsive for 48 hours is reported to Infotact and their tasks are reassigned in this document.

## Project 2 (Month 2)

Roles carry over to Project 2; week-wise tasks will be assigned once the project is allocated, and this document will be updated before Project 2 Week 1.

| Member | Role in Project 2 | Week 1 | Week 2 | Week 3 | Week 4 |
| --- | --- | --- | --- | --- | --- |
| Abinaya Francisca EP | Team Lead | To be assigned | To be assigned | To be assigned | To be assigned |
| Haleem | Member 1 | To be assigned | To be assigned | To be assigned | To be assigned |
| Chetan | Member 2 | To be assigned | To be assigned | To be assigned | To be assigned |
| Sadhamail | Member 3 | To be assigned | To be assigned | To be assigned | To be assigned |

## Sign-off

| Name | Role | Agreed (date) |
| --- | --- | --- |
| Abinaya Francisca EP | Team Lead | Oct 7, 2026 |
| Haleem | Member 1 | Oct 7, 2026 |
| Chetan | Member 2 | Oct 7, 2026 |
| Sadhamail | Member 3 | Oct 7, 2026 |

| Version | Date | Change |
| --- | --- | --- |
| 1.0 | Oct 6, 2026 | First draft, before kickoff call |

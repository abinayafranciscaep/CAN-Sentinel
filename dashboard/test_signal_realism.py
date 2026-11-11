
import csv
import sys
from collections import Counter

CSV_FILE = sys.argv[1] if len(sys.argv) > 1 else "data/normal_run1_1023.csv"

EXPECTED_IDS = {"0x0a0", "0x0b0", "0x100", "0x200", "0x300", "0x600"}
BRAKE_MIN = 2.0
BRAKE_MAX = 6.0
RPM_NOISE_LIMIT = 50
RPM_SPEED_TOLERANCE = 0.03


def read_data(path):
    brake = []
    rpm = []
    speed = []
    id_counts = Counter()
    problems = []

    with open(path, newline="") as file:
        reader = csv.DictReader(file)

        required = {"timestamp", "can_id", "dlc", "data_hex", "label"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"CSV must contain columns: {sorted(required)}")

        for line_no, row in enumerate(reader, start=2):
            try:
                timestamp = float(row["timestamp"])
                can_id = row["can_id"].strip().lower()
                data = bytes.fromhex(row["data_hex"])

                if len(data) != 8 or int(row["dlc"]) != 8:
                    problems.append(f"Line {line_no}: expected 8-byte CAN frame")
                    continue

                id_counts[can_id] += 1

                if can_id == "0x0a0":
                    if data[1] not in (0, 1):
                        problems.append(
                            f"Line {line_no}: invalid brake switch value {data[1]}"
                        )
                    else:
                        brake.append((timestamp, data[1]))

                elif can_id == "0x0100" or can_id == "0x100":
                    value = (data[0] << 8) | data[1]
                    rpm.append((timestamp, value))

                elif can_id == "0x0200" or can_id == "0x200":
                    speed.append((timestamp, data[0]))

            except (ValueError, TypeError, KeyError) as error:
                problems.append(f"Line {line_no}: {error}")

    return brake, rpm, speed, id_counts, problems


def check_brake(brake):
    print("\n=== Brake-switch hold check ===")

    if len(brake) < 2:
        print("INCONCLUSIVE: insufficient brake frames")
        return

    # Sort by timestamp so intervals cannot be negative because of row order.
    brake.sort(key=lambda item: item[0])

    transitions = []
    for i in range(1, len(brake)):
        if brake[i][1] != brake[i - 1][1]:
            transitions.append((brake[i][0], brake[i][1]))

    print(f"Brake frames: {len(brake)}")
    print(f"Brake transitions: {len(transitions)}")

    if len(transitions) < 2:
        print("INCONCLUSIVE: insufficient transitions to measure hold intervals")
        return

    intervals = [
        transitions[i][0] - transitions[i - 1][0]
        for i in range(1, len(transitions))
    ]

    in_range = [duration for duration in intervals
                if BRAKE_MIN <= duration <= BRAKE_MAX]

    print(f"Measured intervals: {len(intervals)}")
    print(f"Minimum interval: {min(intervals):.3f} seconds")
    print(f"Maximum interval: {max(intervals):.3f} seconds")
    print(f"Intervals within 2–6 seconds: {len(in_range)}/{len(intervals)}")

    if len(in_range) == len(intervals):
        print("RESULT: PASS — all measured intervals are within 2–6 seconds")
    else:
        print("RESULT: CHECK — some intervals are outside 2–6 seconds")
        print("First 10 out-of-range intervals:")
        outside = [duration for duration in intervals
                   if not BRAKE_MIN <= duration <= BRAKE_MAX]
        for duration in outside[:10]:
            print(f"  {duration:.3f} seconds")


def check_rpm_speed(rpm, speed):
    print("\n=== RPM-to-speed relationship check ===")

    if not rpm or not speed:
        print("INCONCLUSIVE: RPM or speed frames are missing")
        return

    rpm.sort(key=lambda item: item[0])
    speed.sort(key=lambda item: item[0])

    # Match each speed sample to the nearest RPM timestamp within tolerance.
    matched_errors = []
    j = 0

    for speed_time, speed_value in speed:
        while j + 1 < len(rpm) and abs(rpm[j + 1][0] - speed_time) <= abs(
            rpm[j][0] - speed_time
        ):
            j += 1

        rpm_time, rpm_value = rpm[j]
        if abs(rpm_time - speed_time) > RPM_SPEED_TOLERANCE:
            continue

        expected_rpm = 800 + speed_value * 25
        error = abs(rpm_value - expected_rpm)
        matched_errors.append(error)

    if not matched_errors:
        print("INCONCLUSIVE: no RPM/speed pairs matched within 30 ms")
        return

    passing = sum(error <= RPM_NOISE_LIMIT for error in matched_errors)
    print(f"Matched pairs: {len(matched_errors)}")
    print(f"Pairs within ±{RPM_NOISE_LIMIT} RPM: {passing}/{len(matched_errors)}")
    print(f"Maximum absolute formula error: {max(matched_errors)} RPM")

    if passing == len(matched_errors):
        print("RESULT: PASS — all matched pairs are within the noise limit")
    else:
        print("RESULT: CHECK — some pairs exceed the expected noise limit")


def main():
    print(f"Testing file: {CSV_FILE}")

    try:
        brake, rpm, speed, id_counts, problems = read_data(CSV_FILE)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}")
        return 2

    print("\n=== Frame coverage ===")
    for can_id in sorted(EXPECTED_IDS):
        print(f"{can_id}: {id_counts.get(can_id, 0)} frames")

    missing = EXPECTED_IDS - set(id_counts)
    if missing:
        print("Missing expected CAN IDs:", ", ".join(sorted(missing)))
    else:
        print("All six expected CAN IDs are present.")

    print(f"Malformed/invalid frames found by this script: {len(problems)}")
    for problem in problems[:10]:
        print(" ", problem)

    check_brake(brake)
    check_rpm_speed(rpm, speed)

    print("\nNote: this script checks signal behavior; it does not replace")
    print("the project's CSV validator or baseline/counter checks.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

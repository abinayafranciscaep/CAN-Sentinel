#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L

#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ECU_COUNT 6
#define DLC 8
#define JITTER_US 1000
#define SIGNAL_UPDATE_US 50000L
#define BRAKE_HOLD_MIN_US 2000000L
#define BRAKE_HOLD_MAX_US 6000000L

/* SocketCAN frame structure definition for standalone testing */
struct can_frame {
    uint32_t can_id;
    uint8_t can_dlc;
    uint8_t __pad;
    uint8_t __res0;
    uint8_t len8_dlc;
    uint8_t data[8];
};

typedef struct {
    uint32_t can_id;
    long period_us;
    uint8_t counter;
} TestECU;

static TestECU ecus[ECU_COUNT] = {
    {0x0A0,  20000, 0},  /* Brake: 20 ms */
    {0x0B0,  10000, 0},  /* Steering: 10 ms */
    {0x100,  10000, 0},  /* Engine RPM: 10 ms */
    {0x200,  20000, 0},  /* Vehicle speed: 20 ms */
    {0x300, 100000, 0},  /* Temperature: 100 ms */
    {0x600, 100000, 0}   /* Infotainment: 100 ms */
};

/* Vehicle state signals */
static int brake_pressure = 0;
static int brake_switch = 0;
static int steering_angle = 0;
static int engine_rpm = 2300;
static int vehicle_speed = 60;
static int engine_temp_c = 90;
static uint8_t infotainment_status = 1;

static int clamp_int(int value, int minimum, int maximum)
{
    if (value < minimum) return minimum;
    if (value > maximum) return maximum;
    return value;
}

static long random_range(long minimum, long maximum)
{
    return minimum + (long)(rand() % (unsigned long)(maximum - minimum + 1));
}

static void reset_vehicle_state(void)
{
    brake_pressure = 0;
    brake_switch = 0;
    steering_angle = 0;
    engine_rpm = 2300;
    vehicle_speed = 60;
    engine_temp_c = 90;
    infotainment_status = 1;
    for (int i = 0; i < ECU_COUNT; i++) {
        ecus[i].counter = 0;
    }
}

static void update_vehicle_state_step(void)
{
    if (brake_switch) {
        brake_pressure += (int)random_range(3, 8);
    } else {
        brake_pressure -= (int)random_range(1, 5);
    }
    brake_pressure = clamp_int(brake_pressure, 0, 100);

    vehicle_speed += (int)random_range(-1, 1);
    vehicle_speed = clamp_int(vehicle_speed, 0, 130);

    engine_rpm = clamp_int(
        800 + vehicle_speed * 25 + (int)random_range(-50, 50),
        800,
        4000
    );

    steering_angle += (int)random_range(-10, 10);
    steering_angle = clamp_int(steering_angle, -450, 450);

    engine_temp_c += (int)random_range(-1, 1);
    engine_temp_c = clamp_int(engine_temp_c, 80, 105);

    if (rand() % 1000 == 0) {
        infotainment_status = (uint8_t)(rand() % 2);
    }
}

static void prepare_test_frame(const TestECU *ecu, struct can_frame *frame)
{
    memset(frame, 0, sizeof(*frame));
    frame->can_id = ecu->can_id;
    frame->can_dlc = DLC;

    switch (ecu->can_id) {
        case 0x0A0:
            frame->data[0] = (uint8_t)brake_pressure;
            frame->data[1] = (uint8_t)brake_switch;
            break;

        case 0x0B0: {
            int16_t angle = (int16_t)steering_angle;
            uint16_t encoded_angle = (uint16_t)angle;
            frame->data[0] = (uint8_t)(encoded_angle >> 8);
            frame->data[1] = (uint8_t)(encoded_angle & 0xFF);
            break;
        }

        case 0x100:
            frame->data[0] = (uint8_t)((engine_rpm >> 8) & 0xFF);
            frame->data[1] = (uint8_t)(engine_rpm & 0xFF);
            break;

        case 0x200:
            frame->data[0] = (uint8_t)vehicle_speed;
            break;

        case 0x300:
            frame->data[0] = (uint8_t)(engine_temp_c + 40);
            break;

        case 0x600:
            frame->data[0] = infotainment_status;
            break;

        default:
            break;
    }

    frame->data[7] = ecu->counter;
}

/* ========================================================================= */
/* Test Cases                                                                */
/* ========================================================================= */

/* Test 1: Frame Format (All 6 IDs, DLC 8, reserved bytes 0x00) */
static int test_frame_format(void)
{
    reset_vehicle_state();
    for (int i = 0; i < ECU_COUNT; i++) {
        struct can_frame frame;
        prepare_test_frame(&ecus[i], &frame);

        if (frame.can_id != ecus[i].can_id) return 0;
        if (frame.can_dlc != 8) return 0;

        /* Check reserved bytes are 0x00 */
        if (ecus[i].can_id == 0x0A0) {
            for (int b = 2; b < 7; b++) {
                if (frame.data[b] != 0x00) return 0;
            }
        } else if (ecus[i].can_id == 0x0B0 || ecus[i].can_id == 0x100) {
            for (int b = 2; b < 7; b++) {
                if (frame.data[b] != 0x00) return 0;
            }
        } else if (ecus[i].can_id == 0x200 || ecus[i].can_id == 0x300 || ecus[i].can_id == 0x600) {
            for (int b = 1; b < 7; b++) {
                if (frame.data[b] != 0x00) return 0;
            }
        }
    }
    return 1;
}

/* Test 2: Counter Progression and 255 -> 0 Wrap-around */
static int test_counter_progression(void)
{
    reset_vehicle_state();
    struct can_frame frame;

    for (int i = 0; i < ECU_COUNT; i++) {
        for (int step = 0; step < 300; step++) {
            prepare_test_frame(&ecus[i], &frame);
            uint8_t expected_counter = (uint8_t)(step % 256);
            if (frame.data[7] != expected_counter) return 0;
            ecus[i].counter++;
        }
    }
    return 1;
}

/* Test 3: Steering Angle Encoding & Sign Decoding */
static int test_steering_encoding(void)
{
    reset_vehicle_state();
    struct can_frame frame;

    /* Test 0.0 degrees */
    steering_angle = 0;
    prepare_test_frame(&ecus[1], &frame);
    int16_t decoded = (int16_t)((frame.data[0] << 8) | frame.data[1]);
    if (decoded != 0) return 0;

    /* Test +17.7 degrees (+177) */
    steering_angle = 177;
    prepare_test_frame(&ecus[1], &frame);
    decoded = (int16_t)((frame.data[0] << 8) | frame.data[1]);
    if (decoded != 177) return 0;

    /* Test -17.7 degrees (-177 -> 0xFF4F) */
    steering_angle = -177;
    prepare_test_frame(&ecus[1], &frame);
    decoded = (int16_t)((frame.data[0] << 8) | frame.data[1]);
    if (decoded != -177) return 0;
    if (frame.data[0] != 0xFF || frame.data[1] != 0x4F) return 0;

    /* Test maximum boundaries [-450, +450] */
    steering_angle = 450;
    prepare_test_frame(&ecus[1], &frame);
    decoded = (int16_t)((frame.data[0] << 8) | frame.data[1]);
    if (decoded != 450) return 0;

    steering_angle = -450;
    prepare_test_frame(&ecus[1], &frame);
    decoded = (int16_t)((frame.data[0] << 8) | frame.data[1]);
    if (decoded != -450) return 0;

    return 1;
}

/* Test 4: Engine Temperature Encoding (+40 Offset) */
static int test_temperature_encoding(void)
{
    reset_vehicle_state();
    struct can_frame frame;

    /* Range 80C to 105C -> encoded raw 120 to 145 */
    for (int temp = 80; temp <= 105; temp++) {
        engine_temp_c = temp;
        prepare_test_frame(&ecus[4], &frame);
        if (frame.data[0] != (uint8_t)(temp + 40)) return 0;
        int decoded_c = (int)frame.data[0] - 40;
        if (decoded_c != temp) return 0;
    }
    return 1;
}

/* Test 5: Brake Pressure & Switch Dynamic Coupling (0-100) */
static int test_brake_coupling(void)
{
    reset_vehicle_state();
    srand(42);

    /* Switch ON -> pressure should rise */
    brake_switch = 1;
    brake_pressure = 10;
    int prev_p = brake_pressure;
    for (int i = 0; i < 5; i++) {
        update_vehicle_state_step();
        if (brake_pressure < prev_p && brake_pressure < 100) return 0;
        prev_p = brake_pressure;
    }

    /* Switch OFF -> pressure should fall */
    brake_switch = 0;
    for (int i = 0; i < 20; i++) {
        update_vehicle_state_step();
        if (brake_pressure > prev_p && brake_pressure > 0) return 0;
        prev_p = brake_pressure;
    }

    /* Verify bounds [0, 100] */
    for (int i = 0; i < 100; i++) {
        update_vehicle_state_step();
        if (brake_pressure < 0 || brake_pressure > 100) return 0;
    }

    return 1;
}

/* Test 6: Engine RPM & Vehicle Speed Coupling */
static int test_rpm_speed_coupling(void)
{
    reset_vehicle_state();
    srand(12345);

    for (int i = 0; i < 100; i++) {
        update_vehicle_state_step();
        if (vehicle_speed < 0 || vehicle_speed > 130) return 0;
        if (engine_rpm < 800 || engine_rpm > 4000) return 0;

        /* RPM should stay near 800 + speed * 25 +/- 50 */
        int expected_base = 800 + vehicle_speed * 25;
        if (abs(engine_rpm - expected_base) > 60) return 0;
    }
    return 1;
}

/* Test 7: Deterministic Seed Reproducibility */
static int test_seed_reproducibility(void)
{
    struct can_frame run1[50];
    struct can_frame run2[50];

    /* Run 1 with seed 12345 */
    reset_vehicle_state();
    srand(12345);
    for (int i = 0; i < 50; i++) {
        update_vehicle_state_step();
        prepare_test_frame(&ecus[i % ECU_COUNT], &run1[i]);
    }

    /* Run 2 with same seed 12345 */
    reset_vehicle_state();
    srand(12345);
    for (int i = 0; i < 50; i++) {
        update_vehicle_state_step();
        prepare_test_frame(&ecus[i % ECU_COUNT], &run2[i]);
    }

    /* Compare: must match byte-for-byte */
    for (int i = 0; i < 50; i++) {
        if (memcmp(&run1[i], &run2[i], sizeof(struct can_frame)) != 0) {
            return 0;
        }
    }

    /* Run 3 with different seed 54321: must differ */
    reset_vehicle_state();
    srand(54321);
    int differences = 0;
    for (int i = 0; i < 50; i++) {
        struct can_frame run3_frame;
        update_vehicle_state_step();
        prepare_test_frame(&ecus[i % ECU_COUNT], &run3_frame);
        if (memcmp(&run1[i], &run3_frame, sizeof(struct can_frame)) != 0) {
            differences++;
        }
    }
    if (differences == 0) return 0;

    return 1;
}

/* ========================================================================= */
/* Main Test Runner                                                          */
/* ========================================================================= */

int main(void)
{
    int passed = 0;
    int total = 7;

    printf("====================================================\n");
    printf("   CAN-Sentinel Automated Payload & Protocol Tests   \n");
    printf("====================================================\n\n");

    /* Test 1 */
    if (test_frame_format()) {
        printf("[PASS] Test 1: Frame Format (All 6 IDs, DLC 8, reserved bytes 0x00)\n");
        passed++;
    } else {
        printf("[FAIL] Test 1: Frame Format\n");
    }

    /* Test 2 */
    if (test_counter_progression()) {
        printf("[PASS] Test 2: Counter Progression & Wrap-around (255 -> 0)\n");
        passed++;
    } else {
        printf("[FAIL] Test 2: Counter Progression & Wrap-around\n");
    }

    /* Test 3 */
    if (test_steering_encoding()) {
        printf("[PASS] Test 3: Steering Angle Encoding (-45.0 to +45.0 deg signed)\n");
        passed++;
    } else {
        printf("[FAIL] Test 3: Steering Angle Encoding\n");
    }

    /* Test 4 */
    if (test_temperature_encoding()) {
        printf("[PASS] Test 4: Engine Temperature Encoding (+40 offset, 80-105 C)\n");
        passed++;
    } else {
        printf("[FAIL] Test 4: Engine Temperature Encoding\n");
    }

    /* Test 5 */
    if (test_brake_coupling()) {
        printf("[PASS] Test 5: Brake Pressure & Switch Dynamic Coupling (0-100)\n");
        passed++;
    } else {
        printf("[FAIL] Test 5: Brake Pressure & Switch Coupling\n");
    }

    /* Test 6 */
    if (test_rpm_speed_coupling()) {
        printf("[PASS] Test 6: Engine RPM & Vehicle Speed Coupling (RPM = 800 + speed*25)\n");
        passed++;
    } else {
        printf("[FAIL] Test 6: Engine RPM & Speed Coupling\n");
    }

    /* Test 7 */
    if (test_seed_reproducibility()) {
        printf("[PASS] Test 7: Deterministic Seed Reproducibility (Identical payloads)\n");
        passed++;
    } else {
        printf("[FAIL] Test 7: Seed Reproducibility\n");
    }

    printf("\n====================================================\n");
    printf("Results: %d / %d tests passed (%d failed).\n", passed, total, total - passed);
    printf("====================================================\n");

    return (passed == total) ? EXIT_SUCCESS : EXIT_FAILURE;
}

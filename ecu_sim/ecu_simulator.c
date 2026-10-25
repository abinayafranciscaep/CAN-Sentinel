#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L
#define _GNU_SOURCE

#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define ECU_COUNT 6
#define DLC 8
#define JITTER_US 1000
#define SIGNAL_UPDATE_US 50000L
#define BRAKE_HOLD_MIN_US 2000000L
#define BRAKE_HOLD_MAX_US 6000000L
#define TELEMETRY_INTERVAL_US 5000000L
#define SCHEDULER_SLACK_PERIODS 5

typedef struct {
    canid_t can_id;
    long period_us;
    struct timespec next_send;
    uint8_t counter;
} ECU;

/* Thread configuration for multi-threaded distributed architecture */
typedef struct {
    int id_index;
    canid_t can_id;
    const char *name;
    long period_us;
    int rt_priority;       /* Real-time FIFO priority: 80 for safety-critical, 50 for powertrain, 0 for QM */
    int sched_policy;      /* SCHED_FIFO or SCHED_OTHER */
    uint8_t counter;
} ThreadECUConfig;

/* C11 Lock-free atomic shared vehicle state */
typedef struct {
    atomic_int brake_pressure;
    atomic_int brake_switch;
    atomic_int steering_angle;
    atomic_int engine_rpm;
    atomic_int vehicle_speed;
    atomic_int engine_temp_c;
    atomic_int infotainment_status;
} LockFreeVehicleState;

static volatile sig_atomic_t running = 1;

/* Single-threaded state storage */
static ECU ecus[ECU_COUNT] = {
    {0x0A0,  20000, {0, 0}, 0},  /* Brake: 20 ms */
    {0x0B0,  10000, {0, 0}, 0},  /* Steering: 10 ms */
    {0x100,  10000, {0, 0}, 0},  /* Engine RPM: 10 ms */
    {0x200,  20000, {0, 0}, 0},  /* Vehicle speed: 20 ms */
    {0x300, 100000, {0, 0}, 0},  /* Temperature: 100 ms */
    {0x600, 100000, {0, 0}, 0}   /* Infotainment: 100 ms */
};

/* Multi-threaded ECU specifications with real-time priority mappings */
static ThreadECUConfig thread_configs[ECU_COUNT] = {
    {0, 0x0A0, "Brake",        20000, 80, SCHED_FIFO,  0},  /* ASIL-D: Chassis Safety */
    {1, 0x0B0, "Steering",     10000, 80, SCHED_FIFO,  0},  /* ASIL-D: Chassis Safety */
    {2, 0x100, "Engine RPM",   10000, 50, SCHED_FIFO,  0},  /* ASIL-B: Powertrain */
    {3, 0x200, "Speed",        20000, 50, SCHED_FIFO,  0},  /* ASIL-B: Powertrain */
    {4, 0x300, "Temperature", 100000,  0, SCHED_OTHER, 0},  /* QM: Thermal Monitoring */
    {5, 0x600, "Infotainment", 100000,  0, SCHED_OTHER, 0}   /* QM: Comfort & Media */
};

/* Lock-free state for multi-threaded mode */
static LockFreeVehicleState atomic_state;
static atomic_ulong atomic_total_frames;

/* Single-threaded fallback state variables */
static int st_brake_pressure = 0;
static int st_brake_switch = 0;
static int st_steering_angle = 0;
static int st_engine_rpm = 2300;
static int st_vehicle_speed = 60;
static int st_engine_temp_c = 90;
static uint8_t st_infotainment_status = 1;

static struct timespec next_signal_update;
static struct timespec next_brake_toggle;

static void handle_signal(int signal_number)
{
    (void)signal_number;
    running = 0;
}

static long timespec_diff_us(const struct timespec *a,
                             const struct timespec *b)
{
    return (a->tv_sec - b->tv_sec) * 1000000L
         + (a->tv_nsec - b->tv_nsec) / 1000L;
}

static struct timespec add_us(struct timespec t, long us)
{
    t.tv_nsec += (us % 1000000L) * 1000L;
    t.tv_sec += us / 1000000L;

    if (t.tv_nsec >= 1000000000L) {
        t.tv_sec++;
        t.tv_nsec -= 1000000000L;
    }

    if (t.tv_nsec < 0) {
        t.tv_sec--;
        t.tv_nsec += 1000000000L;
    }

    return t;
}

static long random_jitter_us(void)
{
    return (long)(rand() % (2 * JITTER_US + 1)) - JITTER_US;
}

static int clamp_int(int value, int minimum, int maximum)
{
    if (value < minimum) {
        return minimum;
    }

    if (value > maximum) {
        return maximum;
    }

    return value;
}

static long random_range(long minimum, long maximum)
{
    return minimum
         + (long)(rand() % (unsigned long)(maximum - minimum + 1));
}

/* Helper to open and bind an independent SocketCAN socket to vcan0 */
static int open_vcan_socket(const char *ifname)
{
    int s = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (s < 0) {
        return -1;
    }

    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    strncpy(ifr.ifr_name, ifname, sizeof(ifr.ifr_name) - 1);

    if (ioctl(s, SIOCGIFINDEX, &ifr) < 0) {
        close(s);
        return -1;
    }

    struct sockaddr_can addr;
    memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;

    if (bind(s, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(s);
        return -1;
    }

    return s;
}

/* ============================================================================
 * SINGLE-THREADED ENGINE (Original Rock-Solid Baseline)
 * ============================================================================ */

static void st_update_vehicle_state(const struct timespec *now)
{
    if (timespec_diff_us(now, &next_brake_toggle) >= 0) {
        st_brake_switch = !st_brake_switch;
        long hold_us = random_range(BRAKE_HOLD_MIN_US, BRAKE_HOLD_MAX_US);
        next_brake_toggle = add_us(*now, hold_us);
    }

    if (st_brake_switch) {
        st_brake_pressure += (int)random_range(3, 8);
    } else {
        st_brake_pressure -= (int)random_range(1, 5);
    }
    st_brake_pressure = clamp_int(st_brake_pressure, 0, 100);

    st_vehicle_speed += (int)random_range(-1, 1);
    st_vehicle_speed = clamp_int(st_vehicle_speed, 0, 130);

    st_engine_rpm = clamp_int(
        800 + st_vehicle_speed * 25 + (int)random_range(-50, 50),
        800,
        4000
    );

    st_steering_angle += (int)random_range(-10, 10);
    st_steering_angle = clamp_int(st_steering_angle, -450, 450);

    st_engine_temp_c += (int)random_range(-1, 1);
    st_engine_temp_c = clamp_int(st_engine_temp_c, 80, 105);

    if (rand() % 1000 == 0) {
        st_infotainment_status = (uint8_t)(rand() % 2);
    }
}

static void st_prepare_frame(const ECU *ecu, struct can_frame *frame)
{
    memset(frame, 0, sizeof(*frame));
    frame->can_id = ecu->can_id;
    frame->can_dlc = DLC;

    switch (ecu->can_id) {
        case 0x0A0:
            frame->data[0] = (uint8_t)st_brake_pressure;
            frame->data[1] = (uint8_t)st_brake_switch;
            break;

        case 0x0B0: {
            int16_t angle = (int16_t)st_steering_angle;
            uint16_t encoded_angle = (uint16_t)angle;
            frame->data[0] = (uint8_t)(encoded_angle >> 8);
            frame->data[1] = (uint8_t)(encoded_angle & 0xFF);
            break;
        }

        case 0x100:
            frame->data[0] = (uint8_t)((st_engine_rpm >> 8) & 0xFF);
            frame->data[1] = (uint8_t)(st_engine_rpm & 0xFF);
            break;

        case 0x200:
            frame->data[0] = (uint8_t)st_vehicle_speed;
            break;

        case 0x300:
            frame->data[0] = (uint8_t)(st_engine_temp_c + 40);
            break;

        case 0x600:
            frame->data[0] = st_infotainment_status;
            break;

        default:
            break;
    }

    frame->data[7] = ecu->counter;
}

static int st_send_frame(int socket_fd, ECU *ecu)
{
    struct can_frame frame;
    st_prepare_frame(ecu, &frame);

    ssize_t bytes_sent = write(socket_fd, &frame, sizeof(frame));
    if (bytes_sent != (ssize_t)sizeof(frame)) {
        if (bytes_sent < 0) {
            perror("CAN frame transmission failed");
        } else {
            fprintf(stderr, "Incomplete CAN frame transmission\n");
        }
        return -1;
    }

    ecu->counter++;
    return 0;
}

static int run_singlethreaded(long duration_sec)
{
    int socket_fd = open_vcan_socket("vcan0");
    if (socket_fd < 0) {
        perror("Failed to bind CAN socket to vcan0");
        return EXIT_FAILURE;
    }

    struct timespec now;
    struct timespec start_time;
    struct timespec next_telemetry;
    unsigned long total_frames = 0;

    if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
        perror("Failed to read monotonic clock");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    start_time = now;
    next_signal_update = add_us(now, SIGNAL_UPDATE_US);
    next_telemetry = add_us(now, TELEMETRY_INTERVAL_US);
    next_brake_toggle = add_us(now, random_range(BRAKE_HOLD_MIN_US, BRAKE_HOLD_MAX_US));

    for (int i = 0; i < ECU_COUNT; i++) {
        long initial_delay = ecus[i].period_us + random_jitter_us();
        ecus[i].next_send = add_us(now, initial_delay);
    }

    printf("Architecture: Single-Threaded Bounded Scheduler\n");
    printf("CAN interface: vcan0\n");
    printf("Protocol: six periodic ECU frames, DLC 8\n");
    printf("Timing jitter: approximately +/-1 ms\n");
    if (duration_sec > 0) {
        printf("Simulation duration: %ld seconds (auto-stop)\n", duration_sec);
    }
    printf("Press Ctrl+C to stop.\n");
    fflush(stdout);

    while (running) {
        if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
            perror("Failed to read monotonic clock");
            break;
        }

        if (duration_sec > 0 && (now.tv_sec - start_time.tv_sec) >= duration_sec) {
            printf("\n[DURATION] Reached configured duration of %ld seconds. Stopping...\n", duration_sec);
            break;
        }

        if (timespec_diff_us(&now, &next_signal_update) >= 0) {
            st_update_vehicle_state(&now);
            next_signal_update = add_us(next_signal_update, SIGNAL_UPDATE_US);

            while (timespec_diff_us(&now, &next_signal_update) >= 0) {
                next_signal_update = add_us(next_signal_update, SIGNAL_UPDATE_US);
            }
        }

        if (timespec_diff_us(&now, &next_telemetry) >= 0) {
            long elapsed_sec = now.tv_sec - start_time.tv_sec;
            int minutes = (int)(elapsed_sec / 60);
            int seconds = (int)(elapsed_sec % 60);
            double elapsed_s = (double)(now.tv_sec - start_time.tv_sec)
                             + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
            double fps = (elapsed_s > 0.0) ? ((double)total_frames / elapsed_s) : 0.0;
            char brake_info[16];

            if (st_brake_switch) {
                snprintf(brake_info, sizeof(brake_info), "ON (%d%%)", st_brake_pressure);
            } else {
                snprintf(brake_info, sizeof(brake_info), "OFF");
            }

            printf("[TELEMETRY] [%02d:%02d] Frames: %7lu | Rate: %5.1f fps | Speed: %3d km/h | RPM: %4d | Steer: %+5.1f deg | Brake: %s\n",
                   minutes, seconds, total_frames, fps, st_vehicle_speed, st_engine_rpm,
                   (double)st_steering_angle / 10.0, brake_info);
            fflush(stdout);

            next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            while (timespec_diff_us(&now, &next_telemetry) >= 0) {
                next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            }
        }

        for (int i = 0; i < ECU_COUNT && running; i++) {
            if (timespec_diff_us(&now, &ecus[i].next_send) >= 0) {
                if (st_send_frame(socket_fd, &ecus[i]) < 0) {
                    running = 0;
                    break;
                }

                total_frames++;

                if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
                    perror("Failed to read monotonic clock");
                    running = 0;
                    break;
                }

                long interval = ecus[i].period_us + random_jitter_us();
                struct timespec next_deadline = add_us(ecus[i].next_send, interval);
                long max_slack_us = ecus[i].period_us * SCHEDULER_SLACK_PERIODS;

                while (timespec_diff_us(&now, &next_deadline) > max_slack_us) {
                    next_deadline = add_us(next_deadline, interval);
                }

                ecus[i].next_send = next_deadline;
            }
        }

        if (running) {
            struct timespec earliest = ecus[0].next_send;
            for (int i = 1; i < ECU_COUNT; i++) {
                if (timespec_diff_us(&ecus[i].next_send, &earliest) < 0) {
                    earliest = ecus[i].next_send;
                }
            }

            if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
                perror("Failed to read monotonic clock");
                break;
            }

            long wait_us = timespec_diff_us(&earliest, &now);
            if (wait_us >= 2000L) {
                struct timespec delay = {
                    .tv_sec = wait_us / 1000000L,
                    .tv_nsec = (wait_us % 1000000L) * 1000L
                };

                while (nanosleep(&delay, &delay) < 0 && errno == EINTR && running) {
                    /* Resume sleep after interrupt */
                }
            } else if (wait_us > 0) {
                sched_yield();
            }
        }
    }

    close(socket_fd);

    double total_duration_s = (double)(now.tv_sec - start_time.tv_sec)
                            + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
    double avg_fps = (total_duration_s > 0.0) ? ((double)total_frames / total_duration_s) : 0.0;

    printf("\nCAN-Sentinel ECU Simulator stopped.\n");
    printf("Execution summary: %lu frames transmitted in %.2f seconds (average rate: %.2f fps).\n",
           total_frames, total_duration_s, avg_fps);

    return EXIT_SUCCESS;
}

/* ============================================================================
 * MULTI-THREADED DISTRIBUTED ENGINE (pthreads + C11 Lock-Free Atomics)
 * ============================================================================ */

/* Physics simulation worker thread: updates vehicle dynamics every 50 ms */
static void *physics_worker_thread(void *arg)
{
    (void)arg;
    struct timespec next_update;
    struct timespec next_toggle;
    struct timespec now;

    clock_gettime(CLOCK_MONOTONIC, &now);
    next_update = add_us(now, SIGNAL_UPDATE_US);
    next_toggle = add_us(now, random_range(BRAKE_HOLD_MIN_US, BRAKE_HOLD_MAX_US));

    int l_brake_pressure = 0;
    int l_brake_switch = 0;
    int l_steering_angle = 0;
    int l_engine_rpm = 2300;
    int l_vehicle_speed = 60;
    int l_engine_temp_c = 90;
    int l_infotainment = 1;

    while (running) {
        while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_update, NULL) != 0) {
            if (!running) {
                break;
            }
        }
        if (!running) {
            break;
        }

        clock_gettime(CLOCK_MONOTONIC, &now);

        if (timespec_diff_us(&now, &next_toggle) >= 0) {
            l_brake_switch = !l_brake_switch;
            long hold_us = random_range(BRAKE_HOLD_MIN_US, BRAKE_HOLD_MAX_US);
            next_toggle = add_us(now, hold_us);
        }

        if (l_brake_switch) {
            l_brake_pressure += (int)random_range(3, 8);
        } else {
            l_brake_pressure -= (int)random_range(1, 5);
        }
        l_brake_pressure = clamp_int(l_brake_pressure, 0, 100);

        l_vehicle_speed += (int)random_range(-1, 1);
        l_vehicle_speed = clamp_int(l_vehicle_speed, 0, 130);

        l_engine_rpm = clamp_int(
            800 + l_vehicle_speed * 25 + (int)random_range(-50, 50),
            800,
            4000
        );

        l_steering_angle += (int)random_range(-10, 10);
        l_steering_angle = clamp_int(l_steering_angle, -450, 450);

        l_engine_temp_c += (int)random_range(-1, 1);
        l_engine_temp_c = clamp_int(l_engine_temp_c, 80, 105);

        if (rand() % 1000 == 0) {
            l_infotainment = rand() % 2;
        }

        /* Lock-free atomic stores with release semantics */
        atomic_store_explicit(&atomic_state.brake_pressure, l_brake_pressure, memory_order_release);
        atomic_store_explicit(&atomic_state.brake_switch, l_brake_switch, memory_order_release);
        atomic_store_explicit(&atomic_state.steering_angle, l_steering_angle, memory_order_release);
        atomic_store_explicit(&atomic_state.engine_rpm, l_engine_rpm, memory_order_release);
        atomic_store_explicit(&atomic_state.vehicle_speed, l_vehicle_speed, memory_order_release);
        atomic_store_explicit(&atomic_state.engine_temp_c, l_engine_temp_c, memory_order_release);
        atomic_store_explicit(&atomic_state.infotainment_status, l_infotainment, memory_order_release);

        next_update = add_us(next_update, SIGNAL_UPDATE_US);
    }

    return NULL;
}

/* Individual ECU worker thread: executes independently with dedicated SocketCAN socket */
static void *ecu_worker_thread(void *arg)
{
    ThreadECUConfig *cfg = (ThreadECUConfig *)arg;

    /* Enforce real-time scheduling policy if configured */
    if (cfg->sched_policy == SCHED_FIFO) {
        struct sched_param sp;
        sp.sched_priority = cfg->rt_priority;
        (void)pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp);
    }

    /* Open an independent SocketCAN socket to model independent CAN hardware */
    int socket_fd = open_vcan_socket("vcan0");
    if (socket_fd < 0) {
        fprintf(stderr, "[ECU %s (0x%03X)] Failed to bind SocketCAN: %s\n",
                cfg->name, cfg->can_id, strerror(errno));
        return NULL;
    }

    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);

    long initial_delay = cfg->period_us + random_jitter_us();
    struct timespec next_send = add_us(now, initial_delay);

    struct can_frame frame;
    memset(&frame, 0, sizeof(frame));
    frame.can_id = cfg->can_id;
    frame.can_dlc = DLC;

    while (running) {
        while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_send, NULL) != 0) {
            if (!running) {
                break;
            }
        }
        if (!running) {
            break;
        }

        /* Read state atomically with acquire semantics */
        switch (cfg->can_id) {
            case 0x0A0:
                frame.data[0] = (uint8_t)atomic_load_explicit(&atomic_state.brake_pressure, memory_order_acquire);
                frame.data[1] = (uint8_t)atomic_load_explicit(&atomic_state.brake_switch, memory_order_acquire);
                break;

            case 0x0B0: {
                int16_t angle = (int16_t)atomic_load_explicit(&atomic_state.steering_angle, memory_order_acquire);
                uint16_t encoded = (uint16_t)angle;
                frame.data[0] = (uint8_t)(encoded >> 8);
                frame.data[1] = (uint8_t)(encoded & 0xFF);
                break;
            }

            case 0x100: {
                int rpm = atomic_load_explicit(&atomic_state.engine_rpm, memory_order_acquire);
                frame.data[0] = (uint8_t)((rpm >> 8) & 0xFF);
                frame.data[1] = (uint8_t)(rpm & 0xFF);
                break;
            }

            case 0x200:
                frame.data[0] = (uint8_t)atomic_load_explicit(&atomic_state.vehicle_speed, memory_order_acquire);
                break;

            case 0x300: {
                int temp = atomic_load_explicit(&atomic_state.engine_temp_c, memory_order_acquire);
                frame.data[0] = (uint8_t)(temp + 40);
                break;
            }

            case 0x600:
                frame.data[0] = (uint8_t)atomic_load_explicit(&atomic_state.infotainment_status, memory_order_acquire);
                break;

            default:
                break;
        }

        frame.data[7] = cfg->counter++;

        ssize_t bytes_sent = write(socket_fd, &frame, sizeof(frame));
        if (bytes_sent == (ssize_t)sizeof(frame)) {
            atomic_fetch_add_explicit(&atomic_total_frames, 1, memory_order_relaxed);
        }

        clock_gettime(CLOCK_MONOTONIC, &now);

        long interval = cfg->period_us + random_jitter_us();
        struct timespec next_deadline = add_us(next_send, interval);
        long max_slack = cfg->period_us * SCHEDULER_SLACK_PERIODS;

        while (timespec_diff_us(&now, &next_deadline) > max_slack) {
            next_deadline = add_us(next_deadline, interval);
        }

        next_send = next_deadline;
    }

    close(socket_fd);
    return NULL;
}

static int run_multithreaded(long duration_sec)
{
    pthread_t ecu_threads[ECU_COUNT];
    pthread_t physics_thread;
    struct timespec start_time;
    struct timespec now;
    struct timespec next_telemetry;

    /* Initialize atomic state */
    atomic_init(&atomic_state.brake_pressure, 0);
    atomic_init(&atomic_state.brake_switch, 0);
    atomic_init(&atomic_state.steering_angle, 0);
    atomic_init(&atomic_state.engine_rpm, 2300);
    atomic_init(&atomic_state.vehicle_speed, 60);
    atomic_init(&atomic_state.engine_temp_c, 90);
    atomic_init(&atomic_state.infotainment_status, 1);
    atomic_init(&atomic_total_frames, 0);

    clock_gettime(CLOCK_MONOTONIC, &start_time);
    next_telemetry = add_us(start_time, TELEMETRY_INTERVAL_US);

    printf("====================================================================\n");
    printf("CAN-Sentinel ECU Simulator (Multi-Threaded Architecture)\n");
    printf("====================================================================\n");
    printf("Concurrency: 6 Autonomous ECU POSIX Threads + 1 Physics Engine Thread\n");
    printf("CAN interface: vcan0 (Dedicated SocketCAN socket per ECU thread)\n");
    printf("Synchronization: C11 Lock-Free Atomics (<stdatomic.h> zero mutex contention)\n");
    printf("Real-Time Scheduling:\n");
    printf("  - 0x0A0 (Brake)      & 0x0B0 (Steering): SCHED_FIFO Priority 80 (ASIL-D)\n");
    printf("  - 0x100 (Engine RPM) & 0x200 (Speed):    SCHED_FIFO Priority 50 (ASIL-B)\n");
    printf("  - 0x300 (Temp)       & 0x600 (Info):     SCHED_OTHER (QM)\n");
    if (duration_sec > 0) {
        printf("Simulation duration: %ld seconds (auto-stop)\n", duration_sec);
    }
    printf("Press Ctrl+C to stop.\n");
    printf("====================================================================\n");
    fflush(stdout);

    /* Launch physics simulation worker thread */
    if (pthread_create(&physics_thread, NULL, physics_worker_thread, NULL) != 0) {
        perror("Failed to create physics thread");
        return EXIT_FAILURE;
    }

    /* Launch 6 independent ECU worker threads */
    for (int i = 0; i < ECU_COUNT; i++) {
        if (pthread_create(&ecu_threads[i], NULL, ecu_worker_thread, &thread_configs[i]) != 0) {
            fprintf(stderr, "Failed to create thread for ECU %s\n", thread_configs[i].name);
            running = 0;
            break;
        }
    }

    /* Main thread supervises execution, reports telemetry, and monitors duration */
    while (running) {
        clock_gettime(CLOCK_MONOTONIC, &now);

        if (duration_sec > 0 && (now.tv_sec - start_time.tv_sec) >= duration_sec) {
            printf("\n[DURATION] Reached configured duration of %ld seconds. Stopping...\n", duration_sec);
            running = 0;
            break;
        }

        if (timespec_diff_us(&now, &next_telemetry) >= 0) {
            long elapsed_sec = now.tv_sec - start_time.tv_sec;
            int minutes = (int)(elapsed_sec / 60);
            int seconds = (int)(elapsed_sec % 60);
            double elapsed_s = (double)(now.tv_sec - start_time.tv_sec)
                             + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
            unsigned long frames = atomic_load_explicit(&atomic_total_frames, memory_order_relaxed);
            double fps = (elapsed_s > 0.0) ? ((double)frames / elapsed_s) : 0.0;

            int b_switch = atomic_load_explicit(&atomic_state.brake_switch, memory_order_acquire);
            int b_press = atomic_load_explicit(&atomic_state.brake_pressure, memory_order_acquire);
            int spd = atomic_load_explicit(&atomic_state.vehicle_speed, memory_order_acquire);
            int rpm = atomic_load_explicit(&atomic_state.engine_rpm, memory_order_acquire);
            int steer = atomic_load_explicit(&atomic_state.steering_angle, memory_order_acquire);

            char brake_info[16];
            if (b_switch) {
                snprintf(brake_info, sizeof(brake_info), "ON (%d%%)", b_press);
            } else {
                snprintf(brake_info, sizeof(brake_info), "OFF");
            }

            printf("[TELEMETRY-MT] [%02d:%02d] Frames: %7lu | Rate: %5.1f fps | Speed: %3d km/h | RPM: %4d | Steer: %+5.1f deg | Brake: %s\n",
                   minutes, seconds, frames, fps, spd, rpm, (double)steer / 10.0, brake_info);
            fflush(stdout);

            next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            while (timespec_diff_us(&now, &next_telemetry) >= 0) {
                next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            }
        }

        /* Sleep 50 ms before next supervisor loop iteration */
        struct timespec tick = {0, 50000000L};
        nanosleep(&tick, NULL);
    }

    printf("\nShutting down multi-threaded ECU nodes cleanly...\n");

    /* Join all threads to ensure 100% clean resource deallocation */
    for (int i = 0; i < ECU_COUNT; i++) {
        pthread_join(ecu_threads[i], NULL);
    }
    pthread_join(physics_thread, NULL);

    clock_gettime(CLOCK_MONOTONIC, &now);
    unsigned long final_frames = atomic_load_explicit(&atomic_total_frames, memory_order_relaxed);
    double total_duration_s = (double)(now.tv_sec - start_time.tv_sec)
                            + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
    double avg_fps = (total_duration_s > 0.0) ? ((double)final_frames / total_duration_s) : 0.0;

    printf("CAN-Sentinel Multi-Threaded ECU Simulator stopped.\n");
    printf("Execution summary: %lu frames transmitted in %.2f seconds (average rate: %.2f fps).\n",
           final_frames, total_duration_s, avg_fps);

    return EXIT_SUCCESS;
}

static void print_usage(const char *prog_name)
{
    printf("CAN-Sentinel ECU Simulator\n");
    printf("Usage: %s [OPTIONS] [seed]\n\n", prog_name);
    printf("Options:\n");
    printf("  --threads, -t        Enable distributed multi-threaded architecture (6 pthreads + atomics)\n");
    printf("  --duration, -d <sec> Auto-stop simulation after specified duration in seconds\n");
    printf("  --help, -h           Show this help message\n\n");
    printf("Positional:\n");
    printf("  [seed]               Optional unsigned 32-bit integer for deterministic PRNG\n");
}

int main(int argc, char *argv[])
{
    unsigned int seed = 0;
    bool seed_provided = false;
    bool multithreaded_mode = false;
    long duration_sec = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--threads") == 0 || strcmp(argv[i], "-t") == 0) {
            multithreaded_mode = true;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            print_usage(argv[0]);
            return EXIT_SUCCESS;
        } else if (strcmp(argv[i], "--duration") == 0 || strcmp(argv[i], "-d") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: --duration requires an integer argument in seconds\n");
                return EXIT_FAILURE;
            }
            i++;
            char *endptr = NULL;
            long val = strtol(argv[i], &endptr, 10);
            if (*endptr != '\0' || val <= 0) {
                fprintf(stderr, "Error: invalid duration '%s'\n", argv[i]);
                return EXIT_FAILURE;
            }
            duration_sec = val;
        } else {
            /* Try parsing as seed */
            char *endptr = NULL;
            errno = 0;
            unsigned long parsed = strtoul(argv[i], &endptr, 10);
            if (errno != 0 || endptr == argv[i] || *endptr != '\0' || parsed > UINT32_MAX) {
                fprintf(stderr, "Unknown or invalid option: %s\n", argv[i]);
                print_usage(argv[0]);
                return EXIT_FAILURE;
            }
            seed = (unsigned int)parsed;
            seed_provided = true;
        }
    }

    if (!seed_provided) {
        seed = (unsigned int)time(NULL);
    }

    srand(seed);
    printf("Random seed: %u\n", seed);

    (void)nice(-10);

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    if (multithreaded_mode) {
        return run_multithreaded(duration_sec);
    } else {
        return run_singlethreaded(duration_sec);
    }
}

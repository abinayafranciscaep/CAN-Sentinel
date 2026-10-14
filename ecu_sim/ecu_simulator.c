#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <signal.h>
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

typedef struct {
    canid_t can_id;
    long period_us;
    struct timespec next_send;
    uint8_t counter;
} ECU;

static volatile sig_atomic_t running = 1;

static ECU ecus[ECU_COUNT] = {
    {0x0A0,  20000, {0, 0}, 0},  /* Brake: 20 ms */
    {0x0B0,  10000, {0, 0}, 0},  /* Steering: 10 ms */
    {0x100,  10000, {0, 0}, 0},  /* Engine RPM: 10 ms */
    {0x200,  20000, {0, 0}, 0},  /* Vehicle speed: 20 ms */
    {0x300, 100000, {0, 0}, 0},  /* Temperature: 100 ms */
    {0x600, 100000, {0, 0}, 0}   /* Infotainment: 100 ms */
};

static int brake_pressure = 0;
static int brake_switch = 0;
static int steering_angle = 0;
static int engine_rpm = 1500;
static int vehicle_speed = 60;
static int engine_temp_c = 90;
static uint8_t infotainment_status = 1;

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

/* Update only the signal associated with the transmitting ECU. */
static void update_signals(canid_t can_id)
{
    switch (can_id) {
        case 0x0A0:
            /* Brake pressure: 0-100; switch: 0 or 1 */
            if (rand() % 100 < 8) {
                brake_switch = !brake_switch;
            }

            if (brake_switch) {
                brake_pressure += 5 + rand() % 11;
            } else {
                brake_pressure -= 2 + rand() % 9;
            }

            brake_pressure = clamp_int(brake_pressure, 0, 100);
            break;

        case 0x0B0:
            /* Signed steering angle in 0.1-degree units */
            steering_angle += (rand() % 21) - 10;
            steering_angle = clamp_int(steering_angle, -450, 450);
            break;

        case 0x100:
            /* Engine RPM */
            engine_rpm += (rand() % 101) - 50;
            engine_rpm = clamp_int(engine_rpm, 800, 4000);
            break;

        case 0x200:
            /* Vehicle speed in km/h */
            vehicle_speed += (rand() % 5) - 2;
            vehicle_speed = clamp_int(vehicle_speed, 0, 130);
            break;

        case 0x300:
            /* Coolant temperature in degrees Celsius */
            engine_temp_c += (rand() % 3) - 1;
            engine_temp_c = clamp_int(engine_temp_c, 80, 105);
            break;

        case 0x600:
            /* Infotainment status */
            if (rand() % 1000 == 0) {
                infotainment_status = (uint8_t)(rand() % 2);
            }
            break;

        default:
            break;
    }
}

static void prepare_frame(const ECU *ecu, struct can_frame *frame)
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
            /* Temperature encoding uses the agreed +40 offset. */
            frame->data[0] = (uint8_t)(engine_temp_c + 40);
            break;

        case 0x600:
            frame->data[0] = infotainment_status;
            break;

        default:
            break;
    }

    /* Independent rolling counter for each ECU. */
    frame->data[7] = ecu->counter;
}

static int send_frame(int socket_fd, ECU *ecu)
{
    struct can_frame frame;

    prepare_frame(ecu, &frame);

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

int main(void)
{
    int socket_fd;
    struct ifreq interface_request;
    struct sockaddr_can address;
    struct timespec now;

    srand((unsigned int)time(NULL));

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    socket_fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);

    if (socket_fd < 0) {
        perror("Failed to create CAN socket");
        return EXIT_FAILURE;
    }

    memset(&interface_request, 0, sizeof(interface_request));

    strncpy(interface_request.ifr_name, "vcan0",
            sizeof(interface_request.ifr_name) - 1);

    if (ioctl(socket_fd, SIOCGIFINDEX, &interface_request) < 0) {
        perror("Failed to obtain vcan0 interface index");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    memset(&address, 0, sizeof(address));

    address.can_family = AF_CAN;
    address.can_ifindex = interface_request.ifr_ifindex;

    if (bind(socket_fd, (struct sockaddr *)&address,
             sizeof(address)) < 0) {
        perror("Failed to bind CAN socket to vcan0");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
        perror("Failed to read monotonic clock");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    /* Schedule the first frame after its nominal period plus jitter. */
    for (int i = 0; i < ECU_COUNT; i++) {
        long initial_delay = ecus[i].period_us + random_jitter_us();
        ecus[i].next_send = add_us(now, initial_delay);
    }

    printf("CAN-Sentinel ECU Simulator Started\n");
    printf("CAN interface: vcan0\n");
    printf("Protocol: six periodic ECU frames, DLC 8\n");
    printf("Signal simulation: enabled\n");
    printf("Timing jitter: approximately +/-1 ms\n");
    printf("Press Ctrl+C to stop.\n");
    fflush(stdout);

    while (running) {
        if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
            perror("Failed to read monotonic clock");
            break;
        }

        for (int i = 0; i < ECU_COUNT && running; i++) {
            if (timespec_diff_us(&now, &ecus[i].next_send) >= 0) {

                /* Update only this ECU's signal before transmission. */
                update_signals(ecus[i].can_id);

                if (send_frame(socket_fd, &ecus[i]) < 0) {
                    running = 0;
                    break;
                }

                if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
                    perror("Failed to read monotonic clock");
                    running = 0;
                    break;
                }

                long interval = ecus[i].period_us + random_jitter_us();
                struct timespec next_deadline =
                    add_us(ecus[i].next_send, interval);

                /* Skip missed deadlines instead of accumulating drift
                   or sending bursts of catch-up frames. */
                while (timespec_diff_us(&now, &next_deadline) >= 0) {
                    next_deadline = add_us(next_deadline, interval);
                }

                ecus[i].next_send = next_deadline;
            }
        }

        if (running) {
            struct timespec earliest = ecus[0].next_send;

            for (int i = 1; i < ECU_COUNT; i++) {
                if (timespec_diff_us(&ecus[i].next_send,
                                     &earliest) < 0) {
                    earliest = ecus[i].next_send;
                }
            }

            if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
                perror("Failed to read monotonic clock");
                break;
            }

            long wait_us = timespec_diff_us(&earliest, &now);

            if (wait_us > 0) {
                struct timespec delay = {
                    .tv_sec = wait_us / 1000000L,
                    .tv_nsec = (wait_us % 1000000L) * 1000L
                };

                while (nanosleep(&delay, &delay) < 0
                       && errno == EINTR && running) {
                    /* Resume sleep after an interrupt. */
                }
            }
        }
    }

    close(socket_fd);

    printf("\nCAN-Sentinel ECU Simulator stopped.\n");

    return EXIT_SUCCESS;
}

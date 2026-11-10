#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L
#define _GNU_SOURCE

#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define BRAKE_CAN_ID        0x0A0
#define DEFAULT_IFACE       "vcan1"
#define DEFAULT_TIMEOUT_MS  100
#define NOMINAL_PERIOD_MS   20

/* ANSI Color Escape Codes */
#define ANSI_RESET      "\033[0m"
#define ANSI_BOLD       "\033[1m"
#define ANSI_CYAN       "\033[1;36m"
#define ANSI_GREEN      "\033[1;32m"
#define ANSI_YELLOW     "\033[1;33m"
#define ANSI_RED        "\033[1;31m"
#define ANSI_WHITE      "\033[1;37m"
#define ANSI_GRAY       "\033[0;90m"

#define ANSI_BG_RED     "\033[41;1;97m"
#define ANSI_BG_GREEN   "\033[30;102;1m"
#define ANSI_BG_YELLOW  "\033[30;103;1m"

typedef enum {
    STATE_STANDBY,          /* Waiting for initial frame */
    STATE_OPERATIONAL,      /* Frames arriving within timeout */
    STATE_SAFE_STATE        /* Timeout exceeded (>100ms) - Fail-Safe Default */
} ReceiverState;

static volatile sig_atomic_t running = 1;

static void handle_signal(int sig)
{
    (void)sig;
    running = 0;
}

static double timespec_diff_ms(const struct timespec *end, const struct timespec *start)
{
    return (double)(end->tv_sec - start->tv_sec) * 1000.0
         + (double)(end->tv_nsec - start->tv_nsec) / 1e6;
}

static void print_usage(const char *prog_name)
{
    printf("CAN-Sentinel Brake Actuator Receiver (ISO 26262 Safe-State Demo)\n");
    printf("Usage: %s [OPTIONS] [interface]\n\n", prog_name);
    printf("Options:\n");
    printf("  -i, --interface <name>  CAN interface to listen on (default: vcan1)\n");
    printf("  -t, --timeout <ms>      Loss-of-Signal timeout in ms (default: 100)\n");
    printf("  -p, --plain             Plain scrolling output (default: ANSI cluster)\n");
    printf("  -h, --help              Show this help message\n\n");
    printf("Positional:\n");
    printf("  [interface]             Optional interface name shortcut (e.g. vcan0, vcan1)\n");
}

int main(int argc, char *argv[])
{
    char ifname[IFNAMSIZ] = DEFAULT_IFACE;
    int timeout_ms = DEFAULT_TIMEOUT_MS;
    bool plain_mode = false;

    if (!isatty(STDOUT_FILENO)) {
        plain_mode = true;
    }

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-i") == 0 || strcmp(argv[i], "--interface") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: %s requires an interface name argument\n", argv[i]);
                return EXIT_FAILURE;
            }
            snprintf(ifname, sizeof(ifname), "%s", argv[++i]);
        } else if (strcmp(argv[i], "-t") == 0 || strcmp(argv[i], "--timeout") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: %s requires a timeout in milliseconds\n", argv[i]);
                return EXIT_FAILURE;
            }
            timeout_ms = atoi(argv[++i]);
            if (timeout_ms <= 0) timeout_ms = DEFAULT_TIMEOUT_MS;
        } else if (strcmp(argv[i], "-p") == 0 || strcmp(argv[i], "--plain") == 0) {
            plain_mode = true;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            print_usage(argv[0]);
            return EXIT_SUCCESS;
        } else if (argv[i][0] != '-') {
            snprintf(ifname, sizeof(ifname), "%s", argv[i]);
        } else {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
            print_usage(argv[0]);
            return EXIT_FAILURE;
        }
    }

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    int sock = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (sock < 0) {
        perror("Failed to create SocketCAN socket");
        return EXIT_FAILURE;
    }

    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", ifname);
    if (ioctl(sock, SIOCGIFINDEX, &ifr) < 0) {
        fprintf(stderr, "Error: interface '%s' not found: %s\n", ifname, strerror(errno));
        close(sock);
        return EXIT_FAILURE;
    }

    struct sockaddr_can addr;
    memset(&addr, 0, sizeof(addr));
    addr.can_family = AF_CAN;
    addr.can_ifindex = ifr.ifr_ifindex;

    /* Filter exclusively for Brake ECU (0x0A0) */
    struct can_filter rfilter;
    rfilter.can_id = BRAKE_CAN_ID;
    rfilter.can_mask = CAN_SFF_MASK;
    if (setsockopt(sock, SOL_CAN_RAW, CAN_RAW_FILTER, &rfilter, sizeof(rfilter)) < 0) {
        perror("Failed to set SocketCAN filter for 0x0A0");
        close(sock);
        return EXIT_FAILURE;
    }

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        fprintf(stderr, "Failed to bind to %s: %s\n", ifname, strerror(errno));
        close(sock);
        return EXIT_FAILURE;
    }

    if (!plain_mode) {
        printf("\033[2J\033[?25l"); /* Clear screen and hide cursor */
        fflush(stdout);
    } else {
        printf("CAN-Sentinel Brake Receiver active on %s (Timeout: %d ms, Filter: 0x%03X)\n",
               ifname, timeout_ms, BRAKE_CAN_ID);
        fflush(stdout);
    }

    ReceiverState state = STATE_STANDBY;
    struct timespec last_recv_time = {0, 0};
    struct timespec now;
    unsigned long frames_received = 0;
    unsigned long safe_state_transitions = 0;
    uint8_t last_counter = 0;
    int brake_pressure = 0;
    int brake_switch = 0;
    double delta_ms = 0.0;
    double elapsed_since_last_ms = 0.0;

    struct pollfd pfd;
    pfd.fd = sock;
    pfd.events = POLLIN;

    while (running) {
        clock_gettime(CLOCK_MONOTONIC, &now);

        /* Poll with 10 ms resolution to promptly catch the 100 ms threshold */
        int poll_ret = poll(&pfd, 1, 10);

        if (poll_ret > 0 && (pfd.revents & POLLIN)) {
            struct can_frame frame;
            ssize_t nbytes = read(sock, &frame, sizeof(frame));
            if (nbytes == sizeof(frame)) {
                clock_gettime(CLOCK_MONOTONIC, &now);
                if (frames_received > 0) {
                    delta_ms = timespec_diff_ms(&now, &last_recv_time);
                } else {
                    delta_ms = (double)NOMINAL_PERIOD_MS;
                }
                last_recv_time = now;
                frames_received++;

                brake_pressure = frame.data[0];
                brake_switch = frame.data[1];
                last_counter = frame.data[7];

                if (state == STATE_SAFE_STATE || state == STATE_STANDBY) {
                    state = STATE_OPERATIONAL;
                }
            }
        }

        /* Check Loss-of-Signal condition */
        clock_gettime(CLOCK_MONOTONIC, &now);
        if (state == STATE_OPERATIONAL) {
            elapsed_since_last_ms = timespec_diff_ms(&now, &last_recv_time);
            if (elapsed_since_last_ms > (double)timeout_ms) {
                state = STATE_SAFE_STATE;
                safe_state_transitions++;
            }
        } else if (state == STATE_SAFE_STATE) {
            elapsed_since_last_ms = timespec_diff_ms(&now, &last_recv_time);
        }

        /* Display Rendering */
        if (!plain_mode) {
            printf("\033[H");
            printf("%s╭──────────────────────────────────────────────────────────────────────────────╮%s\033[K\n", ANSI_CYAN, ANSI_RESET);
            printf("%s│%s  %s► CAN-SENTINEL BRAKE ACTUATOR (SAFETY DOMAIN)%s\033[K\033[80G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
            printf("%s├──────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);
            printf("%s│%s  Interface: %s%-6s%s  │  Target ID: %s0x0A0%s  │  Timeout Threshold: %s%3d ms%s\033[K\033[80G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ifname, ANSI_RESET, ANSI_WHITE, ANSI_RESET,
                   ANSI_YELLOW, timeout_ms, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
            printf("%s├──────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

            /* System Status Banner */
            if (state == STATE_STANDBY) {
                printf("%s│%s  ACTUATOR STATE : %s  [ STANDBY: WAITING FOR BUS TRAFFIC ]  %s\033[K\033[80G%s│%s\n",
                       ANSI_CYAN, ANSI_RESET, ANSI_BG_YELLOW, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
                printf("%s│%s  HEALTH STATUS  : %sLISTENING ON %s%s\033[K\033[80G%s│%s\n",
                       ANSI_CYAN, ANSI_RESET, ANSI_GRAY, ifname, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
            } else if (state == STATE_OPERATIONAL) {
                printf("%s│%s  ACTUATOR STATE : %s  [ NORMAL OPERATION: BRAKE SYSTEM ONLINE ]  %s\033[K\033[80G%s│%s\n",
                       ANSI_CYAN, ANSI_RESET, ANSI_BG_GREEN, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
                printf("%s│%s  HEALTH STATUS  : %s● RECEPTION NOMINAL%s (Heartbeat: %4.1f ms / %3.0f%% timeout)\033[K\033[80G%s│%s\n",
                       ANSI_CYAN, ANSI_RESET, ANSI_GREEN, ANSI_RESET, delta_ms, (delta_ms / timeout_ms) * 100.0, ANSI_CYAN, ANSI_RESET);
            } else {
                printf("%s│%s  ACTUATOR STATE : %s  [ 🚨 SAFE STATE ACTIVATED: FAIL-SAFE DEFAULT ENGAGED ]  %s\033[K\033[80G%s│%s\n",
                       ANSI_CYAN, ANSI_RESET, ANSI_BG_RED, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
                printf("%s│%s  HEALTH STATUS  : %s⚠️ LOSS OF SIGNAL (%4.0f ms > %d ms)! Gateway Block Active!%s\033[K\033[80G%s│%s\n",
                       ANSI_CYAN, ANSI_RESET, ANSI_RED, elapsed_since_last_ms, timeout_ms, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
            }

            printf("%s├──────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

            /* Brake Telemetry Visuals */
            int bar_width = 24;
            int fill = (brake_pressure * bar_width) / 100;
            if (fill > bar_width) fill = bar_width;
            char bar[256];
            int pos = snprintf(bar, sizeof(bar), "[");
            for (int b = 0; b < bar_width; b++) {
                if (b < fill) {
                    pos += snprintf(bar + pos, sizeof(bar) - pos, "█");
                } else {
                    pos += snprintf(bar + pos, sizeof(bar) - pos, "░");
                }
            }
            snprintf(bar + pos, sizeof(bar) - pos, "]");

            const char *press_color = (brake_pressure > 50) ? ANSI_RED : ((brake_pressure > 0) ? ANSI_YELLOW : ANSI_GREEN);
            const char *switch_badge = brake_switch ? ANSI_BG_RED " ON (ENGAGED) " ANSI_RESET : ANSI_GRAY " OFF (RELEASED) " ANSI_RESET;

            printf("%s│%s  Brake Pressure : %s%s%s %s%3d%%%s\033[K\033[80G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, press_color, bar, ANSI_RESET, press_color, brake_pressure, ANSI_RESET, ANSI_CYAN, ANSI_RESET);
            printf("%s│%s  Pedal Switch   : %s\033[K\033[80G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, switch_badge, ANSI_CYAN, ANSI_RESET);
            printf("%s│%s  Rolling Counter: %s%3u%s (Byte 7 progression)\033[K\033[80G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, ANSI_WHITE, last_counter, ANSI_RESET, ANSI_CYAN, ANSI_RESET);

            printf("%s├──────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);
            printf("%s│%s  Statistics     : Total Frames: %s%-7lu%s │ Safe State Triggers: %s%-3lu%s\033[K\033[80G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, ANSI_GREEN, frames_received, ANSI_RESET,
                   (safe_state_transitions > 0 ? ANSI_RED : ANSI_WHITE), safe_state_transitions, ANSI_RESET,
                   ANSI_CYAN, ANSI_RESET);
            printf("%s╰──────────────────────────────────────────────────────────────────────────────╯%s\033[K\n", ANSI_CYAN, ANSI_RESET);
            fflush(stdout);
        } else {
            /* Plain scrolling text output */
            static struct timespec last_plain_print = {0, 0};
            if (timespec_diff_ms(&now, &last_plain_print) >= 200.0) {
                last_plain_print = now;
                if (state == STATE_OPERATIONAL) {
                    printf("[%s] [OPERATIONAL] Frames: %6lu | Brake: %3d%% (Switch: %s) | Counter: %3u | Δt: %4.1f ms\n",
                           ifname, frames_received, brake_pressure, (brake_switch ? "ON " : "OFF"), last_counter, delta_ms);
                } else if (state == STATE_SAFE_STATE) {
                    printf("[%s] [🚨 SAFE STATE] Loss of 0x0A0 for %4.0f ms! Fail-Safe Default Engaged!\n",
                           ifname, elapsed_since_last_ms);
                } else {
                    printf("[%s] [STANDBY] Waiting for 0x0A0 frames...\n", ifname);
                }
                fflush(stdout);
            }
        }

        /* 20 Hz loop sleep */
        usleep(50000);
    }

    if (!plain_mode) {
        printf("\033[?25h\n"); /* Restore cursor */
    }

    printf("\nBrake Actuator Receiver stopped. Frames received: %lu, Safe State triggers: %lu\n",
           frames_received, safe_state_transitions);

    close(sock);
    return EXIT_SUCCESS;
}

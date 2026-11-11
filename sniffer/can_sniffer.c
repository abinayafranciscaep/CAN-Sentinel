#define _DEFAULT_SOURCE
#include "socket_bridge.h"

#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested = 0;

static void handle_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static int create_can_socket(const char *interface_name)
{
    int fd;
    struct ifreq ifr;
    struct sockaddr_can address;

    fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (fd < 0) {
        perror("CAN socket");
        return -1;
    }

    memset(&ifr, 0, sizeof(ifr));
    (void)snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s", interface_name);

    if (ioctl(fd, SIOCGIFINDEX, &ifr) < 0) {
        perror("ioctl(SIOCGIFINDEX)");
        close(fd);
        return -1;
    }

    memset(&address, 0, sizeof(address));
    address.can_family = AF_CAN;
    address.can_ifindex = ifr.ifr_ifindex;

    if (bind(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("CAN bind");
        close(fd);
        return -1;
    }
    return fd;
}

int main(int argc, char *argv[])
{
    const char *interface_name = "vcan0";
    const char *socket_path = SOCKET_BRIDGE_DEFAULT_PATH;
    int socket_enabled = 0;
    int can_fd = -1;
    int exit_status = EXIT_FAILURE;
    struct socket_bridge bridge;
    struct sigaction action;

    memset(&bridge, 0, sizeof(bridge));
    bridge.server_fd = -1;
    bridge.client_fd = -1;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--socket") == 0) {
            socket_enabled = 1;
        } else if (strcmp(argv[i], "--socket-path") == 0) {
            if (i + 1 >= argc || argv[i + 1][0] == '\0') {
                fprintf(stderr, "--socket-path requires a path.\n");
                return EXIT_FAILURE;
            }
            socket_path = argv[++i];
            socket_enabled = 1;
        } else if (strcmp(argv[i], "--help") == 0) {
            printf("Usage: %s [interface] [--socket] [--socket-path PATH]\n",
                   argv[0]);
            return EXIT_SUCCESS;
        } else if (argv[i][0] == '-') {
            fprintf(stderr, "Unknown option: %s\n", argv[i]);
            return EXIT_FAILURE;
        } else if (strcmp(interface_name, "vcan0") == 0) {
            interface_name = argv[i];
        } else {
            fprintf(stderr, "Unexpected argument: %s\n", argv[i]);
            return EXIT_FAILURE;
        }
    }

    if (strlen(interface_name) >= IFNAMSIZ) {
        fprintf(stderr, "Invalid interface name.\n");
        return EXIT_FAILURE;
    }

    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) < 0 ||
        sigaction(SIGTERM, &action, NULL) < 0) {
        perror("sigaction");
        return EXIT_FAILURE;
    }
    if (signal(SIGPIPE, SIG_IGN) == SIG_ERR) {
        perror("signal");
        return EXIT_FAILURE;
    }

    can_fd = create_can_socket(interface_name);
    if (can_fd < 0) {
        goto cleanup;
    }

    if (socket_enabled && socket_bridge_init(&bridge, socket_path) < 0) {
        goto cleanup;
    }

    printf("CAN interface: %s\n", interface_name);
    if (socket_enabled) {
        puts("Socket forwarding enabled.");
    }
    puts("Press Ctrl+C to stop.");
    fflush(stdout);

    while (!stop_requested) {
        struct pollfd fds[1 + SOCKET_BRIDGE_POLLFD_CAPACITY];
        size_t bridge_count = 0U;
        nfds_t count;
        int ready;

        fds[0].fd = can_fd;
        fds[0].events = POLLIN;
        fds[0].revents = 0;

        if (socket_enabled) {
            bridge_count = socket_bridge_pollfds(&bridge, &fds[1]);
        }
        count = (nfds_t)(1U + bridge_count);
        ready = poll(fds, count, -1);

        if (ready < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("poll");
            goto cleanup;
        }

        if (socket_enabled) {
            socket_bridge_handle_poll(&bridge, &fds[1], bridge_count);
        }

        if ((fds[0].revents & POLLIN) != 0) {
            struct can_frame frame;
            struct timespec timestamp;
            ssize_t bytes_read = read(can_fd, &frame, sizeof(frame));

            if (bytes_read < 0) {
                if (errno == EINTR) {
                    continue;
                }
                perror("CAN read");
                goto cleanup;
            }
            if ((size_t)bytes_read != sizeof(frame)) {
                fprintf(stderr, "Incomplete CAN frame; skipping.\n");
                continue;
            }

            if ((frame.can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG)) != 0) {
                continue;
            }
            if (frame.can_dlc > CAN_MAX_DLEN) {
                fprintf(stderr, "Invalid CAN DLC; skipping frame.\n");
                continue;
            }
            if (clock_gettime(CLOCK_REALTIME, &timestamp) < 0) {
                perror("clock_gettime");
                goto cleanup;
            }

            printf("CAN ID: 0x%03X  DLC: %u  DATA:",
                   frame.can_id & CAN_SFF_MASK, frame.can_dlc);
            for (unsigned int i = 0U; i < frame.can_dlc; i++) {
                printf(" %02X", frame.data[i]);
            }
            putchar('\n');
            fflush(stdout);

            if (socket_enabled &&
                socket_bridge_queue_frame(&bridge, &frame, &timestamp) < 0) {
                perror("Queue CAN frame for ML client");
                goto cleanup;
            }
        }
    }

    exit_status = EXIT_SUCCESS;

cleanup:
    if (socket_enabled) {
        socket_bridge_cleanup(&bridge);
    }
    if (can_fd >= 0) {
        close(can_fd);
    }
    return exit_status;
}

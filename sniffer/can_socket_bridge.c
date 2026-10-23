#define _DEFAULT_SOURCE

#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_SOCKET_PATH "/tmp/can_sentinel.sock"
#define OUTPUT_QUEUE_CAPACITY (64U * 1024U)

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
    snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s",
             interface_name);

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
    const char *socket_path = DEFAULT_SOCKET_PATH;
    int can_fd = -1;
    int server_fd = -1;
    int client_fd = -1;
    char output_queue[OUTPUT_QUEUE_CAPACITY];
    size_t queue_head = 0;
    size_t queue_length = 0;
    int exit_status = EXIT_FAILURE;
    int socket_bound = 0;
    struct sockaddr_un address;
    struct sigaction action;

    if (argc > 3) {
        fprintf(stderr, "Usage: %s [interface] [socket_path]\n",
                argv[0]);
        return EXIT_FAILURE;
    }

    if (argc >= 2) {
        interface_name = argv[1];
    }

    if (argc == 3) {
        socket_path = argv[2];
    }

    if (interface_name[0] == '\0' ||
        strlen(interface_name) >= IFNAMSIZ ||
        socket_path[0] == '\0' ||
        strlen(socket_path) >= sizeof(address.sun_path)) {
        fprintf(stderr, "Invalid interface name or socket path.\n");
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

    server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("Unix socket");
        goto cleanup;
    }

    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, socket_path, strlen(socket_path) + 1);

    if (bind(server_fd, (struct sockaddr *)&address,
             sizeof(address)) < 0) {
        perror("Unix socket bind (check whether the path is already in use)");
        goto cleanup;
    }
    socket_bound = 1;

    if (listen(server_fd, 1) < 0) {
        perror("listen");
        goto cleanup;
    }

    printf("CAN interface: %s\n", interface_name);
    printf("Unix socket: %s\n", socket_path);
    printf("Waiting for the ML client. Press Ctrl+C to stop.\n");
    fflush(stdout);

    while (!stop_requested) {
        fd_set read_fds;
        fd_set write_fds;
        int max_fd;
        int ready;

        FD_ZERO(&read_fds);
        FD_ZERO(&write_fds);
        FD_SET(server_fd, &read_fds);
        FD_SET(can_fd, &read_fds);
        max_fd = server_fd > can_fd ? server_fd : can_fd;

        if (client_fd >= 0) {
            FD_SET(client_fd, &read_fds);
            if (queue_length > 0) {
                FD_SET(client_fd, &write_fds);
            }
            if (client_fd > max_fd) {
                max_fd = client_fd;
            }
        }

        ready = select(max_fd + 1, &read_fds, &write_fds, NULL, NULL);

        if (ready < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("select");
            goto cleanup;
        }

        if (client_fd >= 0 && FD_ISSET(client_fd, &write_fds) &&
            queue_length > 0) {
            size_t contiguous = OUTPUT_QUEUE_CAPACITY - queue_head;
            ssize_t sent;

            if (contiguous > queue_length) {
                contiguous = queue_length;
            }

            sent = send(client_fd, output_queue + queue_head, contiguous,
                        MSG_NOSIGNAL | MSG_DONTWAIT);
            if (sent > 0) {
                size_t sent_size = (size_t)sent;
                queue_head = (queue_head + sent_size) % OUTPUT_QUEUE_CAPACITY;
                queue_length -= sent_size;
            } else if (sent < 0 &&
                       errno != EINTR &&
                       errno != EAGAIN &&
                       errno != EWOULDBLOCK) {
                perror("Sending to ML client");
                close(client_fd);
                client_fd = -1;
                queue_head = 0;
                queue_length = 0;
                puts("ML client connection lost; waiting for reconnect.");
                fflush(stdout);
                continue;
            } else if (sent == 0) {
                close(client_fd);
                client_fd = -1;
                queue_head = 0;
                queue_length = 0;
                puts("ML client connection lost; waiting for reconnect.");
                fflush(stdout);
                continue;
            }
        }

        if (client_fd >= 0 && FD_ISSET(client_fd, &read_fds)) {
            char probe;
            ssize_t n = recv(client_fd, &probe, 1, MSG_PEEK | MSG_DONTWAIT);

            if (n == 0 ||
                (n < 0 && errno != EINTR &&
                 errno != EAGAIN && errno != EWOULDBLOCK)) {
                close(client_fd);
                client_fd = -1;
                queue_head = 0;
                queue_length = 0;
                puts("ML client disconnected; waiting for reconnect.");
                fflush(stdout);
                continue;
            }

            if (n > 0) {
                close(client_fd);
                client_fd = -1;
                queue_head = 0;
                queue_length = 0;
                puts("ML client sent unexpected data; connection closed.");
                fflush(stdout);
                continue;
            }
        }

        if (FD_ISSET(server_fd, &read_fds)) {
            int new_client = accept(server_fd, NULL, NULL);

            if (new_client >= 0) {
                if (client_fd >= 0) {
                    close(client_fd);
                }
                client_fd = new_client;
                queue_head = 0;
                queue_length = 0;
                puts("ML client connected; forwarding live CAN frames.");
                fflush(stdout);
                continue;
            } else if (errno != EINTR) {
                perror("accept");
            }
        }

        if (FD_ISSET(can_fd, &read_fds)) {
            struct can_frame frame;
            struct timespec timestamp;
            char data_hex[CAN_MAX_DLEN * 2 + 1];
            char message[256];
            ssize_t bytes_read;
            int message_length;

            bytes_read = read(can_fd, &frame, sizeof(frame));

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

            if ((frame.can_id &
                 (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG)) != 0) {
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

            for (unsigned int i = 0; i < frame.can_dlc; i++) {
                snprintf(data_hex + (i * 2), sizeof(data_hex) - (i * 2),
                         "%02X", frame.data[i]);
            }
            data_hex[frame.can_dlc * 2] = '\0';

            message_length = snprintf(
                message, sizeof(message),
                "{\"timestamp\":%lld.%06ld,\"can_id\":\"0x%03X\","
                "\"dlc\":%u,\"data_hex\":\"%s\"}\n",
                (long long)timestamp.tv_sec,
                timestamp.tv_nsec / 1000,
                frame.can_id & CAN_SFF_MASK,
                (unsigned int)frame.can_dlc,
                data_hex
            );

            if (message_length < 0 ||
                (size_t)message_length >= sizeof(message)) {
                fprintf(stderr, "JSON message formatting failed.\n");
                goto cleanup;
            }

            if (client_fd >= 0) {
                size_t length = (size_t)message_length;
                size_t tail = (queue_head + queue_length) %
                              OUTPUT_QUEUE_CAPACITY;
                size_t first = OUTPUT_QUEUE_CAPACITY - tail;

                if (length > OUTPUT_QUEUE_CAPACITY - queue_length) {
                    close(client_fd);
                    client_fd = -1;
                    queue_head = 0;
                    queue_length = 0;
                    puts("ML client too slow; output queue full. "
                         "Disconnecting client.");
                    fflush(stdout);
                    continue;
                }

                if (first > length) {
                    first = length;
                }
                memcpy(output_queue + tail, message, first);
                if (length > first) {
                    memcpy(output_queue, message + first, length - first);
                }
                queue_length += length;
            }
        }
    }

    exit_status = EXIT_SUCCESS;

cleanup:
    if (client_fd >= 0) {
        close(client_fd);
    }
    if (server_fd >= 0) {
        close(server_fd);
    }
    if (socket_bound) {
        unlink(socket_path);
    }
    if (can_fd >= 0) {
        close(can_fd);
    }

    return exit_status;
}

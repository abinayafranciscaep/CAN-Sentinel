#define _DEFAULT_SOURCE
#include "socket_bridge.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/can.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#define OUTPUT_QUEUE_CAPACITY (64U * 1024U)
#define JSON_MESSAGE_CAPACITY 256U

static void disconnect_client(struct socket_bridge *bridge,
                              const char *reason)
{
    if (bridge->client_fd >= 0) {
        close(bridge->client_fd);
        bridge->client_fd = -1;
    }
    bridge->queue_head = 0;
    bridge->queue_length = 0;
    if (reason != NULL) {
        fprintf(stderr, "%s\n", reason);
    }
}

int socket_bridge_init(struct socket_bridge *bridge, const char *path)
{
    struct sockaddr_un address;
    struct stat info;
    int fd;

    if (bridge == NULL || path == NULL || path[0] == '\0' ||
        strlen(path) >= sizeof(bridge->socket_path)) {
        errno = EINVAL;
        return -1;
    }

    memset(bridge, 0, sizeof(*bridge));
    bridge->server_fd = -1;
    bridge->client_fd = -1;

    if (lstat(path, &info) == 0) {
        if (!S_ISSOCK(info.st_mode)) {
            fprintf(stderr, "Refusing to unlink non-socket path: %s\n", path);
            errno = EEXIST;
            return -1;
        }
        if (unlink(path) < 0) {
            perror("unlink stale socket");
            return -1;
        }
    } else if (errno != ENOENT) {
        perror("lstat socket path");
        return -1;
    }

    bridge->queue = malloc(OUTPUT_QUEUE_CAPACITY);
    if (bridge->queue == NULL) {
        perror("malloc output queue");
        return -1;
    }
    bridge->queue_capacity = OUTPUT_QUEUE_CAPACITY;
    memcpy(bridge->socket_path, path, strlen(path) + 1U);

    fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0);
    if (fd < 0) {
        perror("Unix socket");
        socket_bridge_cleanup(bridge);
        return -1;
    }

    memset(&address, 0, sizeof(address));
    address.sun_family = AF_UNIX;
    memcpy(address.sun_path, path, strlen(path) + 1U);

    if (bind(fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("Unix socket bind");
        close(fd);
        socket_bridge_cleanup(bridge);
        return -1;
    }
    bridge->socket_bound = 1;

    /* Restrict socket access to its owner and group. */
    if (chmod(path, S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP) < 0) {
        perror("chmod Unix socket");
        close(fd);
        socket_bridge_cleanup(bridge);
        return -1;
    }

    if (listen(fd, 4) < 0) {
        perror("listen");
        close(fd);
        bridge->server_fd = -1;
        socket_bridge_cleanup(bridge);
        return -1;
    }

    bridge->server_fd = fd;
    printf("Unix socket: %s\n", bridge->socket_path);
    return 0;
}

size_t socket_bridge_pollfds(struct socket_bridge *bridge,
                             struct pollfd fds[SOCKET_BRIDGE_POLLFD_CAPACITY])
{
    size_t count = 0U;

    if (bridge == NULL || fds == NULL) {
        return 0U;
    }

    if (bridge->server_fd >= 0) {
        fds[count].fd = bridge->server_fd;
        fds[count].events = POLLIN;
        fds[count].revents = 0;
        count++;
    }

    if (bridge->client_fd >= 0) {
        fds[count].fd = bridge->client_fd;
        fds[count].events = (short)(POLLIN |
            (bridge->queue_length > 0U ? POLLOUT : 0));
        fds[count].revents = 0;
        count++;
    }

    return count;
}

void socket_bridge_handle_poll(struct socket_bridge *bridge,
                               struct pollfd fds[SOCKET_BRIDGE_POLLFD_CAPACITY],
                               size_t count)
{
    for (size_t i = 0U; i < count; i++) {
        short events = fds[i].revents;

        if (fds[i].fd == bridge->server_fd && (events & POLLIN) != 0) {
            int client = accept(bridge->server_fd, NULL, NULL);
            if (client >= 0) {
                int flags = fcntl(client, F_GETFL, 0);
                if (flags >= 0) {
                    (void)fcntl(client, F_SETFL, flags | O_NONBLOCK);
                }
                (void)fcntl(client, F_SETFD, FD_CLOEXEC);
            }
            if (client >= 0) {
                disconnect_client(bridge, NULL);
                bridge->client_fd = client;
                puts("ML client connected; forwarding live CAN frames.");
                fflush(stdout);
            } else if (errno != EINTR && errno != EAGAIN &&
                       errno != EWOULDBLOCK) {
                perror("accept");
            }
            continue;
        }

        if (fds[i].fd != bridge->client_fd || bridge->client_fd < 0) {
            continue;
        }

        if ((events & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
            disconnect_client(bridge, "ML client disconnected; awaiting reconnect.");
            continue;
        }

        if ((events & POLLIN) != 0) {
            char probe;
            ssize_t received = recv(bridge->client_fd, &probe, 1,
                                    MSG_PEEK | MSG_DONTWAIT);
            if (received == 0) {
                disconnect_client(bridge, "ML client disconnected; awaiting reconnect.");
                continue;
            }
            if (received > 0) {
                disconnect_client(bridge, "ML client sent unexpected data; connection closed.");
                continue;
            }
            if (errno != EINTR && errno != EAGAIN &&
                errno != EWOULDBLOCK) {
                disconnect_client(bridge, "ML client connection lost.");
                continue;
            }
        }

        if ((events & POLLOUT) != 0 && bridge->queue_length > 0U) {
            size_t contiguous = bridge->queue_capacity - bridge->queue_head;
            ssize_t sent;

            if (contiguous > bridge->queue_length) {
                contiguous = bridge->queue_length;
            }

            sent = send(bridge->client_fd,
                        bridge->queue + bridge->queue_head,
                        contiguous, MSG_NOSIGNAL | MSG_DONTWAIT);
            if (sent > 0) {
                size_t sent_size = (size_t)sent;
                bridge->queue_head =
                    (bridge->queue_head + sent_size) % bridge->queue_capacity;
                bridge->queue_length -= sent_size;
            } else if (sent == 0 ||
                       (sent < 0 && errno != EINTR && errno != EAGAIN &&
                        errno != EWOULDBLOCK)) {
                disconnect_client(bridge, "ML client send failed; awaiting reconnect.");
            }
        }
    }
}

int socket_bridge_queue_frame(struct socket_bridge *bridge,
                              const struct can_frame *frame,
                              const struct timespec *timestamp)
{
    char data_hex[CAN_MAX_DLEN * 2U + 1U];
    char message[JSON_MESSAGE_CAPACITY];
    int message_length;
    size_t length;
    size_t tail;
    size_t first;

    if (bridge == NULL || frame == NULL || timestamp == NULL) {
        errno = EINVAL;
        return -1;
    }

    if (bridge->client_fd < 0) {
        return 0;
    }

    if ((frame->can_id & (CAN_EFF_FLAG | CAN_RTR_FLAG | CAN_ERR_FLAG)) != 0 ||
        frame->can_dlc > CAN_MAX_DLEN) {
        return 0;
    }

    for (unsigned int i = 0U; i < frame->can_dlc; i++) {
        (void)snprintf(data_hex + (i * 2U),
                       sizeof(data_hex) - (i * 2U),
                       "%02X", frame->data[i]);
    }
    data_hex[frame->can_dlc * 2U] = '\0';

    message_length = snprintf(
        message, sizeof(message),
        "{\"timestamp\":%lld.%06ld,\"can_id\":\"0x%03X\","
        "\"dlc\":%u,\"data_hex\":\"%s\"}\n",
        (long long)timestamp->tv_sec, timestamp->tv_nsec / 1000L,
        frame->can_id & CAN_SFF_MASK, (unsigned int)frame->can_dlc, data_hex);

    if (message_length < 0 || (size_t)message_length >= sizeof(message)) {
        errno = EOVERFLOW;
        return -1;
    }

    length = (size_t)message_length;
    if (length > bridge->queue_capacity - bridge->queue_length) {
        disconnect_client(bridge, "ML client too slow; output queue full. Disconnecting client.");
        return 0;
    }

    tail = (bridge->queue_head + bridge->queue_length) % bridge->queue_capacity;
    first = bridge->queue_capacity - tail;
    if (first > length) {
        first = length;
    }
    memcpy(bridge->queue + tail, message, first);
    if (length > first) {
        memcpy(bridge->queue, message + first, length - first);
    }
    bridge->queue_length += length;
    return 0;
}

void socket_bridge_cleanup(struct socket_bridge *bridge)
{
    if (bridge == NULL) {
        return;
    }

    disconnect_client(bridge, NULL);
    if (bridge->server_fd >= 0) {
        close(bridge->server_fd);
        bridge->server_fd = -1;
    }
    if (bridge->socket_bound != 0) {
        (void)unlink(bridge->socket_path);
        bridge->socket_bound = 0;
    }
    free(bridge->queue);
    bridge->queue = NULL;
    bridge->queue_capacity = 0U;
    bridge->queue_head = 0U;
    bridge->queue_length = 0U;
}

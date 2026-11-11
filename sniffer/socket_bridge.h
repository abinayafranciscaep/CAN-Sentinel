#ifndef CAN_SENTINEL_SOCKET_BRIDGE_H
#define CAN_SENTINEL_SOCKET_BRIDGE_H

#include <linux/can.h>
#include <poll.h>
#include <stddef.h>
#include <time.h>

#define SOCKET_BRIDGE_DEFAULT_PATH "/tmp/can_sentinel.sock"
#define SOCKET_BRIDGE_POLLFD_CAPACITY 2

struct socket_bridge {
    int server_fd;
    int client_fd;
    int socket_bound;
    char socket_path[108];
    char *queue;
    size_t queue_capacity;
    size_t queue_head;
    size_t queue_length;
};

int socket_bridge_init(struct socket_bridge *bridge, const char *path);
size_t socket_bridge_pollfds(struct socket_bridge *bridge,
                             struct pollfd fds[SOCKET_BRIDGE_POLLFD_CAPACITY]);
void socket_bridge_handle_poll(struct socket_bridge *bridge,
                               struct pollfd fds[SOCKET_BRIDGE_POLLFD_CAPACITY],
                               size_t count);
int socket_bridge_queue_frame(struct socket_bridge *bridge,
                              const struct can_frame *frame,
                              const struct timespec *timestamp);
void socket_bridge_cleanup(struct socket_bridge *bridge);

#endif

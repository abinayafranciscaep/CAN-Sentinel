#define _DEFAULT_SOURCE
#include <errno.h>
#include <linux/can.h>
#include <linux/can/raw.h>
#include <net/if.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>

int main(void)
{
    const char *interface_name = "vcan0";
    int socket_fd;
    struct ifreq ifr;
    struct sockaddr_can address;
    struct can_frame frame;

    socket_fd = socket(PF_CAN, SOCK_RAW, CAN_RAW);
    if (socket_fd < 0) {
        perror("socket");
        return EXIT_FAILURE;
    }

    memset(&ifr, 0, sizeof(ifr));
    snprintf(ifr.ifr_name, sizeof(ifr.ifr_name), "%s",
             interface_name);

    if (ioctl(socket_fd, SIOCGIFINDEX, &ifr) < 0) {
        perror("ioctl(SIOCGIFINDEX)");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    memset(&address, 0, sizeof(address));
    address.can_family = AF_CAN;
    address.can_ifindex = ifr.ifr_ifindex;

    if (bind(socket_fd, (struct sockaddr *)&address,
             sizeof(address)) < 0) {
        perror("bind");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    printf("CAN sniffer listening on %s. Press Ctrl+C to stop.\n",
           interface_name);
    fflush(stdout);

    for (;;) {
        ssize_t bytes_read = read(socket_fd, &frame, sizeof(frame));

        if (bytes_read < 0) {
            if (errno == EINTR) {
                continue;
            }
            perror("read");
            close(socket_fd);
            return EXIT_FAILURE;
        }

        if ((size_t)bytes_read != sizeof(frame)) {
            fprintf(stderr, "Incomplete CAN frame received.\n");
            continue;
        }

        printf("CAN ID: 0x%03X  DLC: %u  DATA:",
               frame.can_id & CAN_SFF_MASK,
               frame.can_dlc);

        for (unsigned int i = 0; i < frame.can_dlc; i++) {
            printf(" %02X", frame.data[i]);
        }

        putchar('\n');
        fflush(stdout);
    }

    close(socket_fd);
    return EXIT_SUCCESS;
}

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
#define DASHBOARD_REFRESH_US 100000L
#define SCHEDULER_SLACK_PERIODS 10

/* ANSI Color Escape Codes */
#define ANSI_RESET      "\033[0m"
#define ANSI_BOLD       "\033[1m"
#define ANSI_CYAN       "\033[1;36m"
#define ANSI_GREEN      "\033[1;32m"
#define ANSI_YELLOW     "\033[1;33m"
#define ANSI_BLUE       "\033[1;34m"
#define ANSI_MAGENTA    "\033[1;35m"
#define ANSI_RED        "\033[1;31m"
#define ANSI_WHITE      "\033[1;37m"
#define ANSI_GRAY       "\033[0;90m"

/* Inverted / Pill Badges for High-Contrast Alerts */
#define ANSI_BG_RED     "\033[41;1;97m"
#define ANSI_BG_YELLOW  "\033[30;103;1m"
#define ANSI_BG_GREEN   "\033[30;102;1m"
#define ANSI_BG_CYAN    "\033[30;106;1m"

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

/* Unified telemetry snapshot for rendering dashboard */
typedef struct {
    const char *arch_mode;
    const char *workers_desc;
    bool is_multithreaded;
    unsigned long total_frames;
    double fps;
    double elapsed_s;
    long duration_sec;
    int speed_kmh;
    int rpm;
    int steer_deci;
    int brake_switch;
    int brake_pressure;
    int engine_temp;
    int infotainment;
    unsigned long ecu_counts[ECU_COUNT];
} TelemetrySnapshot;

static volatile sig_atomic_t running = 1;
static bool use_dashboard = true;

#define TELEMETRY_HISTORY_LINES 10

typedef struct {
    int minutes;
    int seconds;
    unsigned long frames;
    double fps;
    int speed_kmh;
    int rpm;
    int steer_deci;
    int brake_switch;
    int brake_pressure;
    bool valid;
} TelemetryHistoryEntry;

static TelemetryHistoryEntry telemetry_history[TELEMETRY_HISTORY_LINES];
static int telemetry_history_count = 0;
static FILE *telemetry_log_file = NULL;

static void record_telemetry_snapshot(int min, int sec, unsigned long frames, double fps,
                                      int spd, int rpm, int steer, int b_switch, int b_press,
                                      bool is_mt)
{
    if (telemetry_log_file) {
        char brake_info[16];
        if (b_switch) {
            snprintf(brake_info, sizeof(brake_info), "ON (%d%%)", b_press);
        } else {
            snprintf(brake_info, sizeof(brake_info), "OFF");
        }
        fprintf(telemetry_log_file, "[TELEMETRY%s] [%02d:%02d] Frames: %7lu | Rate: %5.1f fps | Speed: %3d km/h | RPM: %4d | Steer: %+5.1f deg | Brake: %s\n",
                (is_mt ? "-MT" : ""), min, sec, frames, fps, spd, rpm, (double)steer / 10.0, brake_info);
        fflush(telemetry_log_file);
    }

    if (telemetry_history_count < TELEMETRY_HISTORY_LINES) {
        telemetry_history[telemetry_history_count].minutes = min;
        telemetry_history[telemetry_history_count].seconds = sec;
        telemetry_history[telemetry_history_count].frames = frames;
        telemetry_history[telemetry_history_count].fps = fps;
        telemetry_history[telemetry_history_count].speed_kmh = spd;
        telemetry_history[telemetry_history_count].rpm = rpm;
        telemetry_history[telemetry_history_count].steer_deci = steer;
        telemetry_history[telemetry_history_count].brake_switch = b_switch;
        telemetry_history[telemetry_history_count].brake_pressure = b_press;
        telemetry_history[telemetry_history_count].valid = true;
        telemetry_history_count++;
    } else {
        for (int i = 0; i < TELEMETRY_HISTORY_LINES - 1; i++) {
            telemetry_history[i] = telemetry_history[i + 1];
        }
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].minutes = min;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].seconds = sec;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].frames = frames;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].fps = fps;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].speed_kmh = spd;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].rpm = rpm;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].steer_deci = steer;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].brake_switch = b_switch;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].brake_pressure = b_press;
        telemetry_history[TELEMETRY_HISTORY_LINES - 1].valid = true;
    }
}

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
    {0, 0x0A0, "Brake Controller", 20000, 80, SCHED_FIFO,  0},  /* ASIL-D: Chassis Safety */
    {1, 0x0B0, "Steering Gateway", 10000, 80, SCHED_FIFO,  0},  /* ASIL-D: Chassis Safety */
    {2, 0x100, "Powertrain Engine",10000, 50, SCHED_FIFO,  0},  /* ASIL-B: Powertrain */
    {3, 0x200, "Speed Sensor",     20000, 50, SCHED_FIFO,  0},  /* ASIL-B: Powertrain */
    {4, 0x300, "Thermal Mgmt",    100000,  0, SCHED_OTHER, 0},  /* QM: Thermal Monitoring */
    {5, 0x600, "Infotainment Media",100000,0, SCHED_OTHER, 0}   /* QM: Comfort & Media */
};

/* Lock-free state for multi-threaded mode */
static LockFreeVehicleState atomic_state;
static atomic_ulong atomic_total_frames;
static atomic_ulong atomic_ecu_counts[ECU_COUNT];

/* Single-threaded fallback state variables */
static int st_brake_pressure = 0;
static int st_brake_switch = 0;
static int st_steering_angle = 0;
static int st_engine_rpm = 2300;
static int st_vehicle_speed = 60;
static int st_engine_temp_c = 90;
static uint8_t st_infotainment_status = 1;
static unsigned long st_ecu_counts[ECU_COUNT] = {0};

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
 * MODERN ANSI IN-PLACE CLUSTER DASHBOARD
 * ============================================================================ */

static void make_gauge_bar(char *buf, size_t buf_sz, int val, int min_val, int max_val, int width, const char *color)
{
    int clamped = clamp_int(val, min_val, max_val);
    int filled = (max_val > min_val) ? ((clamped - min_val) * width / (max_val - min_val)) : 0;
    if (filled > width) filled = width;

    int pos = snprintf(buf, buf_sz, "%s[%s", ANSI_GRAY, color);
    for (int i = 0; i < width && (size_t)pos < buf_sz - 16; i++) {
        if (i == filled) {
            pos += snprintf(buf + pos, buf_sz - pos, "%s", ANSI_GRAY);
        }
        pos += snprintf(buf + pos, buf_sz - pos, "█");
    }
    snprintf(buf + pos, buf_sz - pos, "%s]%s", ANSI_GRAY, ANSI_RESET);
}

/* Progressive Multi-Zone Speed Gauge: Green (0-60 km/h) -> Cyan (61-100 km/h) -> Amber (>100 km/h) */
static void make_speed_gradient_bar(char *buf, size_t buf_sz, int speed_kmh, int width)
{
    int clamped = clamp_int(speed_kmh, 0, 130);
    int filled = (clamped * width) / 130;
    if (filled > width) filled = width;

    int pos = snprintf(buf, buf_sz, "%s[", ANSI_GRAY);
    int cur_col = -1;

    for (int i = 0; i < width && (size_t)pos < buf_sz - 16; i++) {
        if (i < filled) {
            int col_id = (i < 11) ? 0 : (i < 18) ? 1 : 2;
            if (col_id != cur_col) {
                const char *esc = (col_id == 0) ? ANSI_GREEN : (col_id == 1) ? ANSI_CYAN : ANSI_YELLOW;
                pos += snprintf(buf + pos, buf_sz - pos, "%s", esc);
                cur_col = col_id;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        } else {
            if (cur_col != 3) {
                pos += snprintf(buf + pos, buf_sz - pos, "%s", ANSI_GRAY);
                cur_col = 3;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        }
    }
    snprintf(buf + pos, buf_sz - pos, "%s]%s", ANSI_GRAY, ANSI_RESET);
}

/* Progressive Multi-Zone RPM Rev Bar: Blue (800-2400) -> Amber (2401-3200) -> Redline (>3200) */
static void make_rpm_gradient_bar(char *buf, size_t buf_sz, int rpm, int min_rpm, int max_rpm, int width)
{
    int clamped = clamp_int(rpm, min_rpm, max_rpm);
    int filled = (max_rpm > min_rpm) ? ((clamped - min_rpm) * width / (max_rpm - min_rpm)) : 0;
    if (filled > width) filled = width;

    int pos = snprintf(buf, buf_sz, "%s[", ANSI_GRAY);
    int cur_col = -1;

    for (int i = 0; i < width && (size_t)pos < buf_sz - 16; i++) {
        if (i < filled) {
            int col_id = (i < 12) ? 0 : (i < 18) ? 1 : 2;
            if (col_id != cur_col) {
                const char *esc = (col_id == 0) ? ANSI_CYAN : (col_id == 1) ? ANSI_YELLOW : ANSI_RED;
                pos += snprintf(buf + pos, buf_sz - pos, "%s", esc);
                cur_col = col_id;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        } else {
            if (cur_col != 3) {
                pos += snprintf(buf + pos, buf_sz - pos, "%s", ANSI_GRAY);
                cur_col = 3;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        }
    }
    snprintf(buf + pos, buf_sz - pos, "%s]%s", ANSI_GRAY, ANSI_RESET);
}

/* Progressive Multi-Zone Brake Bar: Amber (1-50%) -> Emergency Red (>50%) */
static void make_brake_gradient_bar(char *buf, size_t buf_sz, int press_pct, int width)
{
    int clamped = clamp_int(press_pct, 0, 100);
    int filled = (clamped * width) / 100;
    if (filled > width) filled = width;

    int pos = snprintf(buf, buf_sz, "%s[", ANSI_GRAY);
    int cur_col = -1;

    for (int i = 0; i < width && (size_t)pos < buf_sz - 16; i++) {
        if (i < filled) {
            int col_id = (i < 12) ? 0 : 1;
            if (col_id != cur_col) {
                const char *esc = (col_id == 0) ? ANSI_YELLOW : ANSI_RED;
                pos += snprintf(buf + pos, buf_sz - pos, "%s", esc);
                cur_col = col_id;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        } else {
            if (cur_col != 2) {
                pos += snprintf(buf + pos, buf_sz - pos, "%s", ANSI_GRAY);
                cur_col = 2;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        }
    }
    snprintf(buf + pos, buf_sz - pos, "%s]%s", ANSI_GRAY, ANSI_RESET);
}

/* Progressive Multi-Zone Thermal Gauge: Blue (<85C) -> Green (85-98C) -> Amber (98-102C) -> Red (>102C) */
static void make_temp_gradient_bar(char *buf, size_t buf_sz, int temp_c, int min_t, int max_t, int width)
{
    int clamped = clamp_int(temp_c, min_t, max_t);
    int filled = (max_t > min_t) ? ((clamped - min_t) * width / (max_t - min_t)) : 0;
    if (filled > width) filled = width;

    int pos = snprintf(buf, buf_sz, "%s[", ANSI_GRAY);
    int cur_col = -1;

    for (int i = 0; i < width && (size_t)pos < buf_sz - 16; i++) {
        if (i < filled) {
            int col_id = (i < 5) ? 0 : (i < 17) ? 1 : (i < 21) ? 2 : 3;
            if (col_id != cur_col) {
                const char *esc = (col_id == 0) ? ANSI_CYAN : (col_id == 1) ? ANSI_GREEN : (col_id == 2) ? ANSI_YELLOW : ANSI_RED;
                pos += snprintf(buf + pos, buf_sz - pos, "%s", esc);
                cur_col = col_id;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        } else {
            if (cur_col != 4) {
                pos += snprintf(buf + pos, buf_sz - pos, "%s", ANSI_GRAY);
                cur_col = 4;
            }
            pos += snprintf(buf + pos, buf_sz - pos, "█");
        }
    }
    snprintf(buf + pos, buf_sz - pos, "%s]%s", ANSI_GRAY, ANSI_RESET);
}

/* Horizon Precision Steering Angle Dial with Center Notch & Turn Arrows */
static void make_steer_bar(char *buf, size_t buf_sz, int angle_deci, int width, const char *color)
{
    int center = width / 2;
    int max_offset = center - 1;
    int offset = (angle_deci * max_offset) / 450;
    if (offset < -max_offset) offset = -max_offset;
    if (offset > max_offset) offset = max_offset;
    int mark = center + offset;

    int pos = snprintf(buf, buf_sz, "%s[", ANSI_GRAY);
    for (int i = 0; i < width && (size_t)pos < buf_sz - 16; i++) {
        if (i == mark) {
            pos += snprintf(buf + pos, buf_sz - pos, "%s●%s", color, ANSI_GRAY);
        } else if (offset < 0 && i > mark && i < center) {
            pos += snprintf(buf + pos, buf_sz - pos, "%s◄%s", color, ANSI_GRAY);
        } else if (offset > 0 && i > center && i < mark) {
            pos += snprintf(buf + pos, buf_sz - pos, "%s►%s", color, ANSI_GRAY);
        } else if (i == 0) {
            pos += snprintf(buf + pos, buf_sz - pos, "◄");
        } else if (i == width - 1) {
            pos += snprintf(buf + pos, buf_sz - pos, "►");
        } else if (i == center) {
            pos += snprintf(buf + pos, buf_sz - pos, "%s│%s", ANSI_WHITE, ANSI_GRAY);
        } else {
            pos += snprintf(buf + pos, buf_sz - pos, "─");
        }
    }
    snprintf(buf + pos, buf_sz - pos, "%s]%s", ANSI_GRAY, ANSI_RESET);
}

static void render_dashboard_cluster(const TelemetrySnapshot *s)
{
    int minutes = (int)(s->elapsed_s / 60.0);
    int seconds = (int)(s->elapsed_s) % 60;

    char speed_bar[256];
    char rpm_bar[256];
    char brake_bar[256];
    char steer_bar[256];
    char temp_bar[256];
    char dur_bar[256];

    /* Dynamic Color & Threshold Evaluation */
    const char *speed_color = ANSI_GREEN;
    const char *speed_badge = "(City Zone)";
    if (s->speed_kmh > 100) {
        speed_color = ANSI_YELLOW;
        speed_badge = ANSI_BG_YELLOW " ⚡ HIGH SPEED " ANSI_RESET;
    } else if (s->speed_kmh > 60) {
        speed_color = ANSI_CYAN;
        speed_badge = "(Highway Cruise)";
    }

    const char *rpm_color = ANSI_CYAN;
    const char *rpm_badge = "(Cruise: Nominal)";
    if (s->rpm >= 3200) {
        rpm_color = ANSI_RED;
        rpm_badge = ANSI_BG_RED " ⚠ REDLINE LIMIT " ANSI_RESET;
    } else if (s->rpm >= 2400) {
        rpm_color = ANSI_YELLOW;
        rpm_badge = ANSI_BG_YELLOW " HIGH LOAD ZONE " ANSI_RESET;
    }

    const char *brake_color = ANSI_GRAY;
    const char *brake_badge = "[○ RELEASED]";
    if (s->brake_switch) {
        if (s->brake_pressure > 50) {
            brake_color = ANSI_RED;
            brake_badge = ANSI_BG_RED " 🚨 HARD BRAKE " ANSI_RESET;
        } else {
            brake_color = ANSI_YELLOW;
            brake_badge = ANSI_BG_YELLOW " ● BRAKE ENGAGED " ANSI_RESET;
        }
    }

    const char *steer_color = ANSI_CYAN;
    const char *turn_str = "Straight";
    if (s->steer_deci < -15) {
        turn_str = "Left Turn";
        steer_color = (s->steer_deci < -35) ? ANSI_YELLOW : ANSI_GREEN;
    } else if (s->steer_deci > 15) {
        turn_str = "Right Turn";
        steer_color = (s->steer_deci > 35) ? ANSI_YELLOW : ANSI_GREEN;
    }

    const char *temp_color = ANSI_GREEN;
    const char *temp_badge = "[COOLANT NOMINAL]";
    if (s->engine_temp > 102) {
        temp_color = ANSI_RED;
        temp_badge = ANSI_BG_RED " 🔥 OVERHEAT WARN " ANSI_RESET;
    } else if (s->engine_temp > 98) {
        temp_color = ANSI_YELLOW;
        temp_badge = ANSI_BG_YELLOW " ⚠ ELEVATED TEMP " ANSI_RESET;
    } else if (s->engine_temp < 85) {
        temp_color = ANSI_CYAN;
        temp_badge = "[WARMUP PHASE]";
    }

    make_speed_gradient_bar(speed_bar, sizeof(speed_bar), s->speed_kmh, 24);
    make_rpm_gradient_bar(rpm_bar, sizeof(rpm_bar), s->rpm, 800, 4000, 24);
    make_brake_gradient_bar(brake_bar, sizeof(brake_bar), (s->brake_switch ? s->brake_pressure : 0), 24);
    make_steer_bar(steer_bar, sizeof(steer_bar), s->steer_deci, 24, steer_color);
    make_temp_gradient_bar(temp_bar, sizeof(temp_bar), s->engine_temp, 80, 105, 24);

    int dur_pct = 0;
    if (s->duration_sec > 0) {
        dur_pct = (int)((s->elapsed_s * 100.0) / (double)s->duration_sec);
        if (dur_pct > 100) dur_pct = 100;
        make_gauge_bar(dur_bar, sizeof(dur_bar), dur_pct, 0, 100, 14, ANSI_WHITE);
    } else {
        snprintf(dur_bar, sizeof(dur_bar), "%s[  CONTINUOUS RUN  ]%s", ANSI_GRAY, ANSI_RESET);
    }

    /* Transmission Gear & Drive Mode Calculation */
    char gear_badge[128];
    char mode_desc[64];
    if (s->speed_kmh == 0) {
        if (s->brake_switch) {
            snprintf(gear_badge, sizeof(gear_badge), "%s◄[ P ]►%s  %s( R )  ( N )  ( D )%s",
                     ANSI_YELLOW, ANSI_RESET, ANSI_GRAY, ANSI_RESET);
            snprintf(mode_desc, sizeof(mode_desc), "%s[PARK ENGAGED]%s", ANSI_YELLOW, ANSI_RESET);
        } else {
            snprintf(gear_badge, sizeof(gear_badge), "%s( P )  ( R )%s  %s◄[ N ]►%s  %s( D )%s",
                     ANSI_GRAY, ANSI_RESET, ANSI_CYAN, ANSI_RESET, ANSI_GRAY, ANSI_RESET);
            snprintf(mode_desc, sizeof(mode_desc), "%s[NEUTRAL IDLE]%s", ANSI_CYAN, ANSI_RESET);
        }
    } else {
        int g = 1;
        if (s->speed_kmh < 25) g = 1;
        else if (s->speed_kmh < 50) g = 2;
        else if (s->speed_kmh < 75) g = 3;
        else if (s->speed_kmh < 105) g = 4;
        else g = 5;

        snprintf(gear_badge, sizeof(gear_badge), "%s( P )  ( R )  ( N )%s  %s◄[ D%d ]►%s",
                 ANSI_GRAY, ANSI_RESET, ANSI_GREEN, g, ANSI_RESET);
        snprintf(mode_desc, sizeof(mode_desc), "%s[FORWARD D-%d]%s", ANSI_GREEN, g, ANSI_RESET);
    }

    /* Move cursor to row 1, col 1 without clearing entire screen (zero flicker) */
    printf("\033[H");

    /* Border top with rounded corners (exact 90 display columns: col 1 to 90) */
    printf("%s╭────────────────────────────────────────────────────────────────────────────────────────╮%s\033[K\n", ANSI_CYAN, ANSI_RESET);

    int title_pad = 45 - (int)strlen(s->arch_mode);
    if (title_pad < 0) title_pad = 0;
    printf("%s│%s  %s► CAN-SENTINEL AUTOMOTIVE ECU CLUSTER%s  %s(%s)%s%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ANSI_RESET, ANSI_YELLOW, s->arch_mode, ANSI_RESET,
           title_pad, "", ANSI_CYAN, ANSI_RESET);
    printf("%s├────────────────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

    /* Architecture meta line */
    int meta_pad = 34 - (int)strlen(s->workers_desc);
    if (meta_pad < 0) meta_pad = 0;
    printf("%s│%s  Interface: %svcan0%s  │  Kernel: %sSocketCAN%s  │  Workers: %s%s%s%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ANSI_RESET, ANSI_WHITE, ANSI_RESET,
           ANSI_GREEN, s->workers_desc, ANSI_RESET,
           meta_pad, "", ANSI_CYAN, ANSI_RESET);
    printf("%s├────────────────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

    /* Telemetry gauges section */
    printf("%s│%s  %sVEHICLE TELEMETRY DYNAMICS%s%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ANSI_RESET, 60, "", ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    printf("%s│%s  GEAR  : %s   DRIVE MODE: %s%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, gear_badge, mode_desc,
           22, "", ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    printf("%s│%s  SPEED : %s  %s%3d km/h%s  %s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, speed_bar, speed_color, s->speed_kmh, ANSI_RESET,
           speed_badge, ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    printf("%s│%s  RPM   : %s  %s%4d RPM%s  %s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, rpm_bar, rpm_color, s->rpm, ANSI_RESET,
           rpm_badge, ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    printf("%s│%s  BRAKE : %s  %s%3d %%%s     %s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, brake_bar, brake_color, (s->brake_switch ? s->brake_pressure : 0), ANSI_RESET,
           brake_badge, ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    int steer_pad = 10 - (int)strlen(turn_str);
    if (steer_pad < 0) steer_pad = 0;
    printf("%s│%s  STEER : %s  %s%+5.1f deg%s  (%s)%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, steer_bar, steer_color, (double)s->steer_deci / 10.0, ANSI_RESET,
           turn_str, steer_pad, "", ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    printf("%s│%s  TEMP  : %s  %s%5.1f °C%s  %s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, temp_bar, temp_color, (double)s->engine_temp, ANSI_RESET,
           temp_badge, ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    printf("%s│%s  INFO  : %s[%s] Nav Gateway: Route Guidance Active%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET,
           (s->infotainment ? ANSI_GREEN : ANSI_GRAY),
           (s->infotainment ? "● MEDIA ON " : "○ MEDIA OFF"),
           30, "", ANSI_CYAN, ANSI_RESET);

    printf("%s├────────────────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

    /* Per-ECU Status Table */
    printf("%s│%s  %sPER-ECU TRANSMISSION STATUS & REAL-TIME SCHEDULING%s%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ANSI_RESET, 36, "", ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    for (int i = 0; i < ECU_COUNT; i++) {
        const char *policy_str = (thread_configs[i].sched_policy == SCHED_FIFO) ? "SCHED_FIFO" : "SCHED_OTHER";
        int prio = thread_configs[i].rt_priority;
        char prio_buf[32];
        if (thread_configs[i].sched_policy == SCHED_FIFO) {
            snprintf(prio_buf, sizeof(prio_buf), "%s (%d)", policy_str, prio);
        } else {
            snprintf(prio_buf, sizeof(prio_buf), "%s (0)", policy_str);
        }

        int hz = (int)(1000000L / thread_configs[i].period_us);
        printf("%s│%s  [%s●%s] 0x%03X  %-19s %3ld ms (%3d Hz) │ Frames: %7lu │ %-15s    \033[K\033[90G%s│%s\n",
               ANSI_CYAN, ANSI_RESET,
               ANSI_GREEN, ANSI_RESET,
               thread_configs[i].can_id,
               thread_configs[i].name,
               thread_configs[i].period_us / 1000L,
               hz,
               s->ecu_counts[i],
               prio_buf,
               ANSI_CYAN, ANSI_RESET);
    }

    printf("%s├────────────────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

    /* Rolling Telemetry History Feed (Simultaneous with visual cluster) */
    printf("%s│%s  %sLIVE TELEMETRY FEED (ROLLING 50-SECOND WINDOW / 10 RECENT SNAPSHOTS)%s%*s\033[K\033[90G%s│%s\n",
           ANSI_CYAN, ANSI_RESET, ANSI_WHITE, ANSI_RESET, 18, "", ANSI_CYAN, ANSI_RESET);
    printf("%s│%*s\033[K\033[90G%s│%s\n", ANSI_CYAN, 88, "", ANSI_CYAN, ANSI_RESET);

    for (int i = 0; i < TELEMETRY_HISTORY_LINES; i++) {
        if (telemetry_history[i].valid) {
            char brake_buf[32];
            if (telemetry_history[i].brake_switch) {
                const char *bcol = (telemetry_history[i].brake_pressure > 50) ? ANSI_RED : ANSI_YELLOW;
                if (telemetry_history[i].brake_pressure == 100) {
                    snprintf(brake_buf, sizeof(brake_buf), "%sON (100%%)%s", bcol, ANSI_RESET);
                } else {
                    snprintf(brake_buf, sizeof(brake_buf), "%sON (%2d%%)%s ", bcol, telemetry_history[i].brake_pressure, ANSI_RESET);
                }
            } else {
                snprintf(brake_buf, sizeof(brake_buf), "%sOFF      %s", ANSI_GRAY, ANSI_RESET);
            }

            const char *h_spd_col = (telemetry_history[i].speed_kmh > 100) ? ANSI_YELLOW :
                                    (telemetry_history[i].speed_kmh > 60) ? ANSI_CYAN : ANSI_GREEN;
            const char *h_rpm_col = (telemetry_history[i].rpm >= 3200) ? ANSI_RED :
                                    (telemetry_history[i].rpm >= 2400) ? ANSI_YELLOW : ANSI_CYAN;

            printf("%s│%s  %s[%02d:%02d]%s Frames: %s%7lu%s │ %s%5.1f fps%s │ Speed: %s%3d km/h%s │ RPM: %s%4d%s │ Brake: %s\033[K\033[90G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET,
                   ANSI_WHITE, telemetry_history[i].minutes, telemetry_history[i].seconds, ANSI_RESET,
                   ANSI_WHITE, telemetry_history[i].frames, ANSI_RESET,
                   ANSI_GREEN, telemetry_history[i].fps, ANSI_RESET,
                   h_spd_col, telemetry_history[i].speed_kmh, ANSI_RESET,
                   h_rpm_col, telemetry_history[i].rpm, ANSI_RESET,
                   brake_buf,
                   ANSI_CYAN, ANSI_RESET);
        } else {
            printf("%s│%s  %s[--:--] Awaiting 5-second periodic telemetry sample...%s%*s\033[K\033[90G%s│%s\n",
                   ANSI_CYAN, ANSI_RESET, ANSI_GRAY, ANSI_RESET, 33, "", ANSI_CYAN, ANSI_RESET);
        }
    }

    printf("%s├────────────────────────────────────────────────────────────────────────────────────────┤%s\033[K\n", ANSI_CYAN, ANSI_RESET);

    /* Bottom footer summary */
    if (s->duration_sec > 0) {
        int dur_m = (int)(s->duration_sec / 60);
        int dur_s = (int)(s->duration_sec % 60);
        printf("%s│%s  TIME: %02d:%02d / %02d:%02d  %s %3d%% │ %sTOTAL: %7lu frames (Rate: %5.1f fps)%s \033[K\033[90G%s│%s\n",
               ANSI_CYAN, ANSI_RESET,
               minutes, seconds, dur_m, dur_s,
               dur_bar, dur_pct,
               ANSI_WHITE, s->total_frames, s->fps, ANSI_RESET,
               ANSI_CYAN, ANSI_RESET);
    } else {
        printf("%s│%s  ELAPSED: %02d:%02d (Continuous) │ %sTOTAL FRAMES: %7lu │ RATE: %5.1f fps%s%*s\033[K\033[90G%s│%s\n",
               ANSI_CYAN, ANSI_RESET,
               minutes, seconds,
               ANSI_WHITE, s->total_frames, s->fps, ANSI_RESET,
               17, "", ANSI_CYAN, ANSI_RESET);
    }

    printf("%s╰────────────────────────────────────────────────────────────────────────────────────────╯%s\033[K\n", ANSI_CYAN, ANSI_RESET);
    printf(" %s[Press Ctrl+C to stop simulation cleanly]%s\033[K\n", ANSI_GRAY, ANSI_RESET);
    fflush(stdout);
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

static int st_send_frame(int socket_fd, ECU *ecu, int index)
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
    st_ecu_counts[index]++;
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
    struct timespec next_dashboard;
    unsigned long total_frames = 0;

    if (!use_dashboard) {
        printf("Architecture: Single-Threaded Bounded Scheduler\n");
        printf("CAN interface: vcan0\n");
        printf("Protocol: six periodic ECU frames, DLC 8\n");
        printf("Timing jitter: approximately +/-1 ms\n");
        if (duration_sec > 0) {
            printf("Simulation duration: %ld seconds (auto-stop)\n", duration_sec);
        }
        printf("Press Ctrl+C to stop.\n");
        fflush(stdout);
    } else {
        /* Clear screen and hide cursor for smooth in-place cluster */
        printf("\033[2J\033[?25l");
        fflush(stdout);
    }

    if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
        perror("Failed to read monotonic clock");
        close(socket_fd);
        return EXIT_FAILURE;
    }

    start_time = now;
    next_signal_update = add_us(now, SIGNAL_UPDATE_US);
    next_telemetry = add_us(now, TELEMETRY_INTERVAL_US);
    next_dashboard = add_us(now, DASHBOARD_REFRESH_US);
    next_brake_toggle = add_us(now, random_range(BRAKE_HOLD_MIN_US, BRAKE_HOLD_MAX_US));

    for (int i = 0; i < ECU_COUNT; i++) {
        long initial_delay = ecus[i].period_us + random_jitter_us();
        ecus[i].next_send = add_us(now, initial_delay);
    }

    /* Seed initial telemetry snapshot at t=00:00 */
    record_telemetry_snapshot(0, 0, 0, 0.0, st_vehicle_speed, st_engine_rpm,
                              st_steering_angle, st_brake_switch, st_brake_pressure, false);

    while (running) {
        if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
            perror("Failed to read monotonic clock");
            break;
        }

        if (duration_sec > 0 && (now.tv_sec - start_time.tv_sec) >= duration_sec) {
            running = 0;
            break;
        }

        if (timespec_diff_us(&now, &next_signal_update) >= 0) {
            st_update_vehicle_state(&now);
            next_signal_update = add_us(next_signal_update, SIGNAL_UPDATE_US);

            while (timespec_diff_us(&now, &next_signal_update) >= 0) {
                next_signal_update = add_us(next_signal_update, SIGNAL_UPDATE_US);
            }
        }

        /* Render Dashboard (10 Hz) */
        if (use_dashboard) {
            if (timespec_diff_us(&now, &next_dashboard) >= 0) {
                double elapsed_s = (double)(now.tv_sec - start_time.tv_sec)
                                 + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
                double fps = (elapsed_s > 0.0) ? ((double)total_frames / elapsed_s) : 0.0;

                TelemetrySnapshot snap;
                snap.arch_mode = "SINGLE-THREADED BOUNDED LOOP";
                snap.workers_desc = "1 Main Thread (Cooperative Yield)";
                snap.is_multithreaded = false;
                snap.total_frames = total_frames;
                snap.fps = fps;
                snap.elapsed_s = elapsed_s;
                snap.duration_sec = duration_sec;
                snap.speed_kmh = st_vehicle_speed;
                snap.rpm = st_engine_rpm;
                snap.steer_deci = st_steering_angle;
                snap.brake_switch = st_brake_switch;
                snap.brake_pressure = st_brake_pressure;
                snap.engine_temp = st_engine_temp_c;
                snap.infotainment = st_infotainment_status;
                for (int i = 0; i < ECU_COUNT; i++) {
                    snap.ecu_counts[i] = st_ecu_counts[i];
                }

                render_dashboard_cluster(&snap);

                next_dashboard = add_us(next_dashboard, DASHBOARD_REFRESH_US);
                while (timespec_diff_us(&now, &next_dashboard) >= 0) {
                    next_dashboard = add_us(next_dashboard, DASHBOARD_REFRESH_US);
                }
            }
        }

        /* Periodic Telemetry Sampling (5s) */
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

            if (!use_dashboard) {
                printf("[TELEMETRY] [%02d:%02d] Frames: %7lu | Rate: %5.1f fps | Speed: %3d km/h | RPM: %4d | Steer: %+5.1f deg | Brake: %s\n",
                       minutes, seconds, total_frames, fps, st_vehicle_speed, st_engine_rpm,
                       (double)st_steering_angle / 10.0, brake_info);
                fflush(stdout);
            }

            record_telemetry_snapshot(minutes, seconds, total_frames, fps,
                                      st_vehicle_speed, st_engine_rpm, st_steering_angle,
                                      st_brake_switch, st_brake_pressure, false);

            next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            while (timespec_diff_us(&now, &next_telemetry) >= 0) {
                next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            }
        }

        for (int i = 0; i < ECU_COUNT && running; i++) {
            if (timespec_diff_us(&now, &ecus[i].next_send) >= 0) {
                if (st_send_frame(socket_fd, &ecus[i], i) < 0) {
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
            if (wait_us > 0) {
                sched_yield();
            }
        }
    }

    close(socket_fd);

    if (use_dashboard) {
        /* Restore cursor visibility and position below dashboard */
        printf("\033[?25h\n\n");
        fflush(stdout);
    }

    double total_duration_s = (double)(now.tv_sec - start_time.tv_sec)
                            + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
    double avg_fps = (total_duration_s > 0.0) ? ((double)total_frames / total_duration_s) : 0.0;

    printf("CAN-Sentinel ECU Simulator stopped.\n");
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
            atomic_fetch_add_explicit(&atomic_ecu_counts[cfg->id_index], 1, memory_order_relaxed);
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
    struct timespec next_dashboard;

    /* Initialize atomic state */
    atomic_init(&atomic_state.brake_pressure, 0);
    atomic_init(&atomic_state.brake_switch, 0);
    atomic_init(&atomic_state.steering_angle, 0);
    atomic_init(&atomic_state.engine_rpm, 2300);
    atomic_init(&atomic_state.vehicle_speed, 60);
    atomic_init(&atomic_state.engine_temp_c, 90);
    atomic_init(&atomic_state.infotainment_status, 1);
    atomic_init(&atomic_total_frames, 0);
    for (int i = 0; i < ECU_COUNT; i++) {
        atomic_init(&atomic_ecu_counts[i], 0);
    }

    if (!use_dashboard) {
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
    } else {
        printf("\033[2J\033[?25l");
        fflush(stdout);
    }

    clock_gettime(CLOCK_MONOTONIC, &start_time);
    next_telemetry = add_us(start_time, TELEMETRY_INTERVAL_US);
    next_dashboard = add_us(start_time, DASHBOARD_REFRESH_US);

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

    /* Seed initial telemetry snapshot at t=00:00 */
    record_telemetry_snapshot(0, 0, 0, 0.0,
                              atomic_load_explicit(&atomic_state.vehicle_speed, memory_order_relaxed),
                              atomic_load_explicit(&atomic_state.engine_rpm, memory_order_relaxed),
                              atomic_load_explicit(&atomic_state.steering_angle, memory_order_relaxed),
                              atomic_load_explicit(&atomic_state.brake_switch, memory_order_relaxed),
                              atomic_load_explicit(&atomic_state.brake_pressure, memory_order_relaxed),
                              true);

    /* Main thread supervises execution, reports telemetry, and monitors duration */
    while (running) {
        clock_gettime(CLOCK_MONOTONIC, &now);

        if (duration_sec > 0 && (now.tv_sec - start_time.tv_sec) >= duration_sec) {
            running = 0;
            break;
        }

        /* Render Dashboard (10 Hz) */
        if (use_dashboard) {
            if (timespec_diff_us(&now, &next_dashboard) >= 0) {
                double elapsed_s = (double)(now.tv_sec - start_time.tv_sec)
                                 + (double)(now.tv_nsec - start_time.tv_nsec) / 1e9;
                unsigned long frames = atomic_load_explicit(&atomic_total_frames, memory_order_relaxed);
                double fps = (elapsed_s > 0.0) ? ((double)frames / elapsed_s) : 0.0;

                TelemetrySnapshot snap;
                snap.arch_mode = "MULTI-THREADED DISTRIBUTED";
                snap.workers_desc = "7 pthreads (C11 Lock-Free)";
                snap.is_multithreaded = true;
                snap.total_frames = frames;
                snap.fps = fps;
                snap.elapsed_s = elapsed_s;
                snap.duration_sec = duration_sec;
                snap.speed_kmh = atomic_load_explicit(&atomic_state.vehicle_speed, memory_order_acquire);
                snap.rpm = atomic_load_explicit(&atomic_state.engine_rpm, memory_order_acquire);
                snap.steer_deci = atomic_load_explicit(&atomic_state.steering_angle, memory_order_acquire);
                snap.brake_switch = atomic_load_explicit(&atomic_state.brake_switch, memory_order_acquire);
                snap.brake_pressure = atomic_load_explicit(&atomic_state.brake_pressure, memory_order_acquire);
                snap.engine_temp = atomic_load_explicit(&atomic_state.engine_temp_c, memory_order_acquire);
                snap.infotainment = atomic_load_explicit(&atomic_state.infotainment_status, memory_order_acquire);
                for (int i = 0; i < ECU_COUNT; i++) {
                    snap.ecu_counts[i] = atomic_load_explicit(&atomic_ecu_counts[i], memory_order_relaxed);
                }

                render_dashboard_cluster(&snap);

                next_dashboard = add_us(next_dashboard, DASHBOARD_REFRESH_US);
                while (timespec_diff_us(&now, &next_dashboard) >= 0) {
                    next_dashboard = add_us(next_dashboard, DASHBOARD_REFRESH_US);
                }
            }
        }

        /* Periodic Telemetry Sampling (5s) */
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

            if (!use_dashboard) {
                printf("[TELEMETRY-MT] [%02d:%02d] Frames: %7lu | Rate: %5.1f fps | Speed: %3d km/h | RPM: %4d | Steer: %+5.1f deg | Brake: %s\n",
                       minutes, seconds, frames, fps, spd, rpm, (double)steer / 10.0, brake_info);
                fflush(stdout);
            }

            record_telemetry_snapshot(minutes, seconds, frames, fps,
                                      spd, rpm, steer, b_switch, b_press, true);

            next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            while (timespec_diff_us(&now, &next_telemetry) >= 0) {
                next_telemetry = add_us(next_telemetry, TELEMETRY_INTERVAL_US);
            }
        }

        /* Sleep 50 ms before next supervisor loop iteration */
        struct timespec tick = {0, 50000000L};
        nanosleep(&tick, NULL);
    }

    /* Join all threads to ensure 100% clean resource deallocation */
    for (int i = 0; i < ECU_COUNT; i++) {
        pthread_join(ecu_threads[i], NULL);
    }
    pthread_join(physics_thread, NULL);

    if (use_dashboard) {
        printf("\033[?25h\n\n");
        fflush(stdout);
    }

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
    printf("  --plain, -p          Disable visual dashboard and use scrolling text telemetry\n");
    printf("  --duration, -d <sec> Auto-stop simulation after specified duration in seconds\n");
    printf("  --log, -l <file>     Stream plain text telemetry to specified log file while running\n");
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

    /* Automatically disable dashboard if stdout is redirected to a file or pipe */
    if (!isatty(STDOUT_FILENO)) {
        use_dashboard = false;
    }

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--threads") == 0 || strcmp(argv[i], "-t") == 0) {
            multithreaded_mode = true;
        } else if (strcmp(argv[i], "--plain") == 0 || strcmp(argv[i], "-p") == 0) {
            use_dashboard = false;
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
        } else if (strcmp(argv[i], "--log") == 0 || strcmp(argv[i], "-l") == 0) {
            if (i + 1 >= argc) {
                fprintf(stderr, "Error: --log requires a file path argument\n");
                return EXIT_FAILURE;
            }
            i++;
            telemetry_log_file = fopen(argv[i], "w");
            if (!telemetry_log_file) {
                fprintf(stderr, "Error: failed to open log file '%s': %s\n", argv[i], strerror(errno));
                return EXIT_FAILURE;
            }
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

    (void)nice(-10);

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    int ret;
    if (multithreaded_mode) {
        ret = run_multithreaded(duration_sec);
    } else {
        ret = run_singlethreaded(duration_sec);
    }

    if (telemetry_log_file) {
        fclose(telemetry_log_file);
        telemetry_log_file = NULL;
    }

    return ret;
}

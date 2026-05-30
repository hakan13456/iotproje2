/*
 * MQTT-SN (emcute) metric node for RIOT OS
 * Tree topology — FIT IoT-LAB A8-M3
 *
 * Output format (serial):
 *   CSV,MQTTSN,<seq>,<send_ms>,<recv_ms>,<rtt_ms>
 *   SUMMARY,MQTTSN,SENT=N,RECV=N,PDR=XX.XX,AVG_RTT=XX.XX
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "net/emcute.h"
#include "net/ipv6/addr.h"
#include "net/sock/udp.h"
#include "ztimer.h"
#include "shell.h"
#include "msg.h"
#include "thread.h"

/* ---- tunables ---- */
#define BROKER_PORT         (1883U)
#define SEND_INTERVAL_MS    (500U)
#define NUM_MESSAGES        (200U)
#define WARMUP_MS           (5000U)   /* wait for RPL convergence */
#define QOS                 EMCUTE_QOS_0

/* ---- emcute internals ---- */
#define EMCUTE_PRIO         (THREAD_PRIORITY_MAIN - 1)
#define TOPIC_PUB           "metrics/rtt"
#define TOPIC_SUB           "metrics/rtt"
#define PAYLOAD_MAXLEN      (40U)

static char emcute_stack[THREAD_STACKSIZE_DEFAULT];
static msg_t emcute_queue[8];
static emcute_sub_t sub;
static char sub_topic_name[64];

/* ---- metric arrays ---- */
static uint32_t t_send[NUM_MESSAGES];
static uint32_t t_recv[NUM_MESSAGES];
static uint8_t  pkt_recv[NUM_MESSAGES];

/* ---- subscribe callback: fired when our own publish bounces back ---- */
static void on_pub(const emcute_topic_t *topic, void *data, size_t len)
{
    (void)topic;
    char buf[PAYLOAD_MAXLEN + 1];
    size_t copy = (len < PAYLOAD_MAXLEN) ? len : PAYLOAD_MAXLEN;
    memcpy(buf, data, copy);
    buf[copy] = '\0';

    unsigned seq = 0;
    uint32_t ts  = 0;
    if (sscanf(buf, "%u|%"SCNu32, &seq, &ts) == 2 && seq < NUM_MESSAGES) {
        uint32_t now = ztimer_now(ZTIMER_MSEC);
        t_recv[seq]  = now;
        pkt_recv[seq] = 1;
        printf("CSV,MQTTSN,%u,%"PRIu32",%"PRIu32",%"PRIu32"\n",
               seq, ts, now, now - ts);
    }
}

static void *emcute_thread(void *arg)
{
    (void)arg;
    msg_init_queue(emcute_queue, ARRAY_SIZE(emcute_queue));
    emcute_run(BROKER_PORT, "riot_mqtt_node");
    return NULL;
}

/* Connect + subscribe, called once broker IPv6 is known */
static int connect_and_subscribe(const char *broker_addr)
{
    sock_udp_ep_t gw = { .family = AF_INET6, .port = BROKER_PORT };
    if (ipv6_addr_from_str((ipv6_addr_t *)&gw.addr.ipv6, broker_addr) == NULL) {
        printf("ERROR: bad broker addr '%s'\n", broker_addr);
        return -1;
    }
    if (emcute_con(&gw, true, NULL, NULL, 0, 0) != EMCUTE_OK) {
        puts("ERROR: emcute_con failed");
        return -1;
    }
    puts("INFO: connected to broker");

    /* subscribe to echo topic */
    memcpy(sub_topic_name, TOPIC_SUB, strlen(TOPIC_SUB) + 1);
    sub.cb = on_pub;
    sub.topic.name = sub_topic_name;
    if (emcute_sub(&sub, QOS) != EMCUTE_OK) {
        puts("ERROR: emcute_sub failed");
        return -1;
    }
    puts("INFO: subscribed");
    return 0;
}

static void run_experiment(void)
{
    emcute_topic_t pub_topic;
    pub_topic.name = TOPIC_PUB;
    if (emcute_reg(&pub_topic) != EMCUTE_OK) {
        puts("ERROR: topic reg failed");
        return;
    }

    memset(pkt_recv, 0, sizeof(pkt_recv));

    puts("INFO: experiment starting");
    ztimer_sleep(ZTIMER_MSEC, WARMUP_MS);

    char payload[PAYLOAD_MAXLEN];
    for (unsigned i = 0; i < NUM_MESSAGES; i++) {
        uint32_t now = ztimer_now(ZTIMER_MSEC);
        t_send[i] = now;
        snprintf(payload, sizeof(payload), "%u|%"PRIu32, i, now);

        if (emcute_pub(&pub_topic, payload, strlen(payload), QOS) != EMCUTE_OK) {
            printf("CSV,MQTTSN,%u,%"PRIu32",0,LOST\n", i, now);
        }
        ztimer_sleep(ZTIMER_MSEC, SEND_INTERVAL_MS);
    }

    /* allow last replies to arrive */
    ztimer_sleep(ZTIMER_MSEC, 3000);

    /* summary */
    uint32_t delivered = 0;
    uint64_t total_rtt = 0;
    for (unsigned i = 0; i < NUM_MESSAGES; i++) {
        if (pkt_recv[i]) {
            delivered++;
            total_rtt += (t_recv[i] - t_send[i]);
        }
    }
    printf("SUMMARY,MQTTSN,SENT=%u,RECV=%"PRIu32",PDR=%.2f,AVG_RTT=%.2f\n",
           NUM_MESSAGES, delivered,
           (float)delivered / NUM_MESSAGES * 100.0f,
           delivered > 0 ? (float)total_rtt / delivered : 0.0f);
}

/* shell command: con <broker_ipv6> */
static int cmd_con(int argc, char **argv)
{
    if (argc != 2) { puts("usage: con <broker_ipv6>"); return 1; }
    return connect_and_subscribe(argv[1]);
}

/* shell command: run */
static int cmd_run(int argc, char **argv)
{
    (void)argc; (void)argv;
    run_experiment();
    return 0;
}

static const shell_command_t shell_cmds[] = {
    { "con",  "connect to MQTT-SN broker",  cmd_con  },
    { "run",  "run latency experiment",      cmd_run  },
    { NULL, NULL, NULL }
};

int main(void)
{
    puts("MQTT-SN metric node — RIOT/emcute");
    puts("Commands: con <broker_ipv6>   run");

    thread_create(emcute_stack, sizeof(emcute_stack),
                  EMCUTE_PRIO, 0, emcute_thread, NULL, "emcute");

    char line_buf[SHELL_DEFAULT_BUFSIZE];
    shell_run(shell_cmds, line_buf, SHELL_DEFAULT_BUFSIZE);
    return 0;
}

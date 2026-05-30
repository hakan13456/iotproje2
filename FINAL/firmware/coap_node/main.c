/*
 * CoAP (gcoap) metric node for RIOT OS
 * Tree topology — FIT IoT-LAB A8-M3
 *
 * Role auto-detection:
 *   - First node to boot becomes SERVER (listens on /metrics/rtt)
 *   - Others become CLIENTS (send CON POST, measure RTT)
 *
 * Set role via shell: role server | role client <server_ipv6>
 *
 * Output format (serial):
 *   CSV,COAP,<seq>,<send_ms>,<recv_ms>,<rtt_ms>
 *   SUMMARY,COAP,SENT=N,RECV=N,PDR=XX.XX,AVG_RTT=XX.XX
 */

#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "net/gcoap.h"
#include "net/sock/udp.h"
#include "net/ipv6/addr.h"
#include "ztimer.h"
#include "shell.h"
#include "msg.h"
#include "mutex.h"

/* ---- tunables ---- */
#define COAP_PORT           (5683U)
#define SEND_INTERVAL_MS    (500U)
#define NUM_MESSAGES        (200U)
#define WARMUP_MS           (5000U)
#define PAYLOAD_MAXLEN      (40U)
#define TIMEOUT_MS          (2000U)

/* ---- metric arrays ---- */
static uint32_t t_send[NUM_MESSAGES];
static uint32_t t_recv[NUM_MESSAGES];
static uint8_t  pkt_recv[NUM_MESSAGES];

/* client state */
static char server_addr_str[64];
static volatile unsigned pending_seq = 0;
static mutex_t recv_mutex = MUTEX_INIT;

/* ---- SERVER: resource handler ---- */
static ssize_t _metrics_handler(coap_pkt_t *pdu, uint8_t *buf, size_t len,
                                 coap_request_ctx_t *ctx)
{
    (void)ctx;
    /* echo payload back in 2.05 Content response */
    gcoap_resp_init(pdu, buf, len, COAP_CODE_CONTENT);
    coap_opt_add_format(pdu, COAP_FORMAT_TEXT);
    ssize_t plen = coap_payload_put_bytes(pdu,
                       (uint8_t *)pdu->payload, pdu->payload_len);
    if (plen < 0) {
        return gcoap_response(pdu, buf, len, COAP_CODE_INTERNAL_SERVER_ERROR);
    }
    return gcoap_finish(pdu, (size_t)plen, COAP_FORMAT_TEXT);
}

static const coap_resource_t resources[] = {
    { "/metrics/rtt", COAP_POST, _metrics_handler, NULL },
};
static gcoap_listener_t listener = {
    .resources     = resources,
    .resources_len = ARRAY_SIZE(resources),
};

/* ---- CLIENT: response callback ---- */
static void _resp_handler(const gcoap_request_memo_t *memo,
                          coap_pkt_t *pdu, const sock_udp_ep_t *remote)
{
    (void)remote;
    if (memo->state == GCOAP_MEMO_TIMEOUT) {
        unsigned seq = pending_seq;
        printf("CSV,COAP,%u,%"PRIu32",0,TIMEOUT\n", seq, t_send[seq]);
        mutex_unlock(&recv_mutex);
        return;
    }
    if (pdu && pdu->payload_len > 0) {
        char buf[PAYLOAD_MAXLEN + 1];
        size_t copy = (pdu->payload_len < PAYLOAD_MAXLEN)
                      ? pdu->payload_len : PAYLOAD_MAXLEN;
        memcpy(buf, pdu->payload, copy);
        buf[copy] = '\0';

        unsigned seq = 0;
        uint32_t ts  = 0;
        if (sscanf(buf, "%u|%"SCNu32, &seq, &ts) == 2 && seq < NUM_MESSAGES) {
            uint32_t now = ztimer_now(ZTIMER_MSEC);
            t_recv[seq]   = now;
            pkt_recv[seq] = 1;
            printf("CSV,COAP,%u,%"PRIu32",%"PRIu32",%"PRIu32"\n",
                   seq, ts, now, now - ts);
        }
    }
    mutex_unlock(&recv_mutex);
}

static void run_experiment(void)
{
    sock_udp_ep_t remote = { .family = AF_INET6, .port = COAP_PORT };
    if (ipv6_addr_from_str((ipv6_addr_t *)&remote.addr.ipv6,
                           server_addr_str) == NULL) {
        puts("ERROR: bad server addr — use: role client <ipv6>");
        return;
    }

    memset(pkt_recv, 0, sizeof(pkt_recv));
    puts("INFO: CoAP experiment starting");
    ztimer_sleep(ZTIMER_MSEC, WARMUP_MS);

    uint8_t buf[CONFIG_GCOAP_PDU_BUF_SIZE];
    char payload[PAYLOAD_MAXLEN];

    for (unsigned i = 0; i < NUM_MESSAGES; i++) {
        uint32_t now = ztimer_now(ZTIMER_MSEC);
        t_send[i] = now;
        pending_seq = i;

        snprintf(payload, sizeof(payload), "%u|%"PRIu32, i, now);

        coap_pkt_t pdu;
        gcoap_req_init(&pdu, buf, sizeof(buf), COAP_METHOD_POST, "/metrics/rtt");
        coap_opt_add_format(&pdu, COAP_FORMAT_TEXT);
        ssize_t plen = coap_payload_put_bytes(&pdu,
                           (uint8_t *)payload, strlen(payload));
        if (plen < 0) { continue; }
        ssize_t mlen = gcoap_finish(&pdu, (size_t)plen, COAP_FORMAT_TEXT);

        mutex_lock(&recv_mutex);
        if (gcoap_req_send(buf, (size_t)mlen, &remote, NULL,
                           _resp_handler, NULL, GCOAP_SOCKET_TYPE_UDP) == 0) {
            printf("CSV,COAP,%u,%"PRIu32",0,SEND_ERR\n", i, now);
            mutex_unlock(&recv_mutex);
        }
        /* wait for reply or timeout before next send */
        ztimer_sleep(ZTIMER_MSEC, SEND_INTERVAL_MS);
    }

    ztimer_sleep(ZTIMER_MSEC, TIMEOUT_MS + 500);

    uint32_t delivered = 0;
    uint64_t total_rtt = 0;
    for (unsigned i = 0; i < NUM_MESSAGES; i++) {
        if (pkt_recv[i]) {
            delivered++;
            total_rtt += (t_recv[i] - t_send[i]);
        }
    }
    printf("SUMMARY,COAP,SENT=%u,RECV=%"PRIu32",PDR=%.2f,AVG_RTT=%.2f\n",
           NUM_MESSAGES, delivered,
           (float)delivered / NUM_MESSAGES * 100.0f,
           delivered > 0 ? (float)total_rtt / delivered : 0.0f);
}

/* ---- shell commands ---- */
static int cmd_role(int argc, char **argv)
{
    if (argc < 2) {
        puts("usage: role server | role client <server_ipv6>");
        return 1;
    }
    if (strcmp(argv[1], "server") == 0) {
        gcoap_register_listener(&listener);
        puts("INFO: CoAP server listening on /metrics/rtt");
    }
    else if (strcmp(argv[1], "client") == 0 && argc == 3) {
        strncpy(server_addr_str, argv[2], sizeof(server_addr_str) - 1);
        printf("INFO: CoAP client → server %s\n", server_addr_str);
    }
    else {
        puts("usage: role server | role client <server_ipv6>");
        return 1;
    }
    return 0;
}

static int cmd_run(int argc, char **argv)
{
    (void)argc; (void)argv;
    run_experiment();
    return 0;
}

static const shell_command_t shell_cmds[] = {
    { "role", "set node role (server/client)", cmd_role },
    { "run",  "run RTT experiment",            cmd_run  },
    { NULL, NULL, NULL }
};

int main(void)
{
    puts("CoAP metric node — RIOT/gcoap");
    puts("Commands: role server | role client <ipv6>   run");

    char line_buf[SHELL_DEFAULT_BUFSIZE];
    shell_run(shell_cmds, line_buf, SHELL_DEFAULT_BUFSIZE);
    return 0;
}

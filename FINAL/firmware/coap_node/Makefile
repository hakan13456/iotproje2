APPLICATION = coap_node
BOARD      ?= iotlab-a8-m3
RIOTBASE   ?= $(CURDIR)/../../RIOT

USEMODULE += gcoap
USEMODULE += gnrc_netdev_default
USEMODULE += auto_init_gnrc_netif
USEMODULE += gnrc_ipv6_router_default
USEMODULE += gnrc_rpl
USEMODULE += gnrc_icmpv6_echo
USEMODULE += gnrc_sock_udp
USEMODULE += shell
USEMODULE += shell_cmds_default
USEMODULE += ps
USEMODULE += ztimer_msec

DEFAULT_CHANNEL ?= 26
CFLAGS += -DCONFIG_IEEE802154_DEFAULT_CHANNEL=$(DEFAULT_CHANNEL)
CFLAGS += -DCONFIG_GCOAP_PDU_BUF_SIZE=256

include $(RIOTBASE)/Makefile.include

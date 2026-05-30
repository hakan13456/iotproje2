APPLICATION = mqtt_node
BOARD      ?= iotlab-a8-m3
RIOTBASE   ?= $(CURDIR)/../../RIOT

USEMODULE += emcute
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
USEMODULE += ztimer_usec

CFLAGS += -DCONFIG_EMCUTE_KEEPALIVE_PING=1

DEFAULT_CHANNEL ?= 26
CFLAGS += -DCONFIG_IEEE802154_DEFAULT_CHANNEL=$(DEFAULT_CHANNEL)

include $(RIOTBASE)/Makefile.include

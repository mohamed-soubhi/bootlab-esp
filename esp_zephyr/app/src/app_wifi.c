/*
 * SPDX-License-Identifier: Apache-2.0
 *
 * app_wifi.c — Zephyr WiFi STA management + DHCPv4 (BL-035).
 */

#include "app_wifi.h"

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/net_core.h>
#include <zephyr/net/net_context.h>
#include <zephyr/net/net_mgmt.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/net/dhcpv4.h>
#include <string.h>

LOG_MODULE_REGISTER(app_wifi, LOG_LEVEL_INF);

#ifndef APP_WIFI_SSID
#define APP_WIFI_SSID "DIGIFIBRA-ubEU"
#endif

#ifndef APP_WIFI_PSK
#define APP_WIFI_PSK ""
#endif

#define WIFI_SHELL_MODULE "wifi"
#define WIFI_CONNECT_TIMEOUT_S 15

static K_SEM_DEFINE(s_wifi_connected_sem, 0, 1);
static K_SEM_DEFINE(s_ipv4_assigned_sem, 0, 1);

static struct net_mgmt_event_callback s_wifi_cb;
static struct net_mgmt_event_callback s_ipv4_cb;

static bool s_connected = false;
static char s_ip_str[INET_ADDRSTRLEN] = "0.0.0.0";

static void handle_wifi_connect_result(struct net_mgmt_event_callback *cb, struct net_if *iface)
{
	const struct wifi_status *status = (const struct wifi_status *)cb->info;

	if (status && status->status) {
		LOG_WRN("WiFi connection failed (status: %d)", status->status);
		s_connected = false;
	} else {
		LOG_INF("WiFi STA connected to AP successfully! Requesting DHCPv4...");
		s_connected = true;
		if (iface) {
			net_dhcpv4_start(iface);
		}
		k_sem_give(&s_wifi_connected_sem);
	}
}

static void handle_wifi_disconnect_result(struct net_mgmt_event_callback *cb)
{
	LOG_WRN("WiFi disconnected from AP");
	s_connected = false;
	strncpy(s_ip_str, "0.0.0.0", sizeof(s_ip_str) - 1);
	s_ip_str[sizeof(s_ip_str) - 1] = '\0';
}

static void handle_ipv4_addr_add(struct net_if *iface)
{
	if (!iface || !iface->config.ip.ipv4) {
		return;
	}

	for (int i = 0; i < NET_IF_MAX_IPV4_ADDR; i++) {
		struct net_if_addr_ipv4 *uni = &iface->config.ip.ipv4->unicast[i];

		if (uni->ipv4.addr_type != NET_ADDR_DHCP &&
		    uni->ipv4.addr_type != NET_ADDR_AUTOCONF &&
		    uni->ipv4.addr_type != NET_ADDR_MANUAL) {
			continue;
		}

		if (net_addr_ntop(NET_AF_INET, &uni->ipv4.address.in_addr, s_ip_str, sizeof(s_ip_str)) != NULL) {
			LOG_INF("========================================");
			LOG_INF("  WiFi IP assigned: %s", s_ip_str);
			LOG_INF("  MCUmgr UDP port: 1337 ready");
			LOG_INF("========================================");
			k_sem_give(&s_ipv4_assigned_sem);
			return;
		}
	}
}

static void wifi_mgmt_event_handler(struct net_mgmt_event_callback *cb,
				    uint64_t mgmt_event, struct net_if *iface)
{
	switch (mgmt_event) {
	case NET_EVENT_WIFI_CONNECT_RESULT:
		handle_wifi_connect_result(cb, iface);
		break;
	case NET_EVENT_WIFI_DISCONNECT_RESULT:
		handle_wifi_disconnect_result(cb);
		break;
	case NET_EVENT_IPV4_ADDR_ADD:
		handle_ipv4_addr_add(iface);
		break;
	default:
		break;
	}
}

static void wifi_connect_task(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	/* Allow WiFi hardware subsystem to complete initialization */
	k_sleep(K_MSEC(1500));

	struct net_if *iface = net_if_get_default();
	if (!iface) {
		LOG_ERR("No default network interface found!");
		return;
	}

	char ssid_buf[33] = APP_WIFI_SSID;
	char psk_buf[65] = APP_WIFI_PSK;

	struct wifi_connect_req_params cnx_params = {
		.ssid = ssid_buf,
		.ssid_length = strlen(ssid_buf),
		.psk = psk_buf,
		.psk_length = strlen(psk_buf),
		.channel = WIFI_CHANNEL_ANY,
		.security = strlen(psk_buf) > 0 ? WIFI_SECURITY_TYPE_PSK : WIFI_SECURITY_TYPE_NONE,
		.band = WIFI_FREQ_BAND_2_4_GHZ,
		.mfp = WIFI_MFP_OPTIONAL,
	};

	LOG_INF("Connecting to WiFi SSID: %s (security: %d)...",
		cnx_params.ssid, cnx_params.security);

	int retry_count = 0;
	while (!s_connected) {
		retry_count++;
		int ret = net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &cnx_params, sizeof(cnx_params));
		if (ret != 0) {
			LOG_WRN("net_mgmt connect request returned %d (attempt %d)", ret, retry_count);
		} else {
			if (k_sem_take(&s_wifi_connected_sem, K_SECONDS(WIFI_CONNECT_TIMEOUT_S)) == 0) {
				LOG_INF("WiFi connection confirmed!");
				break;
			}
			LOG_WRN("WiFi connect timeout, retrying...");
		}
		k_sleep(K_SECONDS(3));
	}

	/* Sanitize stack buffers holding credentials (PLAN R7 / BL-024) */
	memset(psk_buf, 0, sizeof(psk_buf));
	memset(&cnx_params, 0, sizeof(cnx_params));

	/* Wait up to 10 seconds for DHCPv4 lease */
	if (k_sem_take(&s_ipv4_assigned_sem, K_SECONDS(10)) != 0) {
		LOG_WRN("DHCPv4 address assignment timed out; check router DHCP status");
	}
}

K_THREAD_DEFINE(wifi_thread_id, 4096, wifi_connect_task, NULL, NULL, NULL, 7, 0, 0);

int app_wifi_init(void)
{
	net_mgmt_init_event_callback(&s_wifi_cb, wifi_mgmt_event_handler,
				     NET_EVENT_WIFI_CONNECT_RESULT | NET_EVENT_WIFI_DISCONNECT_RESULT);
	net_mgmt_add_event_callback(&s_wifi_cb);

	net_mgmt_init_event_callback(&s_ipv4_cb, wifi_mgmt_event_handler,
				     NET_EVENT_IPV4_ADDR_ADD);
	net_mgmt_add_event_callback(&s_ipv4_cb);

	LOG_INF("WiFi STA management initialized");
	return 0;
}

bool app_wifi_is_connected(void)
{
	return s_connected && (strcmp(s_ip_str, "0.0.0.0") != 0);
}

const char *app_wifi_get_ip_str(void)
{
	return s_ip_str;
}

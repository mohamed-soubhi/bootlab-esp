/* SPDX-License-Identifier: Apache-2.0 */

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include "app_ble_smp.h"

LOG_MODULE_REGISTER(app_ble_smp, LOG_LEVEL_INF);

#if defined(CONFIG_MCUMGR_TRANSPORT_BT)

#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/conn.h>
#include <zephyr/bluetooth/gatt.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/mgmt/mcumgr/transport/smp_bt.h>

static struct k_work advertise_work;

static const struct bt_data ad[] = {
	BT_DATA_BYTES(BT_DATA_FLAGS, (BT_LE_AD_GENERAL | BT_LE_AD_NO_BREDR)),
	BT_DATA_BYTES(BT_DATA_UUID128_ALL, SMP_BT_SVC_UUID_VAL),
};

static const struct bt_data sd[] = {
	BT_DATA(BT_DATA_NAME_COMPLETE, CONFIG_BT_DEVICE_NAME, sizeof(CONFIG_BT_DEVICE_NAME) - 1),
};

static void advertise(struct k_work *work)
{
	ARG_UNUSED(work);
	int rc;

	rc = bt_le_adv_start(BT_LE_ADV_CONN_FAST_1, ad, ARRAY_SIZE(ad), sd, ARRAY_SIZE(sd));
	if (rc) {
		LOG_ERR("BLE Advertising failed to start (rc %d)", rc);
		return;
	}

	LOG_INF("BLE Advertising started: name='%s' (SMP over BLE)", CONFIG_BT_DEVICE_NAME);
}

static void connected(struct bt_conn *conn, uint8_t err)
{
	if (err) {
		LOG_ERR("BLE Connection failed: err 0x%02x (%s)", err, bt_hci_err_to_str(err));
		k_work_submit(&advertise_work);
	} else {
		LOG_INF("BLE Connected");
	}
}

static void disconnected(struct bt_conn *conn, uint8_t reason)
{
	LOG_INF("BLE Disconnected (reason 0x%02x %s)", reason, bt_hci_err_to_str(reason));
}

static void on_conn_recycled(void)
{
	k_work_submit(&advertise_work);
}

BT_CONN_CB_DEFINE(conn_callbacks) = {
	.connected = connected,
	.disconnected = disconnected,
	.recycled = on_conn_recycled,
};

static void bt_ready(int err)
{
	if (err != 0) {
		LOG_ERR("Bluetooth failed to initialize: %d", err);
	} else {
		LOG_INF("Bluetooth initialized, starting SMP advertising");
		k_work_submit(&advertise_work);
	}
}

int app_ble_smp_init(void)
{
	int rc;

	k_work_init(&advertise_work, advertise);
	rc = bt_enable(bt_ready);
	if (rc != 0) {
		LOG_ERR("Bluetooth enable failed: %d", rc);
		return rc;
	}
	return 0;
}

#else

int app_ble_smp_init(void)
{
	return 0;
}

#endif /* CONFIG_MCUMGR_TRANSPORT_BT */

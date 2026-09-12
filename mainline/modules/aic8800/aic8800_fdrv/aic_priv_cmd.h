/**
 ******************************************************************************
 *
 * @file private_cmd.h
 *
 * Copyright (C) Aicsemi 2018-2024
 *
 ******************************************************************************
 */

#ifndef _AIC_PRIV_CMD_H_
#define _AIC_PRIV_CMD_H_

#include "rwnx_main.h"

int android_priv_cmd(struct net_device *net, struct ifreq *ifr, int cmd);

#endif /* _AIC_PRIV_CMD_H_ */


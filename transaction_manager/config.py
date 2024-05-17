#   -*- coding: utf-8 -*-
#
#   This file is part of SKALE Transaction Manager
#
#   Copyright (C) 2021 SKALE Labs
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import sys
from typing import List, Optional

REDIS_URI: str = 'redis://@127.0.0.1:6379'

SGX_URL: Optional[str] = 'https://127.0.0.1:1026'

ETH_PRIVATE_KEY: Optional[str] = None

ENDPOINT: str = 'http://127.0.0.1:8545'

GAS_MULTIPLIER: float = 1.2

NODE_DATA_PATH = '/skale_node_data'

# General
RESTART_TIMEOUT: int = 3
BASE_WAITING_TIME: int = 25
CONFIRMATION_BLOCKS: int = 6
MAX_RESUBMIT_AMOUNT: int = 10
MAX_WAITING_TIME: int = 650  # TODO: determine value
UNDERPRICED_RETRIES = 5
ALLOWED_TS_DIFF = 300
DISABLE_GAS_ESTIMATION = False
TXRECORD_EXPIRATION = 24 * 60 * 60  # 1 day
DEFAULT_ID_LEN = 19
DEFAULT_GAS_LIMIT: int = 1000000
IMA_ID_SUFFIX = 'js'
STATSD_HOST: str = '127.0.0.1'
STATSD_PORT: int = 8125

# V1
AVG_GAS_PRICE_INC_PERCENT = 50
MAX_GAS_PRICE: int = 1000 * 10 ** 9
GAS_PRICE_INC_PERCENT: int = 10
GRAD_GAS_PRICE_INC_PERCENT: int = 2
MIN_GAS_PRICE_INC_PERCENT: int = 5

# V2
BASE_FEE_ADJUSMENT_PERCENT = 50
TARGET_REWARD_PERCENTILE = 60
MIN_PRIORITY_FEE: int = 10 ** 9
FEE_INC_PERCENT: int = 12
MAX_FEE_VALUE: int = 10 ** 18
MIN_FEE_INC_PERCENT: int = 5
MAX_TX_CAP: int = 10 ** 18
HARD_REPLACE_START_INDEX = 3
HARD_REPLACE_TIP_OFFSET = 10


def get_params() -> List[str]:
    return list(filter(
        lambda v: not v.startswith('__') and v in os.environ,
        globals()
    ))


for v in get_params():
    type_ = type(getattr(sys.modules[__name__], v))
    if not isinstance(None, type_):
        casted = type_(os.environ[v])
    else:
        casted = os.environ[v]
    globals()[v] = casted

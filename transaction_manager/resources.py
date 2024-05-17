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

import redis
import statsd  # type: ignore

from skale.utils.web3_utils import init_web3  # type: ignore
from web3 import Web3

from .config import ALLOWED_TS_DIFF, ENDPOINT, REDIS_URI, STATSD_HOST, STATSD_PORT

cpool: redis.ConnectionPool = redis.ConnectionPool.from_url(REDIS_URI)
rs: redis.Redis = redis.Redis(connection_pool=cpool)
w3: Web3 = init_web3(ENDPOINT, ts_diff=ALLOWED_TS_DIFF)
stdc: statsd.StatsClient = statsd.StatsClient(STATSD_HOST, STATSD_PORT)

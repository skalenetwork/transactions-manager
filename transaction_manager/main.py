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

import logging
import time

from . import config
from .attempt_manager import AttemptManagerV2, RedisAttemptStorage
from .eth import Eth
from .log import init_logger
from .processor import Processor
from .txpool import TxPool
from .utils import config_string
from .wallet import init_wallet

logger = logging.getLogger(__name__)


def run_proc():
    eth = Eth()
    pool = TxPool()
    wallet = init_wallet()
    attempt_manager = AttemptManagerV2(
        eth,
        RedisAttemptStorage(),
        wallet.address
    )

    proc = Processor(eth, pool, attempt_manager, wallet)
    logger.info('Starting transaction processor')
    proc.run()


def main() -> None:
    init_logger()
    while True:
        try:
            logger.info('Running processor. Config:\n%s', config_string(vars(config)))
            run_proc()
        except Exception:
            logger.exception('TM failed. Sleeping for %ds', config.RESTART_TIMEOUT)
            time.sleep(config.RESTART_TIMEOUT)


if __name__ == '__main__':
    main()

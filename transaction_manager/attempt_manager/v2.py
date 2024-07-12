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
from typing import Optional

from .base import BaseAttemptManager, made
from .storage import BaseAttemptStorage

from ..config import (
    BASE_FEE_ADJUSMENT_PERCENT,
    BASE_WAITING_TIME,
    FEE_INC_PERCENT,
    HARD_REPLACE_START_INDEX,
    HARD_REPLACE_TIP_OFFSET,
    MAX_FEE_VALUE,
    MAX_TX_CAP,
    MIN_FEE_INC_PERCENT,
    MIN_PRIORITY_FEE
)
from ..eth import Eth
from ..resources import stdc
from ..structures import Attempt, Fee, Tx

logger = logging.getLogger(__name__)


class AttemptManagerV2(BaseAttemptManager):
    def __init__(
        self,
        eth: Eth,
        storage: BaseAttemptStorage,
        source: str,
        current: Optional[Attempt] = None,
        base_waiting_time: int = BASE_WAITING_TIME,
        min_priority_fee: int = MIN_PRIORITY_FEE,
        inc_percent: int = FEE_INC_PERCENT,
        min_inc_percent: int = MIN_FEE_INC_PERCENT,
        max_fee: int = MAX_FEE_VALUE,
        max_tx_cap: int = MAX_TX_CAP,
        base_fee_adjustment_percent: int = BASE_FEE_ADJUSMENT_PERCENT
    ) -> None:
        self.eth = eth
        self._current = current
        self.storage = storage
        self.source = source
        self.base_waiting_time = base_waiting_time
        self.inc_percent = inc_percent
        self.min_priority_fee = min_priority_fee
        self.base_fee_adjustment_percent = base_fee_adjustment_percent
        self.min_inc_percent = min_inc_percent
        self.max_fee = max_fee

    def fetch(self) -> None:
        self._current = self.storage.get()

    @property
    def current(self) -> Optional[Attempt]:
        return self._current

    @made
    def save(self) -> None:
        if self.current:
            self.storage.save(self.current)

    def inc_fee_value(
        self,
        fee_value: int,
        inc: Optional[int] = None,
        min_fee: Optional[int] = None,
        max_fee: Optional[int] = None
    ) -> int:
        max_fee = max_fee or self.max_fee
        min_fee = min_fee or 0
        inc = max(self.min_inc_percent, inc or self.inc_percent)
        return max(
            min_fee,
            min(fee_value * (100 + inc) // 100, max_fee)
        )

    @made
    def replace(self, tx: Tx, replace_attempt: int = 0) -> None:
        tip = self.inc_fee_value(
            self.current.fee.max_priority_fee_per_gas,  # type: ignore
            inc=self.min_inc_percent
        )
        gap = self.inc_fee_value(
            self.current.fee.max_fee_per_gas,  # type: ignore
            inc=self.min_inc_percent
        )
        if gap == self.max_fee:
            logger.warning(
                'Next fee %d is not allowed. Defaulting to %d',
                gap, self.max_fee
            )

        # To prevent stucked legacy transactions
        if replace_attempt >= HARD_REPLACE_START_INDEX and tip + HARD_REPLACE_TIP_OFFSET < gap:
            # to make sure tip will never be more then gap
            tip = gap - HARD_REPLACE_TIP_OFFSET

        fee = Fee(max_priority_fee_per_gas=tip, max_fee_per_gas=gap)
        tx.fee = self._current.fee = fee  # type: ignore

    def next_fee_value(
        self,
        fee_value: int,
        min_fee: Optional[int] = None,
        max_fee: Optional[int] = None
    ) -> int:
        return self.inc_fee_value(fee_value, min_fee=min_fee, max_fee=max_fee)

    def next_waiting_time(self, attempt_index: int) -> int:
        return self.base_waiting_time + 10 * (attempt_index ** 2)

    def max_allowed_fee(self, gas: int, value: int) -> int:
        balance = self.eth.get_balance(self.source)
        return max(0, (balance - value)) // gas

    def calculate_initial_fee(
        self,
        estimated_base_fee: int,
        good_tip: int
    ) -> Fee:
        tip = max(self.min_priority_fee, good_tip)
        raw_gap = max(tip, estimated_base_fee)
        gap = (100 + self.base_fee_adjustment_percent) * raw_gap // 100
        return Fee(max_priority_fee_per_gas=tip, max_fee_per_gas=gap)

    def make(self, tx: Tx) -> None:
        last = self.current
        nonce = self.eth.get_nonce(self.source)
        logger.info(f'Received current nonce - {nonce}')

        history = self.eth.get_fee_history()
        estimated_base_fee = self.eth.get_estimated_base_fee(history)
        good_tip = self.eth.get_p60_tip(history)

        if last is None or nonce > last.nonce or last.fee is None:
            next_index = 1
            next_fee = self.calculate_initial_fee(estimated_base_fee, good_tip)
            next_wait_time = self.base_waiting_time
        else:
            next_index = last.index + 1
            tip = self.next_fee_value(
                last.fee.max_priority_fee_per_gas,  # type: ignore
                min_fee=good_tip
            )
            gap = self.next_fee_value(
                last.fee.max_fee_per_gas,  # type: ignore
                min_fee=estimated_base_fee
            )
            stdc.gauge('tm.max_priority_fee', tip)
            stdc.gauge('tm.max_fee_per_gas', gap)
            next_fee = Fee(max_priority_fee_per_gas=tip, max_fee_per_gas=gap)
            next_wait_time = self.next_waiting_time(next_index)
            stdc.gauge('tm.next_wating_time', gap)

        logger.info('Next fee %s', next_fee)
        tx.fee, tx.nonce = next_fee, nonce
        estimated_gas = self.eth.calculate_gas(tx)

        logger.info('Estimated gas %d', estimated_gas)
        tx.gas = max(estimated_gas, tx.gas or 0)
        if tx.gas > estimated_gas:
            allowed_fee = self.max_allowed_fee(tx.gas, tx.value)
            if allowed_fee < next_fee.max_fee_per_gas:   # type: ignore
                logger.warning(
                    'Suggested fee exceeds allowance. Defaulting to %d',
                    estimated_gas
                )
                tx.gas = estimated_gas
            else:
                logger.info(
                    'Estimated gas will be ignored in favor of %d',
                    tx.gas
                )

        self._current = Attempt(
            tx_id=tx.tx_id,
            nonce=nonce,
            index=next_index,
            fee=next_fee,
            wait_time=next_wait_time,
            gas=tx.gas
        )
